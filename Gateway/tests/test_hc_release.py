import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from gateway.core_v1.database import Database
from gateway.core_v1.release import ReleaseManager, backup, restore, verify


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key = ed25519.Ed25519PrivateKey.generate()
        self.manager = ReleaseManager(self.root, self.key.public_key())
        self.db = Database(self.root / 'core.db', b'm' * 32)
        self.db.db.execute("INSERT INTO factory_devices VALUES(?,?,?,?,?,?)", (
            'HC-001122334455', 'ACTION_BOX', 'HC-A1', self.db.cipher.encrypt(b'd' * 32), 'setup-hash', 0))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def package(self, version='1.1.0', unsafe=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            info = tarfile.TarInfo(unsafe or 'gateway/core_v1/__main__.py')
            content = b'print("Home Competition")\n'
            info.size = len(content)
            if unsafe == 'link':
                info.type = tarfile.SYMTYPE
                info.linkname = '/tmp/escape'
            archive.addfile(info, io.BytesIO(content))
        artifact = stream.getvalue()
        manifest = json.dumps(dict(format=1, target='home-competition-gateway', version=version,
                                   size=len(artifact), sha256=hashlib.sha256(artifact).hexdigest(),
                                   schema_min=1, schema_max=1)).encode()
        paths = [self.root / (version + suffix) for suffix in ('.tgz', '.json', '.sig')]
        for path, content in zip(paths, (artifact, manifest, self.key.sign(manifest))):
            path.write_bytes(content)
        return paths

    def test_verify_ed25519_and_p256_reject_bad_hash_and_signature(self):
        paths = self.package()
        artifact, manifest, signature = (p.read_bytes() for p in paths)
        self.assertEqual(verify(artifact, manifest, signature, self.key.public_key())['version'], '1.1.0')
        with self.assertRaises(ValueError):
            verify(artifact + b'x', manifest, signature, self.key.public_key())
        with self.assertRaises(InvalidSignature):
            verify(artifact, manifest, bytes(64), self.key.public_key())
        key = ec.generate_private_key(ec.SECP256R1())
        verify(artifact, manifest, key.sign(manifest, ec.ECDSA(hashes.SHA256())), key.public_key())

    def test_safe_staging_and_reject_traversal_links(self):
        self.assertTrue((self.manager.stage(*self.package()) / 'gateway/core_v1/__main__.py').is_file())
        for unsafe in ('../../escape', '/tmp/escape', 'link', 'a/../escape'):
            with self.assertRaises(ValueError):
                self.manager.stage(*self.package('1.2.0', unsafe=unsafe))
        self.assertFalse((self.root / '1.2.0').exists())

    def test_encrypted_consistent_backup_and_new_directory_restore(self):
        bundle = self.root / 'backup.enc'
        backup(self.root / 'core.db', b'm' * 32, bundle, b'r' * 32)
        self.assertNotIn(b'm' * 32, bundle.read_bytes())
        self.assertEqual(bundle.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(InvalidToken):
            restore(bundle, b'x' * 32, self.root / 'wrong')
        restored = restore(bundle, b'r' * 32, self.root / 'restored')
        self.assertEqual((restored / 'master.key').read_bytes(), b'm' * 32)
        with sqlite3.connect(restored / 'core.db') as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('SELECT count(*) FROM factory_devices').fetchone()[0], 1)
        with self.assertRaises(FileExistsError):
            restore(bundle, b'r' * 32, restored)
        with self.assertRaises(InvalidToken):
            backup(self.root / 'core.db', b'x' * 32, self.root / 'bad.enc', b'r' * 32)
        self.assertFalse((self.root / 'bad.enc').exists())

    def activate(self, health):
        return self.manager.activate('1.1.0', self.root / 'core.db', b'm' * 32, b'r' * 32,
                                     self.root / 'before.enc', stop=lambda: self.calls.append('stop'),
                                     start=lambda: self.calls.append('start'), health=health)

    def previous(self):
        self.manager.stage(*self.package())
        (self.root / '1.0.0').mkdir()
        (self.root / 'current').symlink_to('1.0.0')
        self.calls = []

    def test_restart_health_and_software_rollback_preserve_data(self):
        self.previous()
        def health():
            return os.readlink(self.root / 'current') == '1.0.0'
        with self.assertRaisesRegex(RuntimeError, 'new release failed'):
            self.activate(health)
        self.assertEqual(os.readlink(self.root / 'current'), '1.0.0')
        self.assertEqual(self.calls, ['stop', 'start', 'stop', 'start'])
        self.assertTrue((self.root / 'before.enc').is_file())
        self.assertEqual(self.db.integrity(), 'ok')

    def test_success_and_tampered_stage_fails_before_service_stop(self):
        self.previous()
        entry = self.root / '1.1.0/gateway/core_v1/__main__.py'
        original = entry.read_bytes()
        entry.write_text('raise RuntimeError("tampered")')
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.activate(lambda: True)
        self.assertEqual(self.calls, [])
        entry.write_bytes(original)
        self.assertEqual(self.activate(lambda: True)['status'], 'SUCCEEDED')
        self.assertEqual(os.readlink(self.root / 'current'), '1.1.0')
