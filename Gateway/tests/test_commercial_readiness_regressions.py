"""
Commercial Readiness Regressions Test Suite (R1 - R14).
Validates commercial robustness across:
- R1: Change Wi-Fi rejected without admin permissions.
- R2: WebSocket rejects unauthenticated or mismatched node_id Compact ACK.
- R3: Confirmed load requires correct channel and positive power.
- R5 & R14: 3 relays handled consistently and power not doubled.
- R6: OTA download succeeds with valid ticket, rejected without ticket.
- R7: OTA does not route to wrong socket when target node is offline.
- R8: Accurately record when MQTT publish fails.
- R12: Voice reply confirms success for ACK_ONLY and CONFIRMED_LOAD.
- R13: Member only reads vocabulary of permitted devices.
- Finding 11: Magic byte 0xE9 check and ActionBox vs SubBox compatibility.
- Finding 17: Non-blocking DB operations and telemetry retention pruning.
"""
import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from audio_server import AudioServer
from ota_manager import OTAManager, ESP_IMAGE_MAGIC
from registry_manager import RegistryManager
from verify_engine import CommandVerifier, VerifyResult
from web_server import WebServer
from main import SmartHomeGateway
from intent_engine import IntentEngine
from dialog_manager import DialogManager
import config


class CommercialReadinessRegressions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_registry.db")
        self.fw_dir = os.path.join(self.temp_dir, "firmware")
        os.makedirs(self.fw_dir, exist_ok=True)

        self.auth = Mock()
        self.auth.has_any_admin.return_value = True
        self.auth.authenticate_token.side_effect = self._mock_authenticate_token
        self.auth.get_user_devices.side_effect = lambda uid: ["AB_01"] if uid == 2 else ["AB_01", "SB_01", "AB_3CH"]

        self.registry = RegistryManager(db_path=self.db_path)
        self.gateway = SimpleNamespace(
            auth=self.auth,
            registry=self.registry,
            is_commissioning=False,
            mqtt=Mock(),
            audio_server=Mock(),
            broadcast_event=Mock(),
        )
        self.ota = OTAManager(self.gateway)
        self.ota.firmware_dir = self.fw_dir
        self.gateway.ota = self.ota

        self.server = WebServer(self.gateway)

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

        await self.server._handle_client(reader, writer)
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

    def _create_mock_esp_binary(self, filename: str, content: bytes = b"") -> str:
        """Create a binary file with valid ESP32 magic byte 0xE9 at offset 0."""
        file_path = os.path.join(self.fw_dir, filename)
        # ESP-IDF image header: byte 0 is 0xE9, byte 1 segments (1), byte 12-13 chip_id
        header = bytearray([ESP_IMAGE_MAGIC, 0x01, 0x02, 0x20, 0x00, 0x10, 0x00, 0x40,
                            0x00, 0x00, 0x00, 0x00, 0x09, 0x00, 0x00, 0x00])
        full_bytes = bytes(header) + content
        with open(file_path, "wb") as f:
            f.write(full_bytes)
        return file_path

    # =========================================================================
    # R1: Change Wi-Fi rejected without admin permissions
    # =========================================================================
    async def test_r1_wifi_change_rejected_without_admin(self):
        body = json.dumps({"ssid": "MyWiFi", "password": "password123"}).encode()

        # 1. Unauthenticated request -> 401
        status, _, _ = await self._send_http("POST", "/api/wifi/connect", body=body)
        self.assertEqual(status, 401)

        # 2. Member request (non-admin) -> 403
        status, _, _ = await self._send_http("POST", "/api/wifi/connect",
                                             headers={"Authorization": "Bearer member-token"},
                                             body=body)
        self.assertEqual(status, 403)

        # 3. Admin request -> Accepted (200)
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

    # =========================================================================
    # R2: WebSocket rejects unauthenticated or mismatched node_id Compact ACK
    # =========================================================================
    async def test_r2_ws_rejects_unauthenticated_or_mismatched_ack(self):
        class MockSocket:
            remote_address = ('127.0.0.1', 54321)
            open = True
            def __init__(self, messages=(), headers=None):
                self.messages = iter(messages)
                self.sent = []
                self.headers = headers or {}
                self.closed = False
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

        audio_srv = AudioServer(self.gateway)

        # 1. Compact ACK received before authentication -> Rejected (token required)
        with patch.object(config, "WS_AUDIO_TOKEN", "test_secret_token"):
            ws_unauth = MockSocket([json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 0], "seq": 10})])
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await audio_srv._handle_client(ws_unauth)
                self.assertFalse(mock_update_rl.called)

        # 2. Compact ACK received with mismatched node_id (spoofed from socket bound to AB_01) -> Rejected
        with patch.object(config, "WS_AUDIO_TOKEN", "test_secret_token"):
            ws_spoof = MockSocket([
                json.dumps({"t": "hello", "id": "AB_01"}),
                json.dumps({"t": "ack", "id": "AB_02_SPOOFED", "rl": [1, 0], "seq": 11})
            ], headers={"Authorization": "Bearer test_secret_token"})
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await audio_srv._handle_client(ws_spoof)
                # update_relay_state should never be called with AB_02_SPOOFED
                for call_args in mock_update_rl.call_args_list:
                    self.assertNotEqual(call_args[0][0], "AB_02_SPOOFED")

        # 3. Compact ACK authenticated with matching node_id -> Processed
        with patch.object(config, "WS_AUDIO_TOKEN", "test_secret_token"):
            ws_valid = MockSocket([
                json.dumps({"t": "hello", "id": "AB_01"}),
                json.dumps({"t": "ack", "id": "AB_01", "rl": [1, 0], "seq": 12})
            ], headers={"Authorization": "Bearer test_secret_token"})
            with patch.object(self.registry, "update_relay_state") as mock_update_rl:
                await audio_srv._handle_client(ws_valid)
                mock_update_rl.assert_any_call("AB_01", [1, 0])

    # =========================================================================
    # R3: Confirmed load requires correct channel and positive power
    # =========================================================================
    async def test_r3_load_confirmation_requires_correct_channel_and_positive_power(self):
        thresholds = {"min_on_power_w": 10.0}
        registry = SimpleNamespace(
            get_all_nodes=lambda: {
                "AB_01": {
                    "channels": {
                        "ch1": {"load_verification": thresholds},
                        "ch2": {"load_verification": thresholds},
                    }
                }
            },
            get_rated_watts=lambda *args: 0
        )

        async def _check(sample, report_channel, command_channel):
            command_acks = {}
            load_reports = {}

            async def _send(node, channel, action, seq=None, **kwargs):
                ch_num = {"ch1": 1, "ch2": 2, "ch3": 3}.get(channel, 1)
                command_acks[(node, seq)] = {"channel": ch_num, "status": "OK", "state": "ON" if action == "turn_on" else "OFF"}
                if sample is not None:
                    load_reports[(node, seq)] = {"channel": report_channel, "sample": sample}
                return True

            mqtt = SimpleNamespace(
                send_command=AsyncMock(side_effect=_send),
                command_acks=command_acks,
                load_reports=load_reports,
                get_current_power=lambda nid: 25.0
            )
            verifier = CommandVerifier(mqtt, registry)
            res, before, after, delta = await verifier.verify_command("AB_01", command_channel, "turn_on", seq=7)
            return res

        # 1. Matching channel + power > 10.0W -> CONFIRMED_LOAD
        sample_positive = {"valid": True, "power_w": 25.0, "current_ma": 120}
        res_ok = await _check(sample_positive, report_channel=1, command_channel="ch1")
        self.assertEqual(res_ok, VerifyResult.CONFIRMED_LOAD)

        # 2. Zero power (power_w <= 0) -> ACK_ONLY
        sample_zero = {"valid": True, "power_w": 0.0, "current_ma": 0}
        res_zero = await _check(sample_zero, report_channel=1, command_channel="ch1")
        self.assertEqual(res_zero, VerifyResult.ACK_ONLY)

        # 3. Mismatched channel (command on ch1, report for ch2) -> ACK_ONLY
        res_wrong_ch = await _check(sample_positive, report_channel=2, command_channel="ch1")
        self.assertEqual(res_wrong_ch, VerifyResult.ACK_ONLY)

    # =========================================================================
    # R5 & R14: 3 relays handled consistently and power not doubled
    # =========================================================================
    async def test_r5_and_r14_three_relays_handled_end_to_end_without_doubling_power(self):
        self.registry.data["nodes"]["AB_3CH"] = {
            "name": "ActionBox 3 Relays",
            "hardware": "ActionBox",
            "room": "living_room",
            "status": "online",
            "capabilities": ["relay_3ch"],
            "channels": {
                "ch1": {"name": "Đèn 1", "device_type": "light"},
                "ch2": {"name": "Quạt", "device_type": "fan"},
                "ch3": {"name": "Ổ cắm", "device_type": "socket"},
            },
            "relay_state": [1, 0, 1]
        }
        self.registry.save(changed_node="AB_3CH")

        # Record PZEM telemetry with 120W total board power
        self.registry.record_telemetry("AB_3CH", {
            "power": 120.0,
            "voltage": 220.0,
            "current": 0.55,
            "energy": 1.2
        })

        node = self.registry.data["nodes"]["AB_3CH"]
        # PZEM power stored in last_telemetry without multiplying across relays
        self.assertEqual(node["last_telemetry"]["power"], 120.0)
        self.assertEqual(len(node["relay_state"]), 3)

        # Update relay state on 3rd channel
        self.registry.update_relay_state("AB_3CH", [1, 1, 1])
        self.assertEqual(self.registry.data["nodes"]["AB_3CH"]["relay_state"], [1, 1, 1])

    # =========================================================================
    # R6: OTA download succeeds with valid ticket, rejected without ticket
    # =========================================================================
    async def test_r6_ota_download_succeeds_with_ticket_fails_without(self):
        fn = "actionbox_test_r6.bin"
        self._create_mock_esp_binary(fn, b"OTA_FIRMWARE_PAYLOAD_DATA")

        # 1. Unauthenticated download without ticket -> 401
        status, _, _ = await self._send_http("GET", f"/api/ota/download/{fn}")
        self.assertEqual(status, 401)

        # 2. Unauthenticated download with invalid ticket -> 401
        status, _, _ = await self._send_http("GET", f"/api/ota/download/{fn}?ticket=invalid-ticket&device=AB_01")
        self.assertEqual(status, 401)

        # 3. Create valid ticket for AB_01
        ticket = self.ota.create_download_ticket("AB_01", fn, ttl_seconds=600)
        self.assertTrue(bool(ticket))

        # 4. Download with valid ticket and correct device -> 200 OK
        status, headers, body = await self._send_http("GET", f"/api/ota/download/{fn}?ticket={ticket}&device=AB_01")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-type"), "application/octet-stream")
        self.assertIn(b"OTA_FIRMWARE_PAYLOAD_DATA", body)

        # 5. Download with valid ticket but wrong device -> 401
        status, _, _ = await self._send_http("GET", f"/api/ota/download/{fn}?ticket={ticket}&device=WRONG_DEVICE")
        self.assertEqual(status, 401)

        # 6. Admin session can download without ticket
        status, _, body = await self._send_http("GET", f"/api/ota/download/{fn}",
                                                headers={"Authorization": "Bearer admin-token"})
        self.assertEqual(status, 200)
        self.assertIn(b"OTA_FIRMWARE_PAYLOAD_DATA", body)

    # =========================================================================
    # R7: OTA does not route to wrong socket when target node is offline
    # =========================================================================
    async def test_r7_ota_does_not_route_to_wrong_socket_when_target_offline(self):
        fn = "actionbox_test_r7.bin"
        self._create_mock_esp_binary(fn, b"DATA")

        # Setup audio server mock with active socket for node_A only
        socket_A = AsyncMock()
        self.gateway.audio_server._ws_nodes = {"node_A": socket_A}
        self.gateway.audio_server._active_speakers = [socket_A]
        self.gateway.audio_server._is_ws_alive = Mock(return_value=True)

        # Target node_B is offline (not in _ws_nodes)
        self.gateway.mqtt.publish = AsyncMock(return_value=False)

        res = await self.ota.trigger_via_mqtt("node_B", fn)
        # Must NOT fallback to socket_A
        self.assertFalse(socket_A.send.called)
        # Must report offline/failure
        self.assertFalse(res["success"])
        self.assertTrue(res.get("offline", False))

    # =========================================================================
    # R8: Accurately record when MQTT publish fails
    # =========================================================================
    async def test_r8_ota_mqtt_publish_failure_recorded_correctly(self):
        fn = "actionbox_test_r8.bin"
        self._create_mock_esp_binary(fn, b"DATA")

        # MQTT publish returns False
        self.gateway.mqtt.publish = AsyncMock(return_value=False)
        self.gateway.audio_server._ws_nodes = {}
        self.gateway.audio_server._active_speakers = []

        res = await self.ota.trigger_via_mqtt("node_target", fn)
        self.assertFalse(res["success"])
        self.assertIn("delivery failed", res["error"])

    # =========================================================================
    # R12: Voice reply confirms success for ACK_ONLY and CONFIRMED_LOAD
    # =========================================================================
    async def test_r12_voice_reply_confirms_success_for_ack_only_and_confirmed_load(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.intent = IntentEngine()
        gateway.dialog = DialogManager()
        gateway.registry = SimpleNamespace(
            find_node_by_device=lambda *args: ("AB_01", "ch1"),
            resolve_fullname=lambda *args: "đèn phòng khách",
            next_seq=lambda *args: 1,
            get_all_nodes=lambda: {"AB_01": {}},
        )
        gateway.tts = SimpleNamespace(synthesize=AsyncMock(return_value=None), synthesize_pcm=AsyncMock(return_value=None))

        # 1. CONFIRMED_LOAD: success = True, message contains "đã bật"
        gateway.verifier = CommandVerifier(None, gateway.registry)
        gateway.verifier.verify_command = AsyncMock(return_value=(VerifyResult.CONFIRMED_LOAD, 0, 45, 45))
        res_load = await gateway.process_voice_command("bật đèn phòng khách", client_node_id="SB_01")
        self.assertTrue(res_load["success"])
        self.assertIn("đã bật", res_load["voice_reply"])

        # 2. ACK_ONLY: success = True, message contains "Đã đặt"
        gateway.verifier.verify_command = AsyncMock(return_value=(VerifyResult.ACK_ONLY, 0, 0, 0))
        res_ack = await gateway.process_voice_command("bật đèn phòng khách", client_node_id="SB_01")
        self.assertTrue(res_ack["success"])
        self.assertIn("Đã đặt", res_ack["voice_reply"])

    # =========================================================================
    # R13: Member only reads vocabulary of permitted devices
    # =========================================================================
    async def test_r13_member_only_reads_vocabulary_of_permitted_devices(self):
        self.gateway.get_voice_vocabulary_diagnostics = Mock(
            side_effect=lambda user=None: {
                "devices": ["AB_01"] if user and user.get("role") == "member" else ["AB_01", "SB_01", "AB_3CH"]
            }
        )

        # 1. Request as member -> only AB_01
        status, _, body = await self._send_http("GET", "/api/voice/vocabulary",
                                                headers={"Authorization": "Bearer member-token"})
        self.assertEqual(status, 200)
        data_member = json.loads(body.decode())
        self.assertEqual(data_member["devices"], ["AB_01"])

        # 2. Request as admin -> all devices
        status, _, body = await self._send_http("GET", "/api/voice/vocabulary",
                                                headers={"Authorization": "Bearer admin-token"})
        self.assertEqual(status, 200)
        data_admin = json.loads(body.decode())
        self.assertEqual(len(data_admin["devices"]), 3)

    # =========================================================================
    # Finding 11: Magic byte 0xE9 & Hardware Compatibility (ActionBox vs SubBox)
    # =========================================================================
    async def test_finding_11_magic_byte_and_hardware_compatibility(self):
        # 1. Reject invalid magic byte (not 0xE9)
        bad_fn = "corrupt.bin"
        bad_path = os.path.join(self.fw_dir, bad_fn)
        with open(bad_path, "wb") as f:
            f.write(b"CORRUPTED_NOT_ESP_BINARY_DATA")

        val_bad = self.ota.validate_firmware(bad_fn)
        self.assertFalse(val_bad["valid"])
        self.assertFalse(val_bad["valid_esp"])
        self.assertIn("0xE9", val_bad["error"])

        # 2. Check ActionBox vs SubBox compatibility
        ab_fn = "actionbox_firmware_v2.bin"
        self._create_mock_esp_binary(ab_fn, b"ACTIONBOX_FIRMWARE")

        # Device is SubBox -> Attempting to flash ActionBox binary must be rejected
        self.registry.data["nodes"]["subbox_living"] = {
            "hardware": "SubBox",
            "serial": "SB2_001122"
        }
        val_mismatch = self.ota.validate_firmware(ab_fn, node_id="subbox_living")
        self.assertFalse(val_mismatch["valid"])
        self.assertTrue(val_mismatch["valid_esp"])
        self.assertIn("ActionBox", val_mismatch["error"])
        self.assertIn("SubBox", val_mismatch["error"])

        # Device is ActionBox -> Compatible
        self.registry.data["nodes"]["actionbox_living"] = {
            "hardware": "ActionBox",
            "serial": "AB2_001122"
        }
        val_compat = self.ota.validate_firmware(ab_fn, node_id="actionbox_living")
        self.assertTrue(val_compat["valid"])
        self.assertTrue(val_compat["valid_esp"])
        self.assertTrue(bool(val_compat["sha256"]))

    # =========================================================================
    # Finding 17: Non-blocking DB operations & Telemetry retention pruning
    # =========================================================================
    async def test_finding_17_non_blocking_db_and_telemetry_pruning(self):
        # 1. Non-blocking telemetry recording
        await self.registry.record_telemetry_async("AB_01", {
            "voltage": 220.5, "current": 1.2, "power": 264.6, "energy": 5.4,
            "free_heap": 180000, "wifi_rssi": -65
        })
        # Wait a tick for async worker
        await asyncio.sleep(0.05)

        history = self.registry.get_telemetry_history("AB_01", limit=10)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["power"], 264.6, places=1)

        # 2. Telemetry retention pruning
        # Seed 5 records directly into telemetry_records
        with self.registry._get_db() as conn:
            for i in range(10):
                conn.execute("""
                    INSERT INTO telemetry_records (device_id, voltage, current, power, energy, free_heap, wifi_rssi)
                    VALUES ('AB_01', 220, 1.0, 220, 1.0, 150000, -70)
                """)

        # Prune with max_records=5
        deleted = self.registry.prune_telemetry(max_records=5, retention_days=7)
        self.assertGreater(deleted, 0)

        # Remaining records in DB should not exceed 5
        with self.registry._get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM telemetry_records").fetchone()[0]
            self.assertLessEqual(count, 5)


if __name__ == "__main__":
    unittest.main()
