"""Independent, operator-configured OTA for the existing gateway/main.py runtime.

The package supplies data, never lifecycle commands. Rollback changes software
pointers only; encrypted SQLite snapshots are for deliberate operator recovery.
"""
import argparse
import ast
from contextlib import closing, contextmanager
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .core_v1.release import MAX_BYTES, private_write, read_key

MAX_RUNTIME_BYTES = 2 * 1024 * 1024 * 1024
SERVICES = frozenset(('smarthome-gateway.service', 'homecompetition-gateway.service'))
FINAL = frozenset(('COMMITTED', 'ROLLED_BACK'))
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+'
NAME = r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}'


def host_profile():
    return dict(os=platform.system().lower(), architecture=platform.machine().lower(),
                python_abi=sys.implementation.cache_tag, profile='legacy-main-v1')


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _tree(root, *, follow=False):
    """Canonical file content/mode inventory, including empty directories."""
    result, total = [], 0
    def walk(directory, relative, ancestors):
        nonlocal total
        real = directory.resolve(strict=True)
        if real in ancestors:
            raise ValueError('runtime directory cycle')
        for path in sorted(directory.iterdir()):
            name = relative / path.name
            if path.is_symlink() and not follow:
                raise ValueError('staged release modified: symbolic link')
            mode = path.stat().st_mode
            if stat.S_ISDIR(mode):
                result.append([str(name), 'directory'])
                walk(path, name, ancestors | {real})
            elif stat.S_ISREG(mode):
                size = path.stat().st_size
                total += size
                if total > MAX_RUNTIME_BYTES or len(result) > 100000:
                    raise ValueError('runtime exceeds supported bounds')
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(block)
                result.append([str(name), bool(mode & 0o111), size, digest.hexdigest()])
            else:
                raise ValueError('runtime contains a non-regular file')
    walk(Path(root), PurePosixPath(), set())
    return result


def runtime_digest(root):
    """Digest an operator runtime; symlinks are dereferenced during staging."""
    return hashlib.sha256(json.dumps(_tree(Path(root), follow=True), separators=(',', ':')).encode()).hexdigest()


def _freeze(tree):
    for path in tree.rglob('*'):
        if path.is_file():
            path.chmod(0o555 if path.stat().st_mode & 0o111 else 0o444)
            with path.open('rb') as source:
                os.fsync(source.fileno())
    for path in sorted((p for p in tree.rglob('*') if p.is_dir()), reverse=True):
        path.chmod(0o555)
        _sync_dir(path)
    _sync_dir(tree)


def _extract(artifact, destination):
    total, count, seen = 0, 0, set()
    with tarfile.open(fileobj=io.BytesIO(artifact), mode='r:*') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            count += 1
            total += member.size
            normalized = str(path)
            if (count > 10000 or total > MAX_BYTES or member.size < 0
                    or path.is_absolute() or '..' in path.parts or not path.parts
                    or '\\' in member.name or normalized in seen or path.parts[0] == '.ota'
                    or not (member.isfile() or member.isdir()) or member.mode & 0o7000):
                raise ValueError('unsafe release archive member')
            seen.add(normalized)
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                if shutil.disk_usage(destination).free < member.size + 16 * 1024 * 1024:
                    raise ValueError('insufficient staging space')
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.extractfile(member) as source:
                    content = source.read(MAX_BYTES + 1)
                if len(content) != member.size:
                    raise ValueError('truncated archive member')
                private_write(target, content)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    entry = destination / 'gateway/main.py'
    if not entry.is_file():
        raise ValueError('release lacks gateway/main.py')
    for source in (destination / 'gateway').rglob('*.py'):
        ast.parse(source.read_bytes(), filename=str(source))


def _cipher(key):
    import base64
    if len(key) != 32:
        raise ValueError('recovery key must contain 32 raw bytes')
    return Fernet(base64.urlsafe_b64encode(key))


def _database(path, expected):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('SQLite foreign key check failed')
        if db.execute('PRAGMA user_version').fetchone()[0] != expected:
            raise ValueError('incompatible database schema; migration requires operator service')


