import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from gateway import ota_updater


class PowerCut(BaseException):
    pass


class GatewayUpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / 'releases'
        self.root.mkdir(mode=0o700)
        self.data = self.home / 'data'
        self.data.mkdir(mode=0o700)
        self.db = self.data / 'registry.db'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE events(value TEXT)')
            db.execute("INSERT INTO events VALUES('original')")
        self.secret = self.data / 'master.key'
        self.secret.write_bytes(b'private customer credential')
        self.secret.chmod(0o600)
        self.runtime = self.home / 'runtime'
        (self.runtime / 'bin').mkdir(parents=True)
        (self.runtime / 'bin/python3').write_bytes(b'operator-pinned Python runtime')
        (self.runtime / 'bin/python3').chmod(0o755)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.profile = dict(os='linux', architecture='test-cpu', python_abi='cpython-312', profile='legacy-main-v1')
        self.inventory = dict(databases={'registry': str(self.db)}, files={'master.key': str(self.secret)},
                              data_roots=[str(self.data)])
        self.manager = ota_updater.GatewayUpdater(self.root, self.key.public_key(), self.profile,
                                                self.inventory, b'r' * 32, runtime_source=self.runtime)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def package(self, version='1.1.0', unsafe=None, **changes):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            entry = tarfile.TarInfo(unsafe or 'gateway/main.py')
            content = b'print("existing Gateway runtime")\n'
            entry.size = len(content)
            if unsafe == 'link':
                entry.type = tarfile.SYMTYPE
                entry.linkname = '/tmp/escape'
            archive.addfile(entry, io.BytesIO(content))
        artifact = stream.getvalue()
        info = dict(format=2, target='home-competition-gateway', entrypoint='gateway/main.py',
                    version=version, runtime=self.profile, runtime_sha256=ota_updater.runtime_digest(self.runtime),
                    size=len(artifact), sha256=hashlib.sha256(artifact).hexdigest(),
                    database_schema={name: 0 for name in self.manager.databases}, rollback_compatible=True,
                    release_counter=int(version.split('.')[1]) + 1, security_epoch=0,
                    expires_at=int(time.time()) + 3600)
        info.update(changes)
        manifest = json.dumps(info, sort_keys=True).encode()
        paths = [self.home / (version + suffix) for suffix in ('.tgz', '.json', '.sig')]
        for path, raw in zip(paths, (artifact, manifest, self.key.sign(manifest, ec.ECDSA(hashes.SHA256())))):
            path.write_bytes(raw)
        return paths

    def previous(self):
        self.manager.stage(*self.package('1.0.0'))
        (self.root / 'current').symlink_to('1.0.0')
        self.manager.stage(*self.package())

    def actions(self, health=None):
        return dict(stop=lambda: self.calls.append('stop'), start=lambda: self.calls.append('start'),
                    health=health or (lambda: True))

    def test_stages_main_entrypoint_and_private_immutable_runtime(self):
        release = self.manager.stage(*self.package())
        self.assertEqual((release / 'runtime/bin/python3').read_bytes(), (self.runtime / 'bin/python3').read_bytes())
        self.assertEqual((release / 'gateway/main.py').stat().st_mode & 0o777, 0o444)
        self.assertEqual((release / 'runtime/bin/python3').stat().st_mode & 0o777, 0o555)
        with self.assertRaises(FileExistsError):
            self.manager.stage(*self.package())

    def test_rejects_unsafe_archives_signatures_profiles_and_expiry(self):
        for unsafe in ('../../escape', '/tmp/escape', 'link', 'a/../escape', '.ota/manifest.json'):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                self.manager.stage(*self.package(unsafe=unsafe))
        for change in ({'runtime': {**self.profile, 'python_abi': 'cpython-311'}},
                       {'runtime_sha256': '0' * 64}, {'expires_at': 1},
                       {'rollback_compatible': False}, {'database_schema': {'registry': 1}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.stage(*self.package(**change))
        paths = self.package()
        paths[2].write_bytes(b'bad signature')
        with self.assertRaises(InvalidSignature):
            self.manager.stage(*paths)

    def test_rejects_modified_stage_before_stop(self):
        self.previous()
        entry = self.root / '1.1.0/gateway/main.py'
        entry.chmod(0o600)
        entry.write_text('raise RuntimeError("tampered")')
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.manager.activate('1.1.0', **self.actions())
        self.assertEqual(self.calls, [])

    def test_modified_runtime_and_concurrent_updater_fail_before_service_actions(self):
        self.previous()
        with self.manager._lock(), self.assertRaises(BlockingIOError):
            self.manager.activate('1.1.0', **self.actions())
        runtime = self.root / '1.1.0/runtime/bin/python3'
        runtime.chmod(0o755)
        runtime.write_bytes(b'changed runtime')
        runtime.chmod(0o555)
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.manager.activate('1.1.0', **self.actions())
        self.assertEqual(self.calls, [])

    def test_success_backup_all_inventory_without_exposing_secrets(self):
        auth = self.data / 'auth.db'
        connection = sqlite3.connect(auth)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('CREATE TABLE users(value TEXT)')
        connection.execute("INSERT INTO users VALUES('committed WAL write')")
        connection.commit()
        self.inventory['databases']['auth'] = str(auth)
        self.manager = ota_updater.GatewayUpdater(self.root, self.key.public_key(), self.profile,
                                                self.inventory, b'r' * 32, runtime_source=self.runtime)
        self.previous()
        result = self.manager.activate('1.1.0', **self.actions())
        self.assertEqual(result['status'], 'COMMITTED')
        self.assertEqual(os.readlink(self.root / 'current'), '1.1.0')
        self.assertEqual(os.readlink(self.root / 'previous'), '1.0.0')
        backup = Path(result['backup'])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.secret.read_bytes(), backup.read_bytes())
        restored = ota_updater.inspect_backup(backup, b'r' * 32)
        self.assertIn('databases/registry.sqlite3', restored)
        recovered = self.home / 'auth-snapshot.db'
        recovered.write_bytes(restored['databases/auth.sqlite3'])
        with sqlite3.connect(recovered) as snapshot:
            self.assertEqual(snapshot.execute('SELECT value FROM users').fetchall(), [('committed WAL write',)])
        self.assertEqual(restored['files/master.key'], self.secret.read_bytes())
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'COMMITTED')

    def test_failed_health_rolls_back_software_and_preserves_new_writes(self):
        self.previous()
        def health():
            if os.readlink(self.root / 'current') == '1.1.0':
                with sqlite3.connect(self.db) as db:
                    db.execute("INSERT INTO events VALUES('new write')")
                return False
            return True
        result = self.manager.activate('1.1.0', **self.actions(health))
        self.assertEqual(result['status'], 'ROLLED_BACK')
        self.assertEqual(os.readlink(self.root / 'current'), '1.0.0')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT value FROM events').fetchall(), [('original',), ('new write',)])

    def test_unknown_database_and_schema_change_rejected(self):
        self.previous()
        with sqlite3.connect(self.data / 'unusual-store-name') as db:
            db.execute('CREATE TABLE auth(id)')
        with self.assertRaisesRegex(ValueError, 'unlisted database'):
            self.manager.activate('1.1.0', **self.actions())
        self.assertEqual(self.calls, [])

    def test_new_runtime_schema_change_needs_service_without_restoring_data(self):
        self.previous()
        def health():
            with sqlite3.connect(self.db) as db:
                db.execute('PRAGMA user_version=2')
            return True
        result = self.manager.activate('1.1.0', **self.actions(health))
        self.assertEqual(result['status'], 'NEEDS_SERVICE')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_recovery_at_every_durable_phase_and_callback_boundary(self):
        for boundary in ('PREPARED', 'STOPPED', 'SWITCHED', 'VERIFYING', 'stop', 'start', 'backup', 'previous', 'current', 'health'):
            with self.subTest(boundary=boundary):
                if (self.root / 'current').exists():
                    # Each case uses a fresh root, while the external data stays live.
                    self.root = self.home / ('releases-' + boundary)
                    self.root.mkdir(mode=0o700)
                    self.manager = ota_updater.GatewayUpdater(self.root, self.key.public_key(), self.profile,
                                                            self.inventory, b'r' * 32, runtime_source=self.runtime)
                self.previous()
                journal_write, pointer, backup = self.manager._write_journal, self.manager._pointer, self.manager._backup
                def crash_journal(record):
                    journal_write(record)
                    if record['status'] == boundary:
                        raise PowerCut()
                def crash_pointer(name, target):
                    pointer(name, target)
                    if name == boundary:
                        raise PowerCut()
                def stop():
                    if boundary == 'stop':
                        raise PowerCut()
                def start():
                    if boundary == 'start':
                        raise PowerCut()
                def crash_backup(*args):
                    backup(*args)
                    if boundary == 'backup':
                        raise PowerCut()
                def health():
                    if boundary == 'health':
                        raise PowerCut()
                    return True
                with patch.object(self.manager, '_write_journal', crash_journal), patch.object(self.manager, '_pointer', crash_pointer), patch.object(self.manager, '_backup', crash_backup):
                    with self.assertRaises(PowerCut):
                        self.manager.activate('1.1.0', stop=stop, start=start, health=health)
                self.assertEqual(self.manager.recover(**self.actions())['status'], 'ROLLED_BACK')
                self.assertEqual(os.readlink(self.root / 'current'), '1.0.0')
                before = list(self.calls)
                self.assertEqual(self.manager.recover(**self.actions())['status'], 'ROLLED_BACK')
                self.assertEqual(self.calls, before)

    def test_rollback_health_failure_remains_recoverable_and_modified_old_is_never_started(self):
        self.previous()
        result = self.manager.activate('1.1.0', **self.actions(lambda: False))
        self.assertEqual(result['status'], 'NEEDS_SERVICE')
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'ROLLED_BACK')
        journal = json.loads((self.root / 'activation.json').read_text())
        journal['status'] = 'VERIFYING'
        self.manager._write_journal(journal)
        entry = self.root / '1.0.0/gateway/main.py'
        entry.chmod(0o600)
        entry.write_bytes(b'# modified previous\n')
        self.calls.clear()
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'NEEDS_SERVICE')
        self.assertNotIn('start', self.calls)

    def test_boot_recovery_restores_pointer_before_gateway_starts_and_defers_health(self):
        self.previous()
        with self.assertRaises(PowerCut):
            self.manager.activate('1.1.0', stop=lambda: None, start=lambda: (_ for _ in ()).throw(PowerCut()), health=lambda: True)
        self.assertEqual(os.readlink(self.root / 'current'), '1.1.0')
        result = self.manager.prepare_boot_recovery()
        self.assertEqual(result['status'], 'RECOVERY_PENDING_HEALTH')
        self.assertEqual(os.readlink(self.root / 'current'), '1.0.0')
        self.assertEqual(self.manager.prepare_boot_recovery()['status'], 'RECOVERY_PENDING_HEALTH')
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'ROLLED_BACK')

    def test_committed_crash_keeps_new_release_and_recovery_itself_can_restart(self):
        self.previous()
        write = self.manager._write_journal
        def committed_cut(record):
            write(record)
            if record['status'] == 'COMMITTED':
                raise PowerCut()
        with patch.object(self.manager, '_write_journal', committed_cut), self.assertRaises(PowerCut):
            self.manager.activate('1.1.0', **self.actions())
        self.calls.clear()
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'COMMITTED')
        self.assertEqual(os.readlink(self.root / 'current'), '1.1.0')
        self.assertEqual(self.calls, [])
        record = json.loads((self.root / 'activation.json').read_text())
        record['status'] = 'VERIFYING'
        write(record)
        def recovery_cut(record):
            write(record)
            if record['status'] == 'RECOVERING':
                raise PowerCut()
        with patch.object(self.manager, '_write_journal', recovery_cut), self.assertRaises(PowerCut):
            self.manager.recover(**self.actions())
        self.assertEqual(self.manager.recover(**self.actions())['status'], 'ROLLED_BACK')
        self.assertEqual(os.readlink(self.root / 'current'), '1.0.0')

    def test_systemd_commands_and_health_cannot_be_chosen_by_artifact(self):
        with self.assertRaises(ValueError):
            ota_updater.systemd_actions('some-other.service', 'http://127.0.0.1/api/health')
        for url in ('http://example.com', 'https://127.0.0.1/api/health', 'http://localhost/api/health', 'http://user@127.0.0.1/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ota_updater.systemd_actions('smarthome-gateway.service', url)
        actions = ota_updater.systemd_actions('smarthome-gateway.service', 'http://127.0.0.1/api/health')
        with patch.object(ota_updater.subprocess, 'run') as command:
            actions['stop']()
            self.assertEqual(command.call_args.args[0], ['/usr/bin/systemctl', 'stop', 'smarthome-gateway.service'])
            self.assertNotIn('shell', command.call_args.kwargs)

    def test_loopback_health_requires_legacy_json_success_without_redirects(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302 if self.path == '/redirect' else 200)
                if self.path == '/redirect':
                    self.send_header('Location', '/ok')
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}' if self.path == '/ok' else b'<html>login</html>')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path, expected in (('/login', False), ('/redirect', False), ('/ok', True)):
                actions = ota_updater.systemd_actions('smarthome-gateway.service',
                    f'http://127.0.0.1:{server.server_port}{path}', health_seconds=0.1)
                self.assertEqual(actions['health'](), expected)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
