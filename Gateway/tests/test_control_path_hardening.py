"""
Unit Test Suite for Control Path Hardening (Task T02 - Milestone M1).
Validates:
1. WebSocket Audio & Protocol Protection:
   - Rejects unauthenticated ACK.
   - Rejects spoofed ACK (mismatched node_id).
   - Rejects stale/replay owner_epoch packets (ACK, hello, start, need_cfg).
   - Accepts valid/current owner_epoch.
   - Rejects start / binary stream from unbound sockets.
   - Disallows broadcast relay control commands.
2. Web Server Access Control:
   - Rejects unauthorized Wi-Fi connect under normal conditions.
   - Allows Wi-Fi connect during active commissioning window.
   - Filters voice vocabulary strictly by user permissions (member vs admin).
   - Route guard protects /api/commissioning/* and /api/devices/{uid}/operations (admin-only).
"""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
import config
from audio_server import AudioServer
from registry_manager import RegistryManager
from web_server import WebServer


class MockWebSocket:
    remote_address = ("127.0.0.1", 54321)
    open = True

    def __init__(self, messages=(), headers=None, path=""):
        self.messages = iter(messages)
        self.sent = []
        self.headers = headers or {}
        self.path = path
        self.closed = False
        self.close_code = None
        self.close_reason = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.messages)
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, msg):
        self.sent.append(msg if isinstance(msg, bytes) else json.loads(msg))

    async def close(self, code=1000, reason=""):
        self.open = False
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class TestControlPathHardening(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_hardening_registry.db")

        self.auth = Mock()
        self.auth.has_any_admin.return_value = True
        self.auth.authenticate_token.side_effect = self._mock_authenticate_token
        self.auth.get_user_devices.side_effect = lambda uid: ["AB_01"] if uid == 2 else ["AB_01", "SB_01", "AB_3CH"]

        mqtt_mock = Mock()
        mqtt_mock.send_cfg = AsyncMock()
        mqtt_mock.record_compact_ack = Mock()
        self.registry = RegistryManager(db_path=self.db_path)
        lifecycle_mock = Mock()
        lifecycle_mock.get_candidates = Mock(return_value=[])
        lifecycle_mock.start_operation = Mock(return_value=SimpleNamespace(
            operation_id="op_ctrl_test",
            to_dict=lambda: {"operation_id": "op_ctrl_test", "kind": "identify", "state": "running"},
        ))
        self.gateway = SimpleNamespace(
            auth=self.auth,
            registry=self.registry,
            lifecycle=lifecycle_mock,
            is_commissioning=False,
            mqtt=mqtt_mock,
            audio_server=Mock(),
            broadcast_event=Mock(),
        )

        self.web_server = WebServer(self.gateway)
        self.audio_server = AudioServer(self.gateway)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _mock_authenticate_token(self, token: str):
        if token == "admin-token":
            return {"id": 1, "username": "admin", "role": "admin"}
        if token == "member-token":
            return {"id": 2, "username": "member", "role": "member"}
        return None

    async def _send_http(self, method: str, path: str, headers: dict = None, body: bytes = b""):
        req_headers = {
            "Host": "gateway.local",
            "Content-Length": str(len(body)),
        }
        if headers:
            req_headers.update(headers)

        header_lines = "".join(f"{k}: {v}\r\n" for k, v in req_headers.items())
        raw_req = f"{method} {path} HTTP/1.1\r\n{header_lines}\r\n".encode() + body

        reader = asyncio.StreamReader()
        reader.feed_data(raw_req)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()

        await self.web_server._handle_client(reader, writer)
        raw_response = b"".join(call.args[0] for call in writer.write.call_args_list)
        if not raw_response:
            return 0, {}, b""

        parts = raw_response.split(b"\r\n\r\n", 1)
        resp_headers_raw = parts[0].decode()
        resp_body = parts[1] if len(parts) > 1 else b""

        first_line = resp_headers_raw.split("\r\n")[0]
        status = int(first_line.split()[1])

        resp_headers = {}
        for line in resp_headers_raw.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                resp_headers[k.strip().lower()] = v.strip()

        return status, resp_headers, resp_body

    # =========================================================================
    # 1. WebSocket Protocol Protection & Authentication Tests
    # =========================================================================

    async def test_ws_unauthenticated_ack_rejected(self):
        """Unauthenticated ACK without valid token must be rejected."""
        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 0], "seq": 10})
            ])
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await self.audio_server._handle_client(ws)
                self.assertFalse(mock_update_rl.called)

    async def test_ws_spoofed_ack_rejected(self):
        """Authenticated socket bound to AB_01 cannot acknowledge AB_02_SPOOFED."""
        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01"}),
                json.dumps({"t": "ack", "id": "AB_02_SPOOFED", "rl": [1, 0], "seq": 11}),
            ], headers={"Authorization": "Bearer secret123"})
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await self.audio_server._handle_client(ws)
                for call_args in mock_update_rl.call_args_list:
                    self.assertNotEqual(call_args[0][0], "AB_02_SPOOFED")

    async def test_ws_stale_owner_epoch_ack_rejected(self):
        """ACK sending an owner_epoch older than the registry's accepted epoch must be rejected."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 5,
            "status": "online",
        }
        self.registry.save()

        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            # Socket authenticates and binds to AB_01
            ws = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 5}),
                # Replay / stale packet with epoch 4 (< 5)
                json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 1], "seq": 12, "owner_epoch": 4}),
            ], headers={"Authorization": "Bearer secret123"})

            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await self.audio_server._handle_client(ws)
                self.assertFalse(mock_update_rl.called)

    async def test_ws_valid_owner_epoch_ack_accepted(self):
        """ACK sending an owner_epoch >= current epoch must be accepted."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 3,
            "status": "online",
        }
        self.registry.save()

        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 3}),
                json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 0], "seq": 13, "owner_epoch": 3}),
            ], headers={"Authorization": "Bearer secret123"})

            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await self.audio_server._handle_client(ws)
                mock_update_rl.assert_called_with("AB_01", [1, 0])

    async def test_ws_stale_owner_epoch_hello_rejected(self):
        """Hello with owner_epoch smaller than registry accepted epoch must be rejected with stale_epoch."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 4,
            "status": "online",
        }
        self.registry.save()

        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 2})
            ], headers={"Authorization": "Bearer secret123"})

            await self.audio_server._handle_client(ws)
            self.assertTrue(ws.closed)
            err_msgs = [m for m in ws.sent if isinstance(m, dict) and m.get("error") == "stale_epoch"]
            self.assertTrue(len(err_msgs) > 0)

    async def test_ws_stale_owner_epoch_start_rejected(self):
        """Voice start with stale owner_epoch must be rejected."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 4,
            "status": "online",
        }
        self.registry.save()

        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 4}),
                json.dumps({"type": "start", "node_id": "AB_01", "owner_epoch": 2}),
            ], headers={"Authorization": "Bearer secret123"})

            await self.audio_server._handle_client(ws)
            err_msgs = [m for m in ws.sent if isinstance(m, dict) and m.get("error") == "stale_epoch"]
            self.assertTrue(len(err_msgs) > 0)

    async def test_ws_start_from_unbound_socket_rejected(self):
        """Start sent on a socket that has not bound an identity and provides no node_id must be rejected."""
        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            ws = MockWebSocket([
                json.dumps({"type": "start"})  # No node_id, no prior hello
            ], headers={"Authorization": "Bearer secret123"})

            await self.audio_server._handle_client(ws)
            err_msgs = [m for m in ws.sent if isinstance(m, dict) and m.get("error") == "identity_required"]
            self.assertTrue(len(err_msgs) > 0)

    async def test_ws_binary_stream_from_unauthenticated_or_unbound_rejected(self):
        """Binary audio chunks from an unauthenticated or unbound socket must be discarded."""
        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            # Raw PCM sent directly without hello or auth
            ws = MockWebSocket([
                b"\x00\x01" * 160
            ])
            await self.audio_server._handle_client(ws)
            self.assertFalse(self.audio_server._active_voice_session)

    async def test_ws_broadcast_relay_control_rejected(self):
        """send_relay_ws must refuse broadcast identifiers ('all', 'broadcast', '*')."""
        for broadcast_target in ("all", "broadcast", "*", "", "ff:ff:ff:ff:ff:ff"):
            ok = await self.audio_server.send_relay_ws(broadcast_target, "ch1", "turn_on", seq=1)
            self.assertFalse(ok, f"Expected send_relay_ws({broadcast_target}) to return False")

    # =========================================================================
    # 2. Web Server Access Control & Commissioning Route Guard Tests
    # =========================================================================

    async def test_web_wifi_connect_rejected_without_admin_under_normal_conditions(self):
        """Under normal conditions (is_commissioning=False), /api/wifi/connect requires admin."""
        self.gateway.is_commissioning = False
        body = json.dumps({"ssid": "OfficeWiFi", "password": "pass"}).encode()

        # 1. Unauthenticated -> 401
        status, _, _ = await self._send_http("POST", "/api/wifi/connect", body=body)
        self.assertEqual(status, 401)

        # 2. Member user -> 403
        status, _, _ = await self._send_http("POST", "/api/wifi/connect",
                                             headers={"Authorization": "Bearer member-token"},
                                             body=body)
        self.assertEqual(status, 403)

        # 3. Admin user -> Allowed
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.wait.return_value = 0
        proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            status, _, _ = await self._send_http("POST", "/api/wifi/connect",
                                                 headers={"Authorization": "Bearer admin-token"},
                                                 body=body)
            self.assertEqual(status, 200)
            await asyncio.sleep(0)

    async def test_web_wifi_connect_allowed_during_active_commissioning_window(self):
        """During active commissioning window (is_commissioning=True), /api/wifi/connect is permitted."""
        self.gateway.is_commissioning = True
        body = json.dumps({"ssid": "SetupWiFi", "password": "pass"}).encode()

        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.wait.return_value = 0
        proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            # Unauthenticated connection allowed in commissioning mode
            status, _, _ = await self._send_http("POST", "/api/wifi/connect", body=body)
            self.assertEqual(status, 200)
            await asyncio.sleep(0)

    async def test_web_voice_vocabulary_filtered_by_user_devices(self):
        """Member only sees vocabulary for devices returned by auth.get_user_devices; Admin sees all."""
        def _get_vocab(user=None):
            return {
                "success": True,
                "devices": ["AB_01", "SB_01", "AB_3CH"],
                "stored_vocabulary": [
                    {"node_id": "AB_01", "channel": "ch1", "name": "Đèn 1"},
                    {"node_id": "SB_01", "channel": "ch1", "name": "Đèn SubBox"},
                    {"node_id": "AB_3CH", "channel": "ch1", "name": "Đèn 3CH"},
                ]
            }
        self.gateway.get_voice_vocabulary_diagnostics = Mock(side_effect=_get_vocab)

        # 1. Member -> filtered to AB_01 only
        status, _, body = await self._send_http("GET", "/api/voice/vocabulary",
                                                headers={"Authorization": "Bearer member-token"})
        self.assertEqual(status, 200)
        data_member = json.loads(body.decode())
        self.assertEqual(data_member["devices"], ["AB_01"])
        self.assertEqual(len(data_member["stored_vocabulary"]), 1)
        self.assertEqual(data_member["stored_vocabulary"][0]["node_id"], "AB_01")

        # 2. Admin -> sees all 3 devices
        status, _, body = await self._send_http("GET", "/api/voice/vocabulary",
                                                headers={"Authorization": "Bearer admin-token"})
        self.assertEqual(status, 200)
        data_admin = json.loads(body.decode())
        self.assertEqual(len(data_admin["devices"]), 3)
        self.assertEqual(len(data_admin["stored_vocabulary"]), 3)

    async def test_web_commissioning_route_guard_admin_only(self):
        """Route guard for /api/commissioning/* requires admin."""
        # 1. Unauthenticated -> 401
        status, _, _ = await self._send_http("GET", "/api/commissioning/candidates")
        self.assertEqual(status, 401)

        # 2. Member -> 403
        status, _, _ = await self._send_http("GET", "/api/commissioning/candidates",
                                             headers={"Authorization": "Bearer member-token"})
        self.assertEqual(status, 403)

        # 3. Admin -> 200
        status, _, body = await self._send_http("GET", "/api/commissioning/candidates",
                                                headers={"Authorization": "Bearer admin-token"})
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data.get("success"))

    async def test_web_device_operations_route_guard_admin_only(self):
        """Route guard for /api/devices/{uid}/operations requires admin."""
        req_body = json.dumps({"kind": "identify"}).encode()

        # 1. Unauthenticated -> 401
        status, _, _ = await self._send_http("POST", "/api/devices/AB_01/operations", body=req_body)
        self.assertEqual(status, 401)

        # 2. Member -> 403
        status, _, _ = await self._send_http("POST", "/api/devices/AB_01/operations",
                                             headers={"Authorization": "Bearer member-token"},
                                             body=req_body)
        self.assertEqual(status, 403)

        # 3. Admin -> 200 or 202
        status, _, body = await self._send_http("POST", "/api/devices/AB_01/operations",
                                                headers={"Authorization": "Bearer admin-token"},
                                                body=req_body)
        self.assertIn(status, (200, 202))
        data = json.loads(body.decode())
        self.assertTrue(data.get("success"))

    # =========================================================================
    # 3. Epoch Rollback & Epoch Stripping Defense Tests
    # =========================================================================

    def test_registry_epoch_rollback_rejected(self):
        """RegistryManager must reject owner_epoch rollback via on_hello and update_node_owner_epoch."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 5,
            "status": "online",
            "mac": "11:22:33:44:55:66",
        }
        self.registry.save()

        # 1. update_node_owner_epoch with stale epoch (3 < 5) -> Rejected
        with patch("registry_manager.logger.warning") as mock_warn:
            self.registry.update_node_owner_epoch("AB_01", 3)
            self.assertEqual(self.registry.get_node_owner_epoch("AB_01"), 5)
            mock_warn.assert_called_with("Ignored stale owner_epoch 3")

        # 2. update_node_owner_epoch with newer epoch (6 >= 5) -> Accepted
        self.registry.update_node_owner_epoch("AB_01", 6)
        self.assertEqual(self.registry.get_node_owner_epoch("AB_01"), 6)

        # 3. on_hello with stale epoch (2 < 6) -> Rejected
        with patch("registry_manager.logger.warning") as mock_warn:
            res = self.registry.on_hello({
                "node_id": "AB_01",
                "mac": "11:22:33:44:55:66",
                "owner_epoch": 2,
                "cfg": 1,
                "state": "CONFIGURED",
            })
            self.assertEqual(res, {"action": "rejected", "error": "stale_epoch", "node_id": "AB_01"})
            self.assertEqual(self.registry.get_node_owner_epoch("AB_01"), 6)
            mock_warn.assert_called_with("Rejected stale owner_epoch 2 < 6 for node AB_01")

        # 4. on_hello with newer epoch (8 >= 6) -> Accepted
        res = self.registry.on_hello({
            "node_id": "AB_01",
            "mac": "11:22:33:44:55:66",
            "owner_epoch": 8,
            "cfg": 1,
            "state": "CONFIGURED",
        })
        self.assertEqual(res, {"action": "known", "node_id": "AB_01"})
        self.assertEqual(self.registry.get_node_owner_epoch("AB_01"), 8)

        # 5. on_hello missing owner_epoch when node has owner_epoch > 0 -> Rejected (epoch stripped)
        with patch("registry_manager.logger.warning") as mock_warn:
            res = self.registry.on_hello({
                "node_id": "AB_01",
                "mac": "11:22:33:44:55:66",
                "cfg": 1,
                "state": "CONFIGURED",
            })
            self.assertEqual(res, {"action": "rejected", "error": "epoch_stripped", "node_id": "AB_01"})
            self.assertEqual(self.registry.get_node_owner_epoch("AB_01"), 8)
            mock_warn.assert_called_with("Rejected packet missing owner_epoch (epoch stripped) for node AB_01")

    async def test_ws_epoch_stripping_rejected(self):
        """When node has owner_epoch > 0, packets stripped of owner_epoch/epoch must be rejected."""
        self.registry.data["nodes"]["AB_01"] = {
            "node_id": "AB_01",
            "owner_epoch": 5,
            "status": "online",
        }
        self.registry.save()

        with patch.object(config, "WS_AUDIO_TOKEN", "secret123"):
            # 1. Hello stripped of epoch -> Rejected with stale_epoch error
            ws_hello = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01"})  # No owner_epoch
            ], headers={"Authorization": "Bearer secret123"})
            await self.audio_server._handle_client(ws_hello)
            self.assertTrue(ws_hello.closed)
            err_msgs = [m for m in ws_hello.sent if isinstance(m, dict) and m.get("error") == "stale_epoch"]
            self.assertTrue(len(err_msgs) > 0)

            # 2. ACK stripped of epoch on socket with epoch > 0 -> Rejected
            ws_ack = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 5}),
                json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 1], "seq": 14}),  # Stripped epoch
            ], headers={"Authorization": "Bearer secret123"})
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await self.audio_server._handle_client(ws_ack)
                self.assertFalse(mock_update_rl.called)

            # 3. Voice start stripped of epoch on bound socket with epoch > 0 -> Rejected
            ws_start = MockWebSocket([
                json.dumps({"t": "hello", "id": "AB_01", "owner_epoch": 5}),
                json.dumps({"type": "start", "node_id": "AB_01"}),  # Stripped epoch
            ], headers={"Authorization": "Bearer secret123"})
            await self.audio_server._handle_client(ws_start)
            err_msgs = [m for m in ws_start.sent if isinstance(m, dict) and m.get("error") == "stale_epoch"]
            self.assertTrue(len(err_msgs) > 0)

    async def test_broadcast_commands_flag_respected(self):
        """Broadcast relay control commands must respect ALLOW_BROADCAST_COMMANDS."""
        from mqtt_handler import MQTTHandler
        mqtt = MQTTHandler()

        # Default (False): rejected
        with patch.object(config, "ALLOW_BROADCAST_COMMANDS", False):
            ok_ws = await self.audio_server.send_relay_ws("broadcast", "ch1", "turn_on", seq=1)
            self.assertFalse(ok_ws)
            ok_mqtt = await mqtt.send_command("broadcast", "ch1", "turn_on", seq=1)
            self.assertFalse(ok_mqtt)


if __name__ == "__main__":
    unittest.main()