def inspect_backup(path, recovery_key):
    """Decrypt a bounded archive for inspection; deliberately does not restore."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES * 2:
        raise ValueError('backup exceeds supported bounds')
    raw = _cipher(recovery_key).decrypt(path.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        result = {}
        for member in archive:
            if not member.isfile() or member.size > MAX_BYTES:
                raise ValueError('invalid recovery archive')
            result[member.name] = archive.extractfile(member).read()
        return result


class GatewayUpdater:
    def __init__(self, root, public_key, runtime_profile, inventory, recovery_key, *, runtime_source=None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or self.root.stat().st_mode & 0o022:
            raise ValueError('release root must be an existing operator-owned directory without public writes')
        self.public_key = serialization.load_pem_public_key(public_key) if isinstance(public_key, bytes) else public_key
        if not isinstance(self.public_key, ec.EllipticCurvePublicKey) or not isinstance(self.public_key.curve, ec.SECP256R1):
            raise ValueError('only ECDSA P-256 signing keys are supported')
        self.profile = dict(runtime_profile)
        if set(self.profile) != {'os', 'architecture', 'python_abi', 'profile'} or self.profile['profile'] != 'legacy-main-v1':
            raise ValueError('unsupported Gateway runtime profile')
        self.inventory = inventory
        self.recovery_key = recovery_key
        _cipher(recovery_key)
        self.runtime_source = Path(runtime_source).resolve(strict=True) if runtime_source else None
        self.databases = self._paths('databases')
        self.files = self._paths('files')
        if not self.databases:
            raise ValueError('explicit database inventory is required')
        if any(path == self.root or path.is_relative_to(self.root) for path in (*self.databases.values(), *self.files.values())):
            raise ValueError('customer data must be outside the release root')

    def _paths(self, kind):
        result = {}
        for name, value in self.inventory.get(kind, {}).items():
            if not re.fullmatch(NAME, name):
                raise ValueError('invalid inventory name')
            path = Path(value)
            if path.is_symlink() or not path.is_file():
                raise ValueError('inventory paths must be existing regular files')
            result[name] = path.resolve(strict=True)
        if len(set(result.values())) != len(result):
            raise ValueError('duplicate inventory path')
        return result

    @contextmanager
    def _lock(self):
        fd = os.open(self.root / '.updater.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def _verify(self, artifact, manifest, signature, *, fresh):
        if len(manifest) > 16384:
            raise ValueError('manifest too large')
        self.public_key.verify(signature, manifest, ec.ECDSA(hashes.SHA256()))
        data = _json(manifest)
        schema = data.get('database_schema')
        if (data.get('format') != 2 or data.get('target') != 'home-competition-gateway'
                or data.get('entrypoint') != 'gateway/main.py' or data.get('runtime') != self.profile
                or not re.fullmatch(VERSION, str(data.get('version', '')))
                or type(data.get('size')) is not int or not 0 < data['size'] <= MAX_BYTES
                or not re.fullmatch('[0-9a-f]{64}', str(data.get('sha256', '')))
                or not re.fullmatch('[0-9a-f]{64}', str(data.get('runtime_sha256', '')))
                or data.get('rollback_compatible') is not True or not isinstance(schema, dict)
                or set(schema) != set(self.databases) or any(type(v) is not int or v < 0 for v in schema.values())
                or type(data.get('release_counter')) is not int or data['release_counter'] < 1
                or type(data.get('security_epoch')) is not int or data['security_epoch'] < 0
                or type(data.get('expires_at')) is not int):
            raise ValueError('invalid Gateway manifest/runtime profile or incompatible migration')
        if fresh and (time.time() < 1704067200 or data['expires_at'] <= time.time()):
            raise ValueError('manifest expired or system clock untrusted')
        if len(artifact) != data['size'] or hashlib.sha256(artifact).hexdigest() != data['sha256']:
            raise ValueError('release size/hash mismatch')
        return data

    def _check_data(self, info):
        known = set(self.databases.values())
        for value in self.inventory.get('data_roots', []):
            directory = Path(value).resolve(strict=True)
            if directory == self.root or directory.is_relative_to(self.root):
                raise ValueError('data root is inside releases')
            for path in directory.rglob('*'):
                if path.is_file() and path.resolve() not in known:
                    with path.open('rb') as source:
                        sqlite_header = source.read(16) == b'SQLite format 3\x00'
                    if sqlite_header or path.suffix.lower() in ('.db', '.sqlite', '.sqlite3'):
                        raise ValueError('unlisted database in data inventory')
        for name, path in self.databases.items():
            if path.is_symlink() or not path.is_file():
                raise ValueError('database inventory changed')
            _database(path, info['database_schema'][name])

    def stage(self, artifact_path, manifest_path, signature_path):
        artifact_path = Path(artifact_path)
        if artifact_path.stat().st_size > MAX_BYTES or Path(manifest_path).stat().st_size > 16384 or Path(signature_path).stat().st_size > 256:
            raise ValueError('release input exceeds supported bounds')
        artifact, manifest, signature = (Path(p).read_bytes() for p in (artifact_path, manifest_path, signature_path))
        info = self._verify(artifact, manifest, signature, fresh=True)
        self._check_data(info)
        with self._lock():
            destination = self.root / info['version']
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('release already staged')
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=self.root) as tmp:
                tree = Path(tmp) / 'release'
                tree.mkdir(mode=0o700)
                _extract(artifact, tree)
                if not (tree / 'runtime').exists():
                    if self.runtime_source is None:
                        raise ValueError('package needs a bundled or operator-provisioned runtime')
                    size = sum(row[2] for row in _tree(self.runtime_source, follow=True) if len(row) == 4)
                    if shutil.disk_usage(self.root).free < size + 16 * 1024 * 1024:
                        raise ValueError('insufficient space for private runtime')
                    shutil.copytree(self.runtime_source, tree / 'runtime', symlinks=False)
                python = tree / 'runtime/bin/python3'
                if not python.is_file() or not python.stat().st_mode & 0o111 or runtime_digest(tree / 'runtime') != info['runtime_sha256']:
                    raise ValueError('runtime content/hash mismatch or missing fixed interpreter')
                metadata = tree / '.ota'
                metadata.mkdir(mode=0o700)
                for name, raw in (('artifact', artifact), ('manifest.json', manifest), ('signature', signature)):
                    private_write(metadata / name, raw)
                # The runtime digest is signed even when provisioned from trusted local files.
                _freeze(tree)
                os.rename(tree, destination)
                destination.chmod(0o555)
                _sync_dir(destination)
                _sync_dir(self.root)
            return destination

    def _release(self, version, *, fresh=False):
        if not re.fullmatch(VERSION, str(version)):
            raise ValueError('invalid release version')
        tree = self.root / version
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError('release must be an immutable staged directory')
        if tree.stat().st_mode & 0o222 or any(p.stat().st_mode & 0o222 for p in tree.rglob('*')):
            raise ValueError('staged release modified: writable content')
        metadata = tree / '.ota'
        if metadata.is_symlink():
            raise ValueError('staged release modified')
        for name, limit in (('artifact', MAX_BYTES), ('manifest.json', 16384), ('signature', 256)):
            path = metadata / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
                raise ValueError('staged release modified: invalid metadata')
        artifact, manifest, signature = ((metadata / name).read_bytes() for name in ('artifact', 'manifest.json', 'signature'))
        info = self._verify(artifact, manifest, signature, fresh=fresh)
        if info['version'] != version:
            raise ValueError('release version mismatch')
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=self.root) as tmp:
            expected = Path(tmp) / 'release'
            expected.mkdir()
            _extract(artifact, expected)
            actual = _tree(tree)
            runtime = [row for row in actual if row[0] == 'runtime' or row[0].startswith('runtime/')]
            package = [row for row in actual if not row[0].startswith('.ota') and not row[0].startswith('runtime/') and row[0] != 'runtime']
            expected_package = [row for row in _tree(expected) if not row[0].startswith('runtime/') and row[0] != 'runtime']
            if package != expected_package or runtime_digest(tree / 'runtime') != info['runtime_sha256']:
                raise ValueError('staged release modified')
            allowed_meta = {'.ota', '.ota/artifact', '.ota/manifest.json', '.ota/signature'}
            if any(row[0].startswith('.ota') and row[0] not in allowed_meta for row in actual) or not runtime:
                raise ValueError('staged release modified')
        return info

    def _pointer(self, name, version):
        temporary = self.root / ('.' + name + '-next')
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(version)
        os.replace(temporary, self.root / name)
        _sync_dir(self.root)

    def _current(self):
        current = self.root / 'current'
        if not current.is_symlink():
            raise ValueError('current must point to a verified healthy staged release')
        value = os.readlink(current)
        if not re.fullmatch(VERSION, value):
            raise ValueError('invalid current pointer')
        self._release(value)
        return value

    def _write_journal(self, record):
        temporary = self.root / '.activation-next'
        temporary.unlink(missing_ok=True)
        private_write(temporary, json.dumps(record, sort_keys=True).encode())
        os.replace(temporary, self.root / 'activation.json')
        _sync_dir(self.root)

    def _read_journal(self):
        path = self.root / 'activation.json'
        if not path.exists():
            return None
        if path.is_symlink() or path.stat().st_size > 16384:
            raise ValueError('invalid activation journal')
        record = _json(path.read_bytes())
        if (record.get('status') not in FINAL | {'PREPARED', 'STOPPED', 'SWITCHED', 'VERIFYING', 'RECOVERING', 'NEEDS_SERVICE'}
                or not re.fullmatch(VERSION, str(record.get('previous', '')))
                or not re.fullmatch(VERSION, str(record.get('version', '')))):
            raise ValueError('invalid activation journal')
        return record

    def _backup(self, info, destination):
        self._check_data(info)
        stream = io.BytesIO()
        total = 0
        with tempfile.TemporaryDirectory(prefix='.backup-', dir=self.root) as tmp:
            with tarfile.open(fileobj=stream, mode='w:') as archive:
                for name, source in self.databases.items():
                    snapshot = Path(tmp) / (name + '.sqlite3')
                    private_write(snapshot, b'')
                    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as db:
                        with closing(sqlite3.connect(snapshot)) as target:
                            db.backup(target)
                    _database(snapshot, info['database_schema'][name])
                    total += snapshot.stat().st_size
                    if total > MAX_BYTES:
                        raise ValueError('backup exceeds supported bounds')
                    archive.add(snapshot, arcname='databases/' + name + '.sqlite3', recursive=False)
                for name, source in self.files.items():
                    if source.is_symlink() or not source.is_file():
                        raise ValueError('private file inventory changed')
                    total += source.stat().st_size
                    if total > MAX_BYTES:
                        raise ValueError('backup exceeds supported bounds')
                    archive.add(source, arcname='files/' + name, recursive=False)
                if stream.tell() > MAX_BYTES:
                    raise ValueError('backup exceeds supported bounds')
        private_write(destination, _cipher(self.recovery_key).encrypt(stream.getvalue()))
        _sync_dir(destination.parent)

    def _recover(self, record, *, stop, start, health):
        if record is None:
            return dict(status='IDLE')
        if record['status'] in FINAL:
            return record
        try:
            record['status'] = 'RECOVERING'
            self._write_journal(record)
            stop()
            old = self._release(record['previous'])
            self._check_data(old)
            self._pointer('current', record['previous'])
            start()
            if not health():
                raise RuntimeError('previous release failed local health')
            self._check_data(old)
            record['status'] = 'ROLLED_BACK'
            record.pop('error', None)
        except Exception as exc:
            record['status'] = 'NEEDS_SERVICE'
            record['error'] = type(exc).__name__
        self._write_journal(record)
        return record

    def recover(self, *, stop, start, health):
        with self._lock():
            return self._recover(self._read_journal(), stop=stop, start=start, health=health)

    def prepare_boot_recovery(self):
        """Before=Gateway boot gate: recover pointers without waiting on systemd.

        The independent agent must later call recover() to run local health and
        finalize. Starting the ordered Gateway here would deadlock systemd.
        """
        with self._lock():
            record = self._read_journal()
            if record is None:
                self._current()
                return dict(status='IDLE')
            if record['status'] in FINAL:
                expected = record['version'] if record['status'] == 'COMMITTED' else record['previous']
                if self._current() != expected:
                    raise ValueError('current pointer conflicts with completed journal')
                return record
            try:
                record['status'] = 'RECOVERING'
                self._write_journal(record)
                previous = self._release(record['previous'])
                self._check_data(previous)
                self._pointer('current', record['previous'])
            except Exception as exc:
                record.update(status='NEEDS_SERVICE', error=type(exc).__name__)
                self._write_journal(record)
                return record
            return {**record, 'status': 'RECOVERY_PENDING_HEALTH'}

    def activate(self, version, *, stop, start, health):
        with self._lock():
            pending = self._read_journal()
            if pending and pending['status'] not in FINAL:
                raise RuntimeError('pending activation requires recovery first')
            new = self._release(version, fresh=True)
            previous = self._current()
            old = self._release(previous)
            self._check_data(new)
            self._check_data(old)
            if (new['release_counter'] <= old['release_counter'] or new['security_epoch'] < old['security_epoch']
                    or new['database_schema'] != old['database_schema']):
                raise ValueError('release counter/security epoch must advance without incompatible migrations')
            backups = self.root / 'backups'
            backups.mkdir(mode=0o700, exist_ok=True)
            if backups.is_symlink():
                raise ValueError('backup directory cannot be a symlink')
            backup = backups / (version + '-' + str(time.time_ns()) + '.enc')
            record = dict(status='PREPARED', version=version, previous=previous, backup=str(backup))
            self._write_journal(record)
            try:
                stop()
                record['status'] = 'STOPPED'
                self._write_journal(record)
                self._backup(old, backup)
                self._pointer('previous', previous)
                record['status'] = 'SWITCHED'
                self._write_journal(record)
                self._pointer('current', version)
                record['status'] = 'VERIFYING'
                self._write_journal(record)
                start()
                if not health():
                    raise RuntimeError('new release failed local health')
                self._check_data(new)
                record['status'] = 'COMMITTED'
                self._write_journal(record)
                return record
            except Exception as exc:
                record['error'] = type(exc).__name__
                return self._recover(record, stop=stop, start=start, health=health)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('local health redirects are forbidden')


def systemd_actions(service, health_url, *, health_seconds=30):
    if service not in SERVICES:
        raise ValueError('service is outside the updater allowlist')
    url = urlsplit(health_url)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1') or url.username or url.password or url.fragment:
        raise ValueError('health URL must be literal loopback HTTP')
    def action(operation):
        subprocess.run(['/usr/bin/systemctl', operation, service], check=True, timeout=60,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    def health():
        deadline = time.monotonic() + health_seconds
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        while time.monotonic() < deadline:
            try:
                with opener.open(health_url, timeout=min(3, health_seconds)) as response:
                    if response.status == 200:
                        raw = response.read(16385)
                        if len(raw) <= 16384:
                            data = _json(raw)
                            if isinstance(data, dict) and data.get('status') == 'ok':
                                return True
            except (OSError, ValueError):
                pass
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        return False
    return dict(stop=lambda: action('stop'), start=lambda: action('start'), health=health)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='private operator JSON configuration')
    commands = parser.add_subparsers(dest='command', required=True)
    stage = commands.add_parser('stage')
    for name in ('artifact', 'manifest', 'signature'):
        stage.add_argument(name)
    activate = commands.add_parser('activate')
    activate.add_argument('version')
    commands.add_parser('recover')
    commands.add_parser('boot-recover')
    digest = commands.add_parser('runtime-digest')
    digest.add_argument('directory')
    args = parser.parse_args(argv)
    if args.command == 'runtime-digest':
        print(runtime_digest(args.directory))
        return 0
    if not args.config:
        parser.error('--config is required')
    path = Path(args.config)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('operator config must be a private regular file')
    config = _json(path.read_bytes())
    manager = GatewayUpdater(config['root'], Path(config['public_key']).read_bytes(), host_profile(),
                             config['inventory'], read_key(config['recovery_key']), runtime_source=config.get('runtime_source'))
    if args.command == 'stage':
        print(json.dumps(dict(status='STAGED', path=str(manager.stage(args.artifact, args.manifest, args.signature)))))
        return 0
    if args.command == 'boot-recover':
        result = manager.prepare_boot_recovery()
    else:
        actions = systemd_actions(config['service'], config['health_url'])
        result = manager.activate(args.version, **actions) if args.command == 'activate' else manager.recover(**actions)
    print(json.dumps(result, sort_keys=True))
    return 1 if result['status'] == 'NEEDS_SERVICE' else 0


if __name__ == '__main__':
    raise SystemExit(main())
