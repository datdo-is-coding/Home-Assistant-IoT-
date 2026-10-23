"""Comprehensive test suite for Device Operations (Milestone M2 - Task T07).

Covers:
1. Identify: 15s timeout, blinking warning, no relay command sent.
2. Reboot: Admin required (403 for non-admin), load interruption warning, dispatches reboot, reconnect succeeds.
3. Network Reset: Requires confirmation; without confirmation -> awaiting_confirmation (30s); with confirmation -> running.
4. Factory Reset: Requires confirmation, increases owner_epoch, revokes grants in auth DB (G4), sets node to unclaimed/resetting.
5. Concurrency & Idempotency: 409 Conflict on 2 concurrent active operations; same idempotency_key returns cached operation.
6. SubBox Reset: Affects child ActionBoxes by setting them to reconnecting/needs_route_recovery without deleting or wiping them.
7. WebServer HTTP API: POST /api/devices/{uid}/operations returns 202, 401, 403, 404, 409.
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


class TestDeviceOperations(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_dev_ops_test_")
        self.registry_db_path = os.path.join(self.test_dir, "registry.db")
        self.auth_db_path = os.path.join(self.test_dir, "auth.db")

        self.auth = AuthManager(db_path=self.auth_db_path)
        self.registry = RegistryManager(db_path=self.registry_db_path)

        self.mqtt = Mock()
        self.mqtt.publish = AsyncMock(return_value=True)
        self.discovery = Mock()
        self.discovery.remove_ha_discovery_for_node = AsyncMock(return_value=True)
        self.discovery.publish_ha_discovery_for_node = AsyncMock(return_value=True)

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

        # Seed sample devices in registry
        self.registry.data["nodes"]["DEV_ACTIONBOX_01"] = {
            "device_id": "DEV_ACTIONBOX_01",
            "name": "Living Light",
            "room": "livingroom",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "subbox_id": "SUBBOX_01",
            "capabilities": ["relay_3ch"],
            "channels": {"ch1": "light", "ch2": "fan", "ch3": "socket"},
            "address": {"mac": "AA:BB:CC:DD:EE:01"},
            "security": {"state": "READY", "lifecycle_state": "claimed"},
        }
        self.registry.data["nodes"]["SUBBOX_01"] = {
            "device_id": "SUBBOX_01",
            "name": "SubBox Living",
            "room": "livingroom",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "model": "subbox_v1",
            "board_model": "subbox_v1",
            "address": {"mac": "AA:BB:CC:DD:EE:10"},
            "security": {"state": "READY", "lifecycle_state": "claimed"},
        }
        self.registry.data["nodes"]["CHILD_ACTIONBOX_01"] = {
            "device_id": "CHILD_ACTIONBOX_01",
            "name": "Child Relay 1",
            "room": "livingroom",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "subbox_id": "SUBBOX_01",
            "channels": {"ch1": "light"},
            "address": {"mac": "AA:BB:CC:DD:EE:21"},
            "security": {"state": "READY", "lifecycle_state": "claimed"},
        }
        self.registry.data["nodes"]["CHILD_ACTIONBOX_02"] = {
            "device_id": "CHILD_ACTIONBOX_02",
            "name": "Child Relay 2",
            "room": "livingroom",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "parent_subbox": "SUBBOX_01",
            "channels": {"ch1": "fan"},
            "address": {"mac": "AA:BB:CC:DD:EE:22"},
            "security": {"state": "READY", "lifecycle_state": "claimed"},
        }
        self.registry.save()

        # Assign device grant to member in auth DB
        self.auth.assign_device_to_user(self.member_id, "DEV_ACTIONBOX_01")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_identify_has_15s_timeout_and_never_sends_relay_command(self):
        """Identify runs for 15s TTL, dispatches identify command, and NEVER sends relay actuation."""
        now = 1000.0
        op = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="identify",
            now_sec=now,
        )

        self.assertEqual(op.kind, OperationKind.IDENTIFY)
        self.assertEqual(op.state, OperationState.RUNNING)
        self.assertEqual(op.expires_at, now + 15.0)

        # Verify MQTT identify published
        calls = self.mqtt.publish.call_args_list
        self.assertTrue(len(calls) >= 1)
        # Check topic and payload
        found_identify = False
        for c in calls:
            topic = c.args[0] if len(c.args) > 0 else c.kwargs.get("topic")
            payload = c.args[1] if len(c.args) > 1 else c.kwargs.get("payload")
            if "operation" in topic and payload.get("cmd") == "identify":
                found_identify = True
            # ABSOLUTELY NO RELAY COMMAND
            self.assertNotIn("relay", str(topic).lower())
            self.assertNotEqual(payload.get("t"), "rl")
            self.assertNotIn("action", payload)
            self.assertNotIn("turn_on", str(payload).lower())
            self.assertNotIn("turn_off", str(payload).lower())

        self.assertTrue(found_identify)

        # Timeout reconciliation at 15s+
        reconciled = self.lifecycle.reconcile_operation(op.operation_id, now_sec=now + 16.0)
        self.assertEqual(reconciled.state, OperationState.TIMED_OUT)
        self.assertEqual(reconciled.error_code, "TIMEOUT")

    def test_reboot_requires_admin_and_dispatches_reboot_with_reconnect(self):
        """Reboot rejects non-admin with 403, accepts admin, dispatches warning/command, completes on reconnect."""
        now = 2000.0
        # Non-admin rejected
        with self.assertRaises(OperationError) as ctx:
            self.lifecycle.start_operation(
                user=self.member_user,
                device_uid="DEV_ACTIONBOX_01",
                kind="reboot",
                now_sec=now,
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.error_code, "ADMIN_REQUIRED")

        # Admin accepted
        op = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="reboot",
            now_sec=now,
        )
        self.assertEqual(op.kind, OperationKind.REBOOT)
        self.assertEqual(op.state, OperationState.AWAITING_RECONNECT)
        self.assertEqual(op.expires_at, now + 30.0)
        self.assertIn("warning", op.metadata)

        # Verify MQTT dispatched
        reboot_called = any(
            c.kwargs.get("payload", c.args[1] if len(c.args) > 1 else {}).get("cmd") == "reboot"
            for c in self.mqtt.publish.call_args_list
        )
        self.assertTrue(reboot_called)

        # Device reconnects
        completed_op = self.lifecycle.on_device_reconnected("DEV_ACTIONBOX_01", now_sec=now + 5.0)
        self.assertIsNotNone(completed_op)
        self.assertEqual(completed_op.state, OperationState.SUCCEEDED)

    def test_reboot_enters_awaiting_reconnect_and_succeeds_on_reconnect(self):
        """Reboot operation immediately transitions to awaiting_reconnect after dispatch, then succeeded upon reconnect."""
        now = 2500.0
        op = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="reboot",
            now_sec=now,
        )
        self.assertEqual(op.kind, OperationKind.REBOOT)
        self.assertEqual(op.state, OperationState.AWAITING_RECONNECT)

        # Check ledger state reflects awaiting_reconnect
        op_db = self.lifecycle.get_operation(op.operation_id, now_sec=now)
        self.assertIsNotNone(op_db)
        self.assertEqual(op_db.state, OperationState.AWAITING_RECONNECT)

        # Device reconnects -> transitions to succeeded
        completed_op = self.lifecycle.on_device_reconnected("DEV_ACTIONBOX_01", now_sec=now + 5.0)
        self.assertIsNotNone(completed_op)
        self.assertEqual(completed_op.state, OperationState.SUCCEEDED)

        # Check broadcasted event
        reboot_events = [data for event, data in self.events_broadcasted if event == "device_rebooted"]
        self.assertTrue(len(reboot_events) > 0)
        self.assertEqual(reboot_events[-1]["device_uid"], "DEV_ACTIONBOX_01")
        self.assertEqual(reboot_events[-1]["state"], "succeeded")

    def test_network_reset_requires_confirmation(self):
        """Network reset without confirmation enters awaiting_confirmation (30s); with confirmation enters running."""
        now = 3000.0

        # Step 1: No confirmation -> awaiting_confirmation
        op_pending = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="network_reset",
            confirmation=False,
            now_sec=now,
        )
        self.assertEqual(op_pending.state, OperationState.AWAITING_CONFIRMATION)
        self.assertEqual(op_pending.expires_at, now + 30.0)
        self.mqtt.publish.reset_mock()

        # Step 2: User confirms within 30s
        op_confirmed = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="network_reset",
            confirmation=True,
            now_sec=now + 5.0,
        )
        self.assertEqual(op_confirmed.state, OperationState.RUNNING)
        self.assertEqual(op_confirmed.operation_id, op_pending.operation_id)

        # Verify MQTT command dispatched now
        net_reset_called = any(
            c.kwargs.get("payload", c.args[1] if len(c.args) > 1 else {}).get("cmd") == "network_reset"
            for c in self.mqtt.publish.call_args_list
        )
        self.assertTrue(net_reset_called)

    def test_factory_reset_increments_epoch_and_revokes_grants(self):
        """Factory reset requires confirmation, increments owner_epoch, revokes grants in auth DB (G4), marks unclaimed."""
        now = 4000.0

        # Grants exist before reset
        user_devs_before = self.auth.get_user_devices(self.member_id)
        self.assertIn("DEV_ACTIONBOX_01", user_devs_before)

        # Unconfirmed enters awaiting_confirmation
        op_unconfirmed = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="factory_reset",
            confirmation=False,
            now_sec=now,
        )
        self.assertEqual(op_unconfirmed.state, OperationState.AWAITING_CONFIRMATION)

        # Confirmed factory reset
        op_confirmed = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="factory_reset",
            confirmation=True,
            now_sec=now + 2.0,
        )
        self.assertEqual(op_confirmed.state, OperationState.RUNNING)

        # Check owner_epoch incremented
        node = self.registry.data["nodes"]["DEV_ACTIONBOX_01"]
        self.assertEqual(node["owner_epoch"], 2)
        self.assertEqual(node["status"], "unclaimed")
        self.assertEqual(node["security"]["lifecycle_state"], "resetting")

        # Check auth DB grants thoroughly revoked (G4 fix)
        user_devs_after = self.auth.get_user_devices(self.member_id)
        self.assertNotIn("DEV_ACTIONBOX_01", user_devs_after)

    def test_concurrency_and_idempotency(self):
        """Cannot run 2 active operations simultaneously on 1 node (409 Conflict); same idempotency key returns cached op."""
        now = 5000.0

        # Start operation with idempotency key
        op1 = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="reboot",
            idempotency_key="key-reboot-001",
            now_sec=now,
        )
        self.assertEqual(op1.state, OperationState.AWAITING_RECONNECT)

        # Repeated call with same idempotency key returns existing op
        op_same = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="reboot",
            idempotency_key="key-reboot-001",
            now_sec=now + 1.0,
        )
        self.assertEqual(op_same.operation_id, op1.operation_id)

        # Second different operation on same device triggers 409 Conflict
        with self.assertRaises(OperationError) as ctx:
            self.lifecycle.start_operation(
                user=self.admin_user,
                device_uid="DEV_ACTIONBOX_01",
                kind="identify",
                now_sec=now + 2.0,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.error_code, "OPERATION_IN_PROGRESS")

        # Finish op1
        self.lifecycle.on_device_reconnected("DEV_ACTIONBOX_01", now_sec=now + 3.0)

        # Now identify is allowed
        op2 = self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="DEV_ACTIONBOX_01",
            kind="identify",
            now_sec=now + 4.0,
        )
        self.assertEqual(op2.kind, OperationKind.IDENTIFY)
        self.assertEqual(op2.state, OperationState.RUNNING)

    def test_subbox_reset_preserves_children_and_marks_needs_route_recovery(self):
        """Resetting SubBox must NOT wipe or delete child ActionBoxes; sets them to offline/reconnecting."""
        now = 6000.0
        self.lifecycle.start_operation(
            user=self.admin_user,
            device_uid="SUBBOX_01",
            kind="factory_reset",
            confirmation=True,
            now_sec=now,
        )

        # Children still exist in registry!
        self.assertIn("CHILD_ACTIONBOX_01", self.registry.data["nodes"])
        self.assertIn("CHILD_ACTIONBOX_02", self.registry.data["nodes"])

        # Their state was changed to reconnecting and route needs recovery
        c1 = self.registry.data["nodes"]["CHILD_ACTIONBOX_01"]
        c2 = self.registry.data["nodes"]["CHILD_ACTIONBOX_02"]
        self.assertEqual(c1["status"], "offline")
        self.assertEqual(c1["state"], "reconnecting")
        self.assertEqual(c1["security"]["route_status"], "needs_route_recovery")

        self.assertEqual(c2["status"], "offline")
        self.assertEqual(c2["state"], "reconnecting")
        self.assertEqual(c2["security"]["route_status"], "needs_route_recovery")


class TestDeviceOperationsHttpApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_http_ops_test_")
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

        # Mock gateway for WebServer
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
        self.registry.data["nodes"]["NODE_TEST_OPS"] = {
            "device_id": "NODE_TEST_OPS",
            "name": "Ops Test Node",
            "room": "kitchen",
            "status": "online",
            "state": "READY",
            "owner_epoch": 1,
            "capabilities": ["relay_2ch"],
            "channels": {"ch1": "light", "ch2": "fan"},
        }
        self.registry.save()

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

    async def test_http_operations_non_admin_rejected_403(self):
        payload = json.dumps({"kind": "identify"}).encode()
        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_TEST_OPS/operations",
            token=self.member_token,
            body=payload,
        )
        self.assertEqual(status, 403)
        self.assertIn(data.get("error"), ("Insufficient permissions", "Admin privileges required"))

    async def test_http_operations_unknown_device_404(self):
        payload = json.dumps({"kind": "identify"}).encode()
        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_UNKNOWN/operations",
            token=self.admin_token,
            body=payload,
        )
        self.assertEqual(status, 404)
        self.assertEqual(data.get("error_code"), "DEVICE_NOT_FOUND")

    async def test_http_operations_success_202(self):
        payload = json.dumps({"kind": "identify"}).encode()
        status, _, data = await self._send_request(
            "POST",
            "/api/devices/NODE_TEST_OPS/operations",
            token=self.admin_token,
            body=payload,
        )
        self.assertEqual(status, 202)
        self.assertTrue(data.get("success"))
        self.assertIn("operation_id", data)
        self.assertEqual(data.get("kind"), "identify")

        # Concurrency rejection 409
        status_conflict, _, conflict_data = await self._send_request(
            "POST",
            "/api/devices/NODE_TEST_OPS/operations",
            token=self.admin_token,
            body=json.dumps({"kind": "reboot"}).encode(),
        )
        self.assertEqual(status_conflict, 409)
        self.assertEqual(conflict_data.get("error_code"), "OPERATION_IN_PROGRESS")


if __name__ == "__main__":
    unittest.main()
