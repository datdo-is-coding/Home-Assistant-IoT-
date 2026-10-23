"""Comprehensive test suite for Device Removal & Permission Revocation (Milestone M2 - Task T07).

Covers:
1. Online remove: dispatches factory_reset/unpair, deletes from registry, unpublishes HA discovery,
   revokes all user grants in auth DB (G4 fix), records tombstone, broadcasts device_deleted.
2. Offline remove: records tombstone with offline_removed=True, notices physical button reset requirement,
   revokes auth grants (G4 fix), deletes from registry, does not crash, broadcasts device_deleted.
3. Re-link without proof rejected (G3 fix):
   - Tombstoned device sending old hello without factory reset / proof is rejected (device_removed_from_home).
   - Device reporting FACTORY_NEW matching existing node is rejected from auto-relink without setup proof.
4. SubBox remove: keeps child ActionBoxes in registry, marks them offline/reconnecting (needs_route_recovery).
5. WebServer HTTP API: POST /api/devices/{uid}/remove returns 200, 401, 403, 404.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

import config
config.BOOTSTRAP_PASSWORD = "test_bootstrap_pw_1234"

from auth_manager import AuthManager
from device_lifecycle import (
    DeviceLifecycleManager,
    Operation,
    OperationError,
    OperationKind,
    OperationState,
)
from registry_manager import RegistryManager
from web_server import WebServer


class TestDeviceRemoval(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_dev_rem_test_")
        self.registry_db_path = os.path.join(self.test_dir, "registry.db")
        self.auth_db_path = os.path.join(self.test_dir, "auth.db")

        self.auth = AuthManager(db_path=self.auth_db_path)
        self.registry = RegistryManager(db_path=self.registry_db_path)

        self.mqtt = Mock()
        self.mqtt.publish = AsyncMock(return_value=True)
        self.discovery = Mock()
        self.discovery.remove_ha_discovery_for_node = AsyncMock(return_value=True)

        self.events_broadcasted = []
        def _broadcast(event, data):
            self.events_broadcasted.append((event, data))
        self.broadcaster = _broadcast

        self.lifecycle = DeviceLifecycleManager(
            db_path=self.registry_db_path,
            registry=self.registry,
            mqtt=self.mqtt,
            discovery=self.discovery,
            broadcaster=self.broadcaster,
            auth=self.auth,
        )

        # Seed admin and member users
        with self.auth._get_db() as conn:
            self.admin_id = self.auth._create_user(conn, "admin_user", "password123456", role="admin")
            self.member_id = self.auth._create_user(conn, "member_user", "password123456", role="member")

        self.admin_user = {"id": self.admin_id, "username": "admin_user", "role": "admin"}
        self.member_user = {"id": self.member_id, "username": "member_user", "role": "member"}

        # Seed online and offline nodes
        self.registry.data["nodes"]["NODE_ONLINE_01"] = {
            "device_id": "NODE_ONLINE_01",
            "name": "Online Light",
            "room": "livingroom",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "capabilities": ["relay_2ch"],
            "channels": {"ch1": "light", "ch2": "fan"},
            "address": {"mac": "11:22:33:44:55:01"},
            "mac": "11:22:33:44:55:01",
        }
        self.registry.data["nodes"]["NODE_OFFLINE_01"] = {
            "device_id": "NODE_OFFLINE_01",
            "name": "Offline Socket",
            "room": "bedroom",
            "status": "offline",
            "state": "OFFLINE",
            "owner_epoch": 1,
            "capabilities": ["relay_2ch"],
            "channels": {"ch1": "socket"},
            "address": {"mac": "11:22:33:44:55:02"},
            "mac": "11:22:33:44:55:02",
        }
        self.registry.data["nodes"]["SUBBOX_DEV"] = {
            "device_id": "SUBBOX_DEV",
            "name": "SubBox Central",
            "room": "hall",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "model": "subbox_v1",
            "address": {"mac": "11:22:33:44:55:10"},
        }
        self.registry.data["nodes"]["CHILD_OF_SUBBOX"] = {
            "device_id": "CHILD_OF_SUBBOX",
            "name": "SubBox Child 1",
            "room": "hall",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "subbox_id": "SUBBOX_DEV",
            "address": {"mac": "11:22:33:44:55:20"},
        }
        self.registry.save()

        # Assign grants in auth DB
        self.auth.assign_device_to_user(self.member_id, "NODE_ONLINE_01")
        self.auth.assign_device_to_user(self.member_id, "NODE_OFFLINE_01")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_online_remove_dispatches_reset_deletes_registry_and_revokes_grants(self):
        """Online remove: dispatches factory reset/unpair, deletes from registry, unpublishes HA, revokes auth grants (G4)."""
        now = 1000.0

        # Verify grant exists before removal
        self.assertIn("NODE_ONLINE_01", self.auth.get_user_devices(self.member_id))

        op = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="NODE_ONLINE_01",
            kind=OperationKind.REMOVE_FROM_HOME,
            confirmation=True,
            now_sec=now,
        )

        self.assertEqual(op.state, OperationState.SUCCEEDED)
        self.assertTrue(op.metadata.get("auth_revoked"))
        self.assertFalse(op.metadata.get("offline_removed"))

        # Node removed from registry
        self.assertNotIn("NODE_ONLINE_01", self.registry.data["nodes"])

        # Auth grants completely wiped (G4 fix)
        self.assertNotIn("NODE_ONLINE_01", self.auth.get_user_devices(self.member_id))

        # HA discovery unpublish was triggered
        self.discovery.remove_ha_discovery_for_node.assert_called_with("NODE_ONLINE_01")

        # MQTT command dispatched to device
        mqtt_called = any(
            c.kwargs.get("payload", c.args[1] if len(c.args) > 1 else {}).get("cmd") == "factory_reset"
            for c in self.mqtt.publish.call_args_list
        )
        self.assertTrue(mqtt_called)

        # Tombstone recorded
        tomb = self.lifecycle.ledger.get_tombstone("NODE_ONLINE_01")
        self.assertIsNotNone(tomb)
        self.assertEqual(tomb["status"], "removed_from_home")
        self.assertEqual(tomb["offline_removed"], 0)

        # Broadcast event device_deleted
        broadcast_events = [e[0] for e in self.events_broadcasted]
        self.assertIn("device_deleted", broadcast_events)

    def test_offline_remove_records_tombstone_revokes_grants_and_requires_physical_button(self):
        """Offline remove: records tombstone, revokes auth grants (G4), does not crash, warns about physical reset."""
        now = 2000.0

        self.assertIn("NODE_OFFLINE_01", self.auth.get_user_devices(self.member_id))

        op = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="NODE_OFFLINE_01",
            kind=OperationKind.REMOVE_FROM_HOME,
            confirmation=True,
            now_sec=now,
        )

        self.assertEqual(op.state, OperationState.SUCCEEDED)
        self.assertTrue(op.metadata.get("offline_removed"))
        self.assertIn("physical button reset", op.metadata.get("notice", "").lower())

        # Removed from registry
        self.assertNotIn("NODE_OFFLINE_01", self.registry.data["nodes"])

        # Auth grants revoked (G4 fix)
        self.assertNotIn("NODE_OFFLINE_01", self.auth.get_user_devices(self.member_id))

        # Tombstone recorded with offline_removed=True
        tomb = self.lifecycle.ledger.get_tombstone("NODE_OFFLINE_01")
        self.assertIsNotNone(tomb)
        self.assertEqual(tomb["status"], "removed_from_home")
        self.assertEqual(tomb["offline_removed"], 1)
        self.assertIn("physical button reset", tomb["notice"].lower())

    def test_relink_without_proof_rejected_g3(self):
        """Re-link without proof is rejected (G3 fix):
        1. Hello from tombstoned device without commissioning is rejected.
        2. FACTORY_NEW matching existing node is rejected from auto-relink.
        """
        # Part 1: Offline remove a device
        self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="NODE_OFFLINE_01",
            kind=OperationKind.REMOVE_FROM_HOME,
            confirmation=True,
            now_sec=3000.0,
        )
        self.assertNotIn("NODE_OFFLINE_01", self.registry.data["nodes"])

        # Device comes back online sending legacy hello without having been reset / commissioned
        hello_payload = {
            "id": "NODE_OFFLINE_01",
            "mac": "11:22:33:44:55:02",
            "state": "READY",
        }
        res = self.registry.on_hello(hello_payload)
        self.assertEqual(res.get("action"), "rejected")
        self.assertEqual(res.get("error"), "device_removed_from_home")
        self.assertNotIn("NODE_OFFLINE_01", self.registry.data["nodes"])

        # Part 2: Device reporting FACTORY_NEW matching existing claimed node
        factory_hello = {
            "id": "NODE_ONLINE_01",
            "mac": "11:22:33:44:55:01",
            "state": "FACTORY_NEW",
        }
        res_factory = self.registry.on_hello(factory_hello)
        self.assertEqual(res_factory.get("action"), "rejected")
        self.assertEqual(res_factory.get("error"), "proof_required_for_factory_new")

    def test_tombstone_cleared_on_recommission_and_hello_accepted(self):
        """Xóa thiết bị -> tạo tombstone -> hello bị reject -> thiết bị reset vật lý và claim lại hợp lệ -> tombstone bị xóa -> hello READY được accept bình thường!"""
        now = 3000.0
        # 1. Device removed while offline
        self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="NODE_OFFLINE_01",
            kind=OperationKind.REMOVE_FROM_HOME,
            confirmation=True,
            now_sec=now,
        )
        self.assertNotIn("NODE_OFFLINE_01", self.registry.data["nodes"])
        tomb = self.lifecycle.ledger.get_tombstone("NODE_OFFLINE_01")
        self.assertIsNotNone(tomb)
        self.assertEqual(tomb["status"], "removed_from_home")

        # 2. Device hello before reset/claim is rejected because of tombstone
        res = self.registry.on_hello({
            "id": "NODE_OFFLINE_01",
            "mac": "11:22:33:44:55:02",
            "state": "READY",
        })
        self.assertEqual(res.get("action"), "rejected")
        self.assertEqual(res.get("error"), "device_removed_from_home")

        # 3. Device physically reset -> discovered as candidate in setup window
        self.lifecycle.add_candidate({
            "device_uid": "NODE_OFFLINE_01",
            "board_model": "actionbox_2ch",
            "board_revision": "v2.0",
            "protocol_version": 2,
            "capabilities": ["relay_2ch"],
            "channel_count": 2,
            "setup_proof": "valid_proof_123",
            "state": "unclaimed",
        }, now_sec=now + 10.0)
        self.registry.data["pending"]["NODE_OFFLINE_01"] = {
            "device_id": "NODE_OFFLINE_01",
            "mac": "11:22:33:44:55:02",
            "hardware": "actionbox_2ch",
        }

        # 4. Admin starts claim
        claim_op = self.lifecycle.start_claim(
            user=self.admin_user,
            request={
                "candidate_id": "NODE_OFFLINE_01",
                "room_id": "livingroom",
                "name": "Recommissioned Light",
                "setup_proof": "valid_proof_123",
            },
            now=now + 15.0,
        )
        self.assertIsNotNone(claim_op)

        # 5. Node ACK applied configuration
        asyncio.run(self.lifecycle.on_device_applied(
            device_uid="NODE_OFFLINE_01",
            owner_epoch=2,
            operation_id=claim_op.operation_id,
            config_revision=1,
            now_sec=now + 20.0,
        ))

        # 6. Tombstone is cleared!
        self.assertIsNone(self.lifecycle.ledger.get_tombstone("NODE_OFFLINE_01"))
        self.assertIn("NODE_OFFLINE_01", self.registry.data["nodes"])

        # 7. Device hello with state READY is now accepted!
        hello_res = self.registry.on_hello({
            "id": "NODE_OFFLINE_01",
            "mac": "11:22:33:44:55:02",
            "state": "READY",
            "cfg": 1,
            "owner_epoch": 2,
        })
        self.assertNotEqual(hello_res.get("action"), "rejected")
        self.assertEqual(hello_res.get("action"), "known")

    def test_subbox_removal_preserves_children_in_reconnecting_state(self):
        """Removing SubBox does NOT wipe child ActionBoxes; puts them in reconnecting / needs_route_recovery."""
        self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="SUBBOX_DEV",
            kind=OperationKind.REMOVE_FROM_HOME,
            confirmation=True,
            now_sec=4000.0,
        )

        # SubBox itself is removed
        self.assertNotIn("SUBBOX_DEV", self.registry.data["nodes"])

        # Child is STILL in registry
        self.assertIn("CHILD_OF_SUBBOX", self.registry.data["nodes"])
        child = self.registry.data["nodes"]["CHILD_OF_SUBBOX"]
        self.assertEqual(child["status"], "offline")
        self.assertEqual(child["state"], "reconnecting")
        self.assertEqual(child["security"]["route_status"], "needs_route_recovery")


class TestDeviceRemovalHttpApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_http_rem_test_")
        self.registry_db_path = os.path.join(self.test_dir, "registry.db")
        self.auth_db_path = os.path.join(self.test_dir, "auth.db")

        self.auth = AuthManager(db_path=self.auth_db_path)
        self.registry = RegistryManager(db_path=self.registry_db_path)

        self.mqtt = Mock()
        self.mqtt.publish = AsyncMock(return_value=True)
        self.discovery = Mock()
        self.discovery.remove_ha_discovery_for_node = AsyncMock(return_value=True)

        self.lifecycle = DeviceLifecycleManager(
            db_path=self.registry_db_path,
            registry=self.registry,
            mqtt=self.mqtt,
            discovery=self.discovery,
            broadcaster=None,
            auth=self.auth,
        )

        self.gateway = SimpleNamespace(
            auth=self.auth,
            registry=self.registry,
            lifecycle=self.lifecycle,
            mqtt=self.mqtt,
            discovery=self.discovery,
            broadcast_event=Mock(),
        )
        self.server = WebServer(self.gateway)

        # Seed users & tokens
        with self.auth._get_db() as conn:
            self.admin_id = self.auth._create_user(conn, "admin_user", "password123456", role="admin")
            self.member_id = self.auth._create_user(conn, "member_user", "password123456", role="member")

        res_adm = self.auth.login("admin_user", "password123456")
        self.admin_token = res_adm["token"]

        res_mem = self.auth.login("member_user", "password123456")
        self.member_token = res_mem["token"]

        # Seed device
        self.registry.data["nodes"]["NODE_FOR_HTTP_REMOVE"] = {
            "device_id": "NODE_FOR_HTTP_REMOVE",
            "name": "Remove Test Node",
            "room": "garage",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "capabilities": ["relay_1ch"],
            "channels": {"ch1": "light"},
        }
        self.registry.save()

        # Assign grant to member
        self.auth.assign_device_to_user(self.member_id, "NODE_FOR_HTTP_REMOVE")

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def _send_request(self, method: str, path: str, token: str | None = None, body: bytes = b""):
        req_headers = {
            "Host": "gateway.local",
            "Content-Length": str(len(body)),
        }
        if token:
            req_headers["Authorization"] = f"Bearer {token}"

        header_lines = "".join(f"{k}: {v}\r\n" for k, v in req_headers.items())
        raw_req = f"{method} {path} HTTP/1.1\r\n{header_lines}\r\n".encode() + body

        reader = asyncio.StreamReader()
        reader.feed_data(raw_req)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()

        await self.server._handle_client(reader, writer)
        raw_response = b"".join(call.args[0] for call in writer.write.call_args_list)
        if not raw_response:
            return 0, {}, {}

        parts = raw_response.split(b"\r\n\r\n", 1)
        resp_headers_raw = parts[0].decode()
        resp_body = parts[1] if len(parts) > 1 else b""
        status = int(resp_headers_raw.split("\r\n")[0].split()[1])

        parsed_json = {}
        if resp_body:
            try:
                parsed_json = json.loads(resp_body.decode())
            except Exception:
                pass
        return status, {}, parsed_json

    async def test_http_remove_non_admin_rejected_403(self):
        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_FOR_HTTP_REMOVE/remove",
            token=self.member_token,
        )
        self.assertEqual(status, 403)
        self.assertIn(data.get("error"), ("Insufficient permissions", "Admin privileges required"))

    async def test_http_remove_unknown_device_404(self):
        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_UNKNOWN/remove",
            token=self.admin_token,
        )
        self.assertEqual(status, 404)
        self.assertEqual(data.get("error_code"), "DEVICE_NOT_FOUND")

    async def test_http_remove_admin_success_200(self):
        self.assertIn("NODE_FOR_HTTP_REMOVE", self.auth.get_user_devices(self.member_id))

        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_FOR_HTTP_REMOVE/remove",
            token=self.admin_token,
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("device_id"), "NODE_FOR_HTTP_REMOVE")
        self.assertEqual(data.get("kind"), "remove_from_home")
        self.assertEqual(data.get("state"), "succeeded")

        # Node removed from registry
        self.assertNotIn("NODE_FOR_HTTP_REMOVE", self.registry.data["nodes"])

        # Auth grant revoked (G4 fix)
        self.assertNotIn("NODE_FOR_HTTP_REMOVE", self.auth.get_user_devices(self.member_id))


if __name__ == "__main__":
    unittest.main()
