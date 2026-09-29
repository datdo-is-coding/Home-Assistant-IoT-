"""
AETHERIA OS — Authentication & Device Access Scoping Manager
Multi-tenant SQLite database for users, sessions, and device ownership.
"""

import sqlite3
import hashlib
import secrets
import time
import logging
import os
from typing import Optional, Dict, Any, List

import config

logger = logging.getLogger("auth_manager")

class AuthManager:
    """Manages user accounts, credentials, sessions, and device ownership."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or getattr(config, "AUTH_DB", "/home/pi4/smarthome/auth.db")
        # Local fallback if path does not exist
        if not os.path.exists(os.path.dirname(self.db_path)):
            try:
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            except Exception:
                self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "auth.db")
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.login_attempts = {}
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    fullname TEXT,
                    role TEXT DEFAULT 'admin',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_devices (
                    user_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    is_owner INTEGER DEFAULT 1,
                    can_control INTEGER DEFAULT 1,
                    assigned_at REAL NOT NULL,
                    PRIMARY KEY (user_id, node_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # Retire the previously shipped default account without deleting ownership.
            old = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
            if old and self._verify_password("admin123", old["salt"], old["password_hash"]):
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (old["id"],))
                conn.execute("DELETE FROM api_keys WHERE user_id = ?", (old["id"],))
                replacement = config.BOOTSTRAP_PASSWORD
                if len(replacement) < 12 or replacement == "admin123":
                    raise RuntimeError("Set BOOTSTRAP_PASSWORD (12+ characters) to retire the default admin")
                digest, salt = self._hash_password(replacement)
                conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (digest, salt, old["id"]))
            if not conn.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
                if len(config.BOOTSTRAP_PASSWORD) < 12:
                    raise RuntimeError("First startup requires BOOTSTRAP_PASSWORD (12+ characters)")
                self._create_user(conn, config.BOOTSTRAP_USERNAME, config.BOOTSTRAP_PASSWORD, role="admin")

    def _hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        if not salt:
            salt = secrets.token_hex(16)
        # ponytail: scrypt instead of pbkdf2 as requested, minimal config
        h = hashlib.scrypt(password.encode('utf-8'), salt=salt.encode('utf-8'), n=16384, r=8, p=1).hex()
        return "scrypt$" + h, salt

    def _verify_password(self, password: str, salt: str, stored: str) -> bool:
        if stored.startswith("scrypt$"):
            return secrets.compare_digest(self._hash_password(password, salt)[0], stored)
        if len(stored) == 128:  # Unversioned scrypt from the previous local revision.
            return secrets.compare_digest(self._hash_password(password, salt)[0][7:], stored)
        legacy = hashlib.pbkdf2_hmac("sha256", (password + salt).encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(legacy, stored)

    def _create_user(self, conn: sqlite3.Connection, username: str, password: str, fullname: str = "", role: str = "member") -> int:
        h, salt = self._hash_password(password)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, fullname, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username.strip().lower(), h, salt, fullname.strip() or username, role, now)
        )
        return cur.lastrowid

    def register(self, username: str, password: str, fullname: str = "", bootstrap_password: str = "") -> Dict[str, Any]:
        """Register a new user (bootstrap admin on first run, locked afterwards)."""
        return {"success": False, "error": "Public registration is disabled; provision accounts locally."}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return session token."""
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 128 or len(password) > 1024:
            return {"success": False, "error": "Invalid credentials"}
        u = username.strip().lower()
        now = time.time()

        self.login_attempts = {k: [t for t in v if now - t < 900] for k, v in self.login_attempts.items() if any(now - t < 900 for t in v)}
        if u not in self.login_attempts and len(self.login_attempts) >= 1024:
            return {"success": False, "error": "Too many login attempts", "rate_limited": True}
        attempts = self.login_attempts.get(u, [])
        attempts = [t for t in attempts if now - t < 900]
        if len(attempts) >= 5:
            self.login_attempts[u] = attempts
            return {"success": False, "error": "Bạn đã đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.", "rate_limited": True}

        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (u,))
            row = cur.fetchone()
            if not row:
                attempts.append(now)
                self.login_attempts[u] = attempts
                return {"success": False, "error": "Tài khoản hoặc mật khẩu không chính xác"}

            if not self._verify_password(password, row["salt"], row["password_hash"]):
                attempts.append(now)
                self.login_attempts[u] = attempts
                return {"success": False, "error": "Tài khoản hoặc mật khẩu không chính xác"}

            if u in self.login_attempts:
                del self.login_attempts[u]

            if not row["password_hash"].startswith("scrypt$"):
                digest, salt = self._hash_password(password)
                conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (digest, salt, row["id"]))

            # Expired sessions are removed at each successful login.
            token = secrets.token_hex(32)
            now = time.time()
            expires = now + config.SESSION_TTL_SECONDS
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, row["id"], now, expires)
            )

            # Generate or retrieve permanent API key for Mobile App
            api_key = self.get_or_create_api_key(row["id"], conn=conn)

            user_info = {
                "id": row["id"],
                "username": row["username"],
                "fullname": row["fullname"],
                "role": row["role"]
            }
            logger.info(f"🔑 User '{u}' logged in successfully (API key ready)")
            return {"success": True, "token": token, "api_key": api_key, "user": user_info}

    def get_or_create_api_key(self, user_id: int, conn: Optional[sqlite3.Connection] = None) -> str:
        """Get or create permanent API key for user."""
        if conn is not None:
            return self._get_or_create_api_key_impl(conn, user_id)
        with self._get_conn() as c:
            return self._get_or_create_api_key_impl(c, user_id)

    def _get_or_create_api_key_impl(self, conn: sqlite3.Connection, user_id: int) -> str:
        cur = conn.execute("SELECT key FROM api_keys WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            return row["key"]
        new_key = f"aeth_{secrets.token_hex(20)}"
        now = time.time()
        conn.execute("INSERT INTO api_keys (key, user_id, name, created_at) VALUES (?, ?, 'Mobile App', ?)",
                     (new_key, user_id, now))
        return new_key

    def authenticate_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Validate token or API key and return user info."""
        if not token:
            return None
        t = token.strip()
        now = time.time()
        with self._get_conn() as conn:
            # 1. Check temporary sessions
            cur = conn.execute("""
                SELECT u.id, u.username, u.fullname, u.role
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ? AND s.expires_at > ?
            """, (t, now))
            row = cur.fetchone()
            if row:
                return dict(row)

            # 2. Check permanent API keys
            cur_key = conn.execute("""
                SELECT u.id, u.username, u.fullname, u.role
                FROM api_keys k
                JOIN users u ON k.user_id = u.id
                WHERE k.key = ?
            """, (t,))
            row_key = cur_key.fetchone()
            if row_key:
                return dict(row_key)

        return None

    def logout(self, token: str) -> bool:
        """Delete session token."""
        if not token:
            return True
        with self._get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token.strip(),))
        return True

    def get_user_devices(self, user_id: int) -> List[str]:
        """Get list of node IDs assigned to a user."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT node_id FROM user_devices WHERE user_id = ?", (user_id,))
            return [r["node_id"] for r in cur.fetchall()]

    def assign_device_to_user(self, user_id: int, node_id: str) -> bool:
        """Assign ownership of a device node to a user."""
        now = time.time()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_devices (user_id, node_id, is_owner, can_control, assigned_at)
                VALUES (?, ?, 1, 1, ?)
            """, (user_id, node_id, now))
        return True

    def filter_nodes(self, user: Optional[Dict[str, Any]], all_nodes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter nodes dictionary based on user permissions.
        Admin sees all nodes. Regular members see assigned nodes only.
        """
        if not user:
            return {}
        if user.get("role") == "admin":
            return all_nodes

        user_id = user.get("id")
        allowed_ids = set(self.get_user_devices(user_id))
        
        # If user has no specific devices assigned yet, leave empty (unassigned user)
        if not allowed_ids:
            return {}

        return {k: v for k, v in all_nodes.items() if k in allowed_ids}
