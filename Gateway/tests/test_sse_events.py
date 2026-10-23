"""Comprehensive test suite for Gateway SSE /api/events endpoint and revision tracking (Milestone M3 - Task T12)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import config
config.BOOTSTRAP_PASSWORD = "test_bootstrap_pw_1234"

from auth_manager import AuthManager
from registry_manager import RegistryManager
from web_server import WebServer


class TestSseEventsHttpApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_sse_test_")
        self.registry_db_path = os.path.join(self.test_dir, "registry.db")
        self.auth_db_path = os.path.join(self.test_dir, "auth.db")

        self.auth = AuthManager(db_path=self.auth_db_path)
        self.registry = RegistryManager(db_path=self.registry_db_path)

        self.gateway = SimpleNamespace(
            auth=self.auth,
            registry=self.registry,
            mqtt=Mock(),
            discovery=Mock(),
        )
        self.server = WebServer(self.gateway)

        # Create admin and member
        with self.auth._get_db() as conn:
            self.admin_id = self.auth._create_user(conn, "admin_user", "password123456", role="admin")
            self.member_id = self.auth._create_user(conn, "member_user", "password123456", role="member")

        res_adm = self.auth.login("admin_user", "password123456")
        self.admin_token = res_adm["token"]

        res_mem = self.auth.login("member_user", "password123456")
        self.member_token = res_mem["token"]

        # Seed devices
        self.registry.data["nodes"]["NODE_ADMIN_ONLY"] = {
            "device_id": "NODE_ADMIN_ONLY",
            "name": "Admin Node",
            "room": "server_room",
            "status": "online",
            "relay_state": [0, 0],
        }
        self.registry.data["nodes"]["NODE_SHARED"] = {
            "device_id": "NODE_SHARED",
            "name": "Shared Node",
            "room": "living_room",
            "status": "online",
            "relay_state": [0, 0],
        }
        self.registry.save()

        # Grant member access to NODE_SHARED only
        self.auth.assign_device_to_user(self.member_id, "NODE_SHARED")

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_broadcast_event_increments_revision_and_formats_sse(self):
        self.assertEqual(self.server._event_revision, 0)
        q = asyncio.Queue()
        self.server.sse_queues[q] = {"id": self.admin_id, "username": "admin_user", "role": "admin"}

        data = {"node_id": "NODE_SHARED", "state": "on"}
        self.server.broadcast_event("relay_state", data)

        self.assertEqual(self.server._event_revision, 1)
        self.assertEqual(data["revision"], 1)

        msg = q.get_nowait()
        self.assertIn("id: 1\n", msg)
        self.assertIn("event: relay_state\n", msg)
        self.assertIn('"revision": 1', msg)
        self.assertIn('"node_id": "NODE_SHARED"', msg)

    def test_broadcast_event_non_admin_filtering(self):
        q_admin = asyncio.Queue()
        q_member = asyncio.Queue()
        self.server.sse_queues[q_admin] = {"id": self.admin_id, "username": "admin_user", "role": "admin"}
        self.server.sse_queues[q_member] = {"id": self.member_id, "username": "member_user", "role": "member"}

        # Event for NODE_ADMIN_ONLY -> member should NOT receive it
        self.server.broadcast_event("node_status", {"node_id": "NODE_ADMIN_ONLY", "status": "online"})
        self.assertFalse(q_admin.empty())
        self.assertTrue(q_member.empty())

        q_admin.get_nowait()

        # Event for NODE_SHARED -> both admin and member should receive it
        self.server.broadcast_event("node_status", {"node_id": "NODE_SHARED", "status": "offline"})
        self.assertFalse(q_admin.empty())
        self.assertFalse(q_member.empty())

    async def test_http_events_unauthorized_without_token(self):
        req_headers = {
            "Host": "gateway.local",
            "Content-Length": "0",
        }
        header_lines = "".join(f"{k}: {v}\r\n" for k, v in req_headers.items())
        raw_req = f"GET /api/events HTTP/1.1\r\n{header_lines}\r\n".encode()

        reader = asyncio.StreamReader()
        reader.feed_data(raw_req)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()

        await self.server._handle_client(reader, writer)
        raw_response = b"".join(call.args[0] for call in writer.write.call_args_list)

        self.assertIn(b"401 Unauthorized", raw_response)


if __name__ == "__main__":
    unittest.main()
