"""SQLite migrations and encrypted credential storage; no default master key."""
import base64
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from cryptography.fernet import Fernet

class Database:
    def __init__(self, path, master_key):
        if len(master_key) != 32:
            raise ValueError('master key must be 32 bytes')
        self.cipher = Fernet(base64.urlsafe_b64encode(master_key))
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise RuntimeError('database schema newer than this software')
        if version == 0:
            sql = (Path(__file__).parent / 'migrations/001_initial.sql').read_text()
            self.db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=1;\nCOMMIT;')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield self.db
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def close(self):
        self.db.close()

    def integrity(self):
        result = self.db.execute('PRAGMA integrity_check').fetchone()[0]
        if self.db.execute('PRAGMA foreign_key_check').fetchone():
            return 'foreign key violation'
        return result

    def backup(self, path):

        with open(path, 'xb'):
            pass
        Path(path).chmod(0o600)
        with sqlite3.connect(path) as target:
            self.db.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup integrity failed')
