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

            # Seed default admin user if none exists
            cur = conn.execute("SELECT COUNT(*) as cnt FROM users")
            if cur.fetchone()["cnt"] == 0:
                self._create_user(conn, "admin", "admin123", fullname="Chủ Hộ (Admin)", role="admin")
                logger.info("👤 Initialized default admin account: 'admin' (password: admin123)")

    def _hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        if not salt:
            salt = secrets.token_hex(16)
        salted = (password + salt).encode('utf-8')
        h = hashlib.pbkdf2_hmac('sha256', salted, salt.encode('utf-8'), 100000).hex()
        return h, salt

    def _create_user(self, conn: sqlite3.Connection, username: str, password: str, fullname: str = "", role: str = "member") -> int:
        h, salt = self._hash_password(password)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, fullname, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username.strip().lower(), h, salt, fullname.strip() or username, role, now)
        )
        return cur.lastrowid

    def register(self, username: str, password: str, fullname: str = "") -> Dict[str, Any]:
        """Register a new user."""
        u = username.strip().lower()
        if not u or len(u) < 3:
            return {"success": False, "error": "Tên đăng nhập phải có ít nhất 3 ký tự"}
        if not password or len(password) < 6:
            return {"success": False, "error": "Mật khẩu phải có ít nhất 6 ký tự"}

        try:
            with self._get_conn() as conn:
                cur = conn.execute("SELECT id FROM users WHERE username = ?", (u,))
                if cur.fetchone():
                    return {"success": False, "error": "Tên đăng nhập đã tồn tại"}

                uid = self._create_user(conn, u, password, fullname=fullname, role="member")
                # Automatically grant permission to current online nodes for new user
                logger.info(f"✨ Registered new user: {u} (id={uid})")
                return {"success": True, "user_id": uid, "username": u}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return session token."""
        u = username.strip().lower()
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (u,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": "Tài khoản hoặc mật khẩu không chính xác"}

            h, _ = self._hash_password(password, row["salt"])
            if h != row["password_hash"]:
                return {"success": False, "error": "Tài khoản hoặc mật khẩu không chính xác"}

            # Generate secure session token (valid 14 days)
            token = secrets.token_hex(32)
            now = time.time()
            expires = now + 14 * 86400

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
        if not user or user.get("role") == "admin":
            return all_nodes

        user_id = user.get("id")
        allowed_ids = set(self.get_user_devices(user_id))
        
        # If user has no specific devices assigned yet, grant access to master or leave empty
        if not allowed_ids:
            return {k: v for k, v in all_nodes.items() if k == "esp32s3_master"}

        return {k: v for k, v in all_nodes.items() if k in allowed_ids}
