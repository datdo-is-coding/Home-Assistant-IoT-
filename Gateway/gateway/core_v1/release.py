"""Signed Gateway software releases and encrypted SQLite recovery bundles.

No signing private key, OS upgrade, artifact-provided install script, or implicit
service action is accepted. Lifecycle callbacks belong to the trusted operator.
"""
import ast
import base64
from contextlib import closing, contextmanager
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tarfile
import tempfile
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

MAX_BYTES = 256 * 1024 * 1024

def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())

def _cipher(key):
    if len(key) != 32:
        raise ValueError('key must contain exactly 32 raw bytes')
    return Fernet(base64.urlsafe_b64encode(key))

def read_key(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('key must be a private regular file (mode 600)')
    key = path.read_bytes()
    _cipher(key)
    return key

def _check_database(connection, master_key=None):
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite integrity check failed')
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('SQLite foreign key check failed')
    if connection.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise ValueError('unsupported schema: release supports schema 1 only')
    if master_key is not None:
        cipher = _cipher(master_key)
        for table, column in (('factory_devices', 'secret'), ('node_credentials', 'key_cipher')):
            for (value,) in connection.execute(f'SELECT {column} FROM {table}'):
                if len(cipher.decrypt(value)) != 32:
                    raise ValueError('invalid credential in recovery database')

def backup(database, master_key, destination, recovery_key):
    """Online SQLite backup without starting Registry or changing its state."""
    database = Path(database).resolve(strict=True)
    _cipher(master_key)
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / 'core.db'
        private_write(snapshot, b'')
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                _check_database(target, master_key)
        if snapshot.stat().st_size > MAX_BYTES:
            raise ValueError('backup exceeds supported 256 MiB')
        bundle = json.dumps(dict(format=1, master_key=base64.b64encode(master_key).decode(),
                                 database=base64.b64encode(snapshot.read_bytes()).decode()), separators=(',', ':')).encode()
        private_write(destination, _cipher(recovery_key).encrypt(bundle))

def restore(bundle, recovery_key, destination):
    """Restore into a NEW private directory; never overwrite a live database."""
    bundle = Path(bundle)
    if bundle.stat().st_size > MAX_BYTES * 2:
        raise ValueError('recovery bundle too large')
    data = json.loads(_cipher(recovery_key).decrypt(bundle.read_bytes()))
    if data.get('format') != 1:
        raise ValueError('unsupported recovery format')
    key = base64.b64decode(data['master_key'], validate=True)
    raw = base64.b64decode(data['database'], validate=True)
    if len(raw) > MAX_BYTES:
        raise ValueError('recovery database too large')
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('restore destination must not exist')
    with tempfile.TemporaryDirectory(prefix='.hc-restore-', dir=destination.parent) as tmp:
        staged = Path(tmp) / 'data'
        staged.mkdir(mode=0o700)
        private_write(staged / 'core.db', raw)
        private_write(staged / 'master.key', key)
        with closing(sqlite3.connect(staged / 'core.db')) as connection:
            _check_database(connection, key)
        os.rename(staged, destination)
    return destination

def verify(artifact, manifest, signature, public_key):
    """Signature covers exact manifest bytes, binding target/version/hash/size."""
    if len(manifest) > 8192:
        raise ValueError('manifest too large')
    if isinstance(public_key, bytes):
        public_key = serialization.load_pem_public_key(public_key)
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        public_key.verify(signature, manifest)
    elif isinstance(public_key, ec.EllipticCurvePublicKey) and isinstance(public_key.curve, ec.SECP256R1):
        public_key.verify(signature, manifest, ec.ECDSA(hashes.SHA256()))
    else:
        raise ValueError('only Ed25519 or ECDSA P-256 public keys are supported')
    data = json.loads(manifest)
    if (data.get('format') != 1 or data.get('target') != 'home-competition-gateway'
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', str(data.get('version', '')))
            or data.get('schema_min') != 1 or data.get('schema_max') != 1
            or type(data.get('size')) is not int or not 0 < data['size'] <= MAX_BYTES
            or not re.fullmatch('[0-9a-f]{64}', str(data.get('sha256', '')))):
        raise ValueError('invalid release manifest or unsupported schema')
    if len(artifact) != data['size'] or hashlib.sha256(artifact).hexdigest() != data['sha256']:
        raise ValueError('release size/hash mismatch')
    return data

def _extract(artifact, destination):
    total, count, seen = 0, 0, set()
    with tarfile.open(fileobj=io.BytesIO(artifact), mode='r:*') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            count += 1
            total += member.size
            if (count > 10000 or total > MAX_BYTES or path.is_absolute() or '..' in path.parts
                    or not path.parts or '\\' in member.name or member.name in seen
                    or not (member.isfile() or member.isdir())):
                raise ValueError('unsafe release archive member')
            seen.add(member.name)
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.extractfile(member) as source:
                    private_write(target, source.read(MAX_BYTES + 1))
    entry = destination / 'gateway/core_v1/__main__.py'
    if not entry.is_file():
        raise ValueError('release lacks gateway/core_v1/__main__.py')
    for source in destination.rglob('*.py'):
        ast.parse(source.read_bytes(), filename=str(source))

class ReleaseManager:
    def __init__(self, root, public_key):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('release root must be an existing private directory')
        self.public_key = public_key

    @contextmanager
    def _lock(self):
        fd = os.open(self.root / '.release.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def stage(self, artifact_path, manifest_path, signature_path):
        artifact_path = Path(artifact_path)
        if artifact_path.stat().st_size > MAX_BYTES:
            raise ValueError('release artifact too large')
        artifact = artifact_path.read_bytes()
        manifest = Path(manifest_path).read_bytes()
        signature = Path(signature_path).read_bytes()
        info = verify(artifact, manifest, signature, self.public_key)
        with self._lock():
            destination = self.root / info['version']
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('release already staged')
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=self.root) as tmp:
                tree = Path(tmp) / 'release'
                tree.mkdir(mode=0o700)
                _extract(artifact, tree)

                private_write(tree / '.hc-artifact', artifact)
                private_write(tree / '.hc-manifest', manifest)
                private_write(tree / '.hc-signature', signature)
                os.rename(tree, destination)
        return destination

    def _switch(self, target):
        temporary = self.root / '.current-next'
        temporary.symlink_to(target.name)
        try:
            os.replace(temporary, self.root / 'current')
        finally:
            temporary.unlink(missing_ok=True)

    def activate(self, version, database, master_key, recovery_key, backup_path, *, stop, start, health):
        """Trusted callbacks control restart and bounded health checks.

        Software rollback only: schema-changing upgrades are rejected. A failed
        health check never replaces the user's database with an older snapshot.
        """
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
            raise ValueError('invalid release version')
        with self._lock():
            target = self.root / version
            if target.is_symlink() or not target.is_dir():
                raise ValueError('release must be a staged directory')
            info = verify((target / '.hc-artifact').read_bytes(), (target / '.hc-manifest').read_bytes(),
                          (target / '.hc-signature').read_bytes(), self.public_key)
            if info['version'] != version:
                raise ValueError('release version mismatch')

            with tempfile.TemporaryDirectory(prefix='.verify-', dir=self.root) as tmp:
                clean = Path(tmp) / 'release'
                clean.mkdir(mode=0o700)
                _extract((target / '.hc-artifact').read_bytes(), clean)
                expected = {p.relative_to(clean): p.read_bytes() for p in clean.rglob('*') if p.is_file()}
                actual = {p.relative_to(target): p.read_bytes() for p in target.rglob('*') if p.is_file()
                          and p.name not in ('.hc-artifact', '.hc-manifest', '.hc-signature')}
                if any(p.is_symlink() for p in target.rglob('*')) or actual != expected:
                    raise ValueError('staged release modified')
            current = self.root / 'current'
            if not current.is_symlink():
                raise ValueError('current must point to a known healthy release before update')
            old = current.resolve(strict=True)
            if old.parent != self.root or old == target:
                raise ValueError('invalid previous release')
            if tuple(map(int, version.split('.'))) <= tuple(map(int, old.name.split('.'))):
                raise ValueError('version must increase; rollback only occurs after failed health check')
            stopped, switched = False, False
            try:
                stop()
                stopped = True
                backup(database, master_key, backup_path, recovery_key)
                self._switch(target)
                switched = True
                start()
                if not health():
                    raise RuntimeError('new release failed health check')
            except Exception:
                if switched:
                    stop()
                    self._switch(old)
                if stopped:
                    start()
                    if not health():
                        raise RuntimeError('rollback restart failed health check; operator recovery required')
                raise
            return dict(status='SUCCEEDED', version=version, previous=old.name, backup=str(backup_path))
