"""
Task T08: Standardized Command Results, Three-channel ActionBox V2, and Telemetry Tests.
Validates:
1. CommandResult DTO & tuple unpacking & no false success on failure/timeout (R3/R5).
2. LOAD_REPORT staleness check (> 15s rejected).
3. LOAD_REPORT wrong channel rejected.
4. LOAD_REPORT valid=False or missing rejected.
5. LOAD_REPORT positive power confirms load.
6. Vietnamese voice replies for CONFIRMED_LOAD, ACK_ONLY, ALREADY_IN_STATE, TIMEOUT, FAILED.
7. Bulk and Scene command results per device with partial failure detection.
8. ActionBox V2 3-relay independent control and board telemetry not duplicated.
"""

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from verify_engine import CommandVerifier, VerifyResult, CommandResult, ChannelTelemetry
from registry_manager import RegistryManager
from main import SmartHomeGateway
from intent_engine import IntentEngine
from dialog_manager import DialogManager


class TestCommandAndTelemetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_registry.db")
        self.registry = RegistryManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. CommandResult DTO & Unpacking & No False Success
    # =========================================================================
    async def test_command_result_unpacking_and_no_false_success(self):
        res = CommandResult(
            command_id="101",
            requested_state="ON",
            confirmed_state="ON",
            verification=VerifyResult.CONFIRMED_LOAD,
            power_before=10.0,
            power_after=65.0,
            delta=55.0,
            channel="ch1",
            node_id="AB_01",
        )
        self.assertTrue(res.is_success)
        d = res.to_dict()
        self.assertEqual(d["command_id"], "101")
        self.assertEqual(d["requested_state"], "ON")
        self.assertEqual(d["confirmed_state"], "ON")
        self.assertEqual(d["verification"], "confirmed_load")
        self.assertEqual(d["power_before"], 10.0)
        self.assertEqual(d["power_after"], 65.0)
        self.assertEqual(d["delta"], 55.0)

        # Tuple unpacking test
        v, p_b, p_a, delta = res
        self.assertEqual(v, VerifyResult.CONFIRMED_LOAD)
        self.assertEqual(p_b, 10.0)
        self.assertEqual(p_a, 65.0)
        self.assertEqual(delta, 55.0)
        self.assertEqual(len(res), 4)
        self.assertEqual(res[0], VerifyResult.CONFIRMED_LOAD)

        # Failure & Timeout: confirmed_state must NEVER be stamped to requested_state
        res_fail = CommandResult(
            command_id="102",
            requested_state="ON",
            confirmed_state=None,
            verification=VerifyResult.FAILED,
            error="mismatch",
        )
        self.assertFalse(res_fail.is_success)
        self.assertIsNone(res_fail.confirmed_state)

        res_timeout = CommandResult(
            command_id="103",
            requested_state="ON",
            confirmed_state=None,
            verification=VerifyResult.TIMEOUT,
            error="ack_timeout",
        )
        self.assertFalse(res_timeout.is_success)
        self.assertIsNone(res_timeout.confirmed_state)

        # ChannelTelemetry DTO
        telem = ChannelTelemetry("ch1", 1700000000.0, True, 45.5, 220.0, 0.21, 10.5)
        td = telem.to_dict()
        self.assertEqual(td["channel_id"], "ch1")
        self.assertEqual(td["power_w"], 45.5)
        self.assertTrue(td["validity"])

    # =========================================================================
    # 2. LOAD_REPORT Staleness Check (> 15s)
    # =========================================================================
    async def test_load_report_staleness_check(self):
        thresholds = {"min_on_power_w": 10.0}
        registry = SimpleNamespace(
            get_all_nodes=lambda: {
                "AB_01": {
                    "channels": {
                        "ch1": {"load_verification": thresholds},
                    }
                }
            },
            get_rated_watts=lambda *args: 0
        )

        now = time.time()
        # Stale sample: 20s old
        sample_stale = {
            "valid": True,
            "power_w": 30.0,
            "current_ma": 150,
            "sample_time": now - 20.0,
        }
        # Fresh sample: 2s old
        sample_fresh = {
            "valid": True,
            "power_w": 30.0,
            "current_ma": 150,
            "sample_time": now - 2.0,
        }

        async def _run_verify(sample):
            command_acks = {}
            load_reports = {}

            async def _send(node, channel, action, seq=None, **kwargs):
                ch_num = {"ch1": 1, "ch2": 2, "ch3": 3}.get(channel, 1)
                command_acks[(node, seq)] = {"channel": ch_num, "status": "OK", "state": "ON"}
                if sample is not None:
                    load_reports[(node, seq)] = {"channel": 1, "sample": sample, "seq": seq}
                return True

            mqtt = SimpleNamespace(
                send_command=AsyncMock(side_effect=_send),
                command_acks=command_acks,
                load_reports=load_reports,
                get_current_power=lambda nid: 30.0,
            )
            verifier = CommandVerifier(mqtt, registry)
            res = await verifier.verify_command("AB_01", "ch1", "turn_on", seq=7)
            return res

        res_stale = await _run_verify(sample_stale)
        self.assertEqual(res_stale.verification, VerifyResult.ACK_ONLY)

        res_fresh = await _run_verify(sample_fresh)
        self.assertEqual(res_fresh.verification, VerifyResult.CONFIRMED_LOAD)

    # =========================================================================
    # 3. LOAD_REPORT Wrong Channel Check
    # =========================================================================
    async def test_load_report_wrong_channel(self):
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
        sample = {"valid": True, "power_w": 25.0, "current_ma": 120}
        command_acks = {}
        load_reports = {}

        async def _send(node, channel, action, seq=None, **kwargs):
            command_acks[(node, seq)] = {"channel": 1, "status": "OK", "state": "ON"}
            load_reports[(node, seq)] = {"channel": 2, "sample": sample, "seq": seq}
            return True

        mqtt = SimpleNamespace(
            send_command=AsyncMock(side_effect=_send),
            command_acks=command_acks,
            load_reports=load_reports,
            get_current_power=lambda nid: 25.0,
        )
        verifier = CommandVerifier(mqtt, registry)
        res = await verifier.verify_command("AB_01", "ch1", "turn_on", seq=8)
        self.assertEqual(res.verification, VerifyResult.ACK_ONLY)

    # =========================================================================
    # 4. LOAD_REPORT Valid Flag False or Missing
    # =========================================================================
    async def test_load_report_valid_flag_false_or_missing(self):
        thresholds = {"min_on_power_w": 10.0}
        registry = SimpleNamespace(
            get_all_nodes=lambda: {
                "AB_01": {
                    "channels": {
                        "ch1": {"load_verification": thresholds},
                    }
                }
            },
            get_rated_watts=lambda *args: 0
        )

        async def _check_valid(sample_dict):
            command_acks = {}
            load_reports = {}

            async def _send(node, channel, action, seq=None, **kwargs):
                command_acks[(node, seq)] = {"channel": 1, "status": "OK", "state": "ON"}
                load_reports[(node, seq)] = {"channel": 1, "sample": sample_dict, "seq": seq}
                return True

            mqtt = SimpleNamespace(
                send_command=AsyncMock(side_effect=_send),
                command_acks=command_acks,
                load_reports=load_reports,
                get_current_power=lambda nid: 25.0,
            )
            verifier = CommandVerifier(mqtt, registry)
            res = await verifier.verify_command("AB_01", "ch1", "turn_on", seq=9)
            return res.verification

        # valid is False
        self.assertEqual(await _check_valid({"valid": False, "power_w": 25.0}), VerifyResult.ACK_ONLY)
        # valid missing
        self.assertEqual(await _check_valid({"power_w": 25.0}), VerifyResult.ACK_ONLY)

    # =========================================================================
    # 5. LOAD_REPORT Positive Power Confirm
    # =========================================================================
    async def test_load_report_power_thresholds(self):
        thresholds = {"min_on_power_w": 10.0}
        registry = SimpleNamespace(
            get_all_nodes=lambda: {
                "AB_01": {
                    "channels": {
                        "ch1": {"load_verification": thresholds},
                    }
                }
            },
            get_rated_watts=lambda *args: 0
        )

        async def _test_p(p_w):
            command_acks = {}
            load_reports = {}

            async def _send(node, channel, action, seq=None, **kwargs):
                command_acks[(node, seq)] = {"channel": 1, "status": "OK", "state": "ON"}
                load_reports[(node, seq)] = {"channel": 1, "sample": {"valid": True, "power_w": p_w}, "seq": seq}
                return True

            mqtt = SimpleNamespace(
                send_command=AsyncMock(side_effect=_send),
                command_acks=command_acks,
                load_reports=load_reports,
                get_current_power=lambda nid: p_w,
            )
            verifier = CommandVerifier(mqtt, registry)
            res = await verifier.verify_command("AB_01", "ch1", "turn_on", seq=10)
            return res.verification

        self.assertEqual(await _test_p(15.0), VerifyResult.CONFIRMED_LOAD)
        self.assertEqual(await _test_p(0.0), VerifyResult.ACK_ONLY)
        self.assertEqual(await _test_p(-5.0), VerifyResult.ACK_ONLY)

    # =========================================================================
    # 6. Vietnamese Voice Responses
    # =========================================================================
    async def test_voice_responses_differentiation(self):
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

        # 1. CONFIRMED_LOAD -> "đã bật"
        gateway.verifier = SimpleNamespace(
            verify_command=AsyncMock(return_value=CommandResult(
                command_id="1", requested_state="ON", confirmed_state="ON",
                verification=VerifyResult.CONFIRMED_LOAD, power_after=30.0
            ))
        )
        res = await gateway.process_voice_command("bật đèn phòng khách")
        self.assertTrue(res["success"])
        self.assertIn("đã bật", res["voice_reply"])

        # 2. ACK_ONLY -> "Đã đặt ... sang bật"
        gateway.verifier.verify_command = AsyncMock(return_value=CommandResult(
            command_id="2", requested_state="ON", confirmed_state="ON",
            verification=VerifyResult.ACK_ONLY
        ))
        res = await gateway.process_voice_command("bật đèn phòng khách")
        self.assertTrue(res["success"])
        self.assertIn("Đã đặt", res["voice_reply"])

        # 3. ALREADY_IN_STATE -> "đang ở trạng thái bật"
        gateway.verifier.verify_command = AsyncMock(return_value=CommandResult(
            command_id="3", requested_state="ON", confirmed_state="ON",
            verification=VerifyResult.ALREADY_IN_STATE
        ))
        res = await gateway.process_voice_command("bật đèn phòng khách")
        self.assertTrue(res["success"])
        self.assertIn("đang ở trạng thái bật", res["voice_reply"])

        # 4. TIMEOUT -> "Chưa xác nhận được trạng thái thiết bị."
        gateway.verifier.verify_command = AsyncMock(return_value=CommandResult(
            command_id="4", requested_state="ON", confirmed_state=None,
            verification=VerifyResult.TIMEOUT, error="timeout"
        ))
        res = await gateway.process_voice_command("bật đèn phòng khách")
        self.assertFalse(res["success"])
        self.assertEqual(res["voice_reply"], "Chưa xác nhận được trạng thái thiết bị.")

        # 5. FAILED -> "Thiết bị chưa thực hiện được lệnh."
        gateway.verifier.verify_command = AsyncMock(return_value=CommandResult(
            command_id="5", requested_state="ON", confirmed_state=None,
            verification=VerifyResult.FAILED, error="failed"
        ))
        res = await gateway.process_voice_command("bật đèn phòng khách")
        self.assertFalse(res["success"])
        self.assertEqual(res["voice_reply"], "Thiết bị chưa thực hiện được lệnh.")

    # =========================================================================
    # 7. Bulk and Scene Command Results & Partial Failure
    # =========================================================================
    async def test_bulk_and_scene_partial_failure_and_device_results(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.tts = SimpleNamespace(synthesize=AsyncMock(return_value=None), synthesize_pcm=AsyncMock(return_value=None))

        # 2 nodes online: AB_1 succeeds, AB_2 fails
        mock_nodes = {
            "AB_1": {"room": "living_room", "channels": {"ch1": {"device_type": "light"}}},
            "AB_2": {"room": "living_room", "channels": {"ch1": {"device_type": "light"}}},
        }
        gateway.registry = SimpleNamespace(
            get_online_nodes=lambda: mock_nodes,
            next_seq=lambda nid: 1,
            allowed_rooms=lambda: ["living_room"],
        )

        async def _mock_verify(nid, cid, action, seq=0):
            if nid == "AB_1":
                return CommandResult(str(seq), "ON", "ON", VerifyResult.CONFIRMED_LOAD, node_id=nid, channel=cid)
            else:
                return CommandResult(str(seq), "ON", None, VerifyResult.TIMEOUT, error="timeout", node_id=nid, channel=cid)

        gateway.verifier = SimpleNamespace(verify_command=_mock_verify)

        scene_res = await gateway.execute_scene("morning")
        self.assertFalse(scene_res["success"])
        self.assertEqual(scene_res["verify"], "partial")
        self.assertEqual(scene_res["affected_count"], 1)
        self.assertEqual(scene_res["failed_count"], 1)
        self.assertEqual(len(scene_res["device_results"]), 2)
        self.assertIn("1 thiết bị xác nhận, 1 thiết bị chưa xác nhận", scene_res["voice_reply"])

        # Test exception handled properly with return_exceptions=True
        async def _mock_verify_exc(nid, cid, action, seq=0):
            if nid == "AB_1":
                return CommandResult(str(seq), "ON", "ON", VerifyResult.CONFIRMED_LOAD, node_id=nid, channel=cid)
            else:
                raise RuntimeError("Connection reset")

        gateway.verifier = SimpleNamespace(verify_command=_mock_verify_exc)
        scene_res2 = await gateway.execute_scene("morning")
        self.assertFalse(scene_res2["success"])
        self.assertEqual(scene_res2["affected_count"], 1)
        self.assertEqual(scene_res2["failed_count"], 1)
        self.assertEqual(scene_res2["device_results"][1]["error"], "Connection reset")

    # =========================================================================
    # 8. ActionBox V2 3-relays Independent & Telemetry Not Duplicated
    # =========================================================================
    async def test_actionbox_v2_3ch_independent_and_telemetry_isolation(self):
        self.registry.data["nodes"]["AB_V2"] = {
            "name": "ActionBox V2",
            "hardware": "ActionBox_V2",
            "room": "living_room",
            "status": "online",
            "capabilities": ["relay_3ch"],
            "channels": {
                "ch1": {"name": "Đèn", "device_type": "light"},
                "ch2": {"name": "Quạt", "device_type": "fan"},
                "ch3": {"name": "Ổ cắm", "device_type": "socket"},
            },
            "relay_state": [0, 0, 0]
        }
        self.registry.save(changed_node="AB_V2")

        # 1. Update ch2 independently
        ok = self.registry.update_relay_channel("AB_V2", "ch2", 1)
        self.assertTrue(ok)
        self.assertEqual(self.registry.data["nodes"]["AB_V2"]["relay_state"], [0, 1, 0])

        # 2. Update ch3 independently
        ok = self.registry.update_relay_channel("AB_V2", "ch3", 1)
        self.assertTrue(ok)
        self.assertEqual(self.registry.data["nodes"]["AB_V2"]["relay_state"], [0, 1, 1])

        # 3. Telemetry: total board power is 95W, not multiplied onto individual channels
        self.registry.record_telemetry("AB_V2", {
            "voltage": 220.0,
            "current": 0.43,
            "power": 95.0,
            "energy": 0.5,
        })
        node = self.registry.data["nodes"]["AB_V2"]
        self.assertEqual(node["last_telemetry"]["power"], 95.0)
        # ch1, ch2, ch3 must NOT have board power copied directly
        self.assertNotIn("telemetry", node["channels"]["ch1"])
        self.assertNotIn("telemetry", node["channels"]["ch2"])

        # 4. If individual channel telemetry is provided, it is stored per channel
        self.registry.record_telemetry("AB_V2", {
            "voltage": 220.0,
            "current": 0.43,
            "power": 95.0,
            "energy": 0.5,
            "channels": {
                "ch1": {"telemetry": {"power_w": 25.0, "current_a": 0.11, "voltage_v": 220.0, "energy_wh": 0.1}},
                "ch2": {"telemetry": {"power_w": 70.0, "current_a": 0.32, "voltage_v": 220.0, "energy_wh": 0.4}},
            }
        })
        node = self.registry.data["nodes"]["AB_V2"]
        self.assertEqual(node["channels"]["ch1"]["telemetry"]["power_w"], 25.0)
        self.assertEqual(node["channels"]["ch2"]["telemetry"]["power_w"], 70.0)

    # =========================================================================
    # 9. LOAD_REPORT Async Deadline Wait & Power Update
    # =========================================================================
    async def test_load_report_async_deadline_and_power_update(self):
        thresholds = {"min_on_power_w": 10.0}
        registry = SimpleNamespace(
            get_all_nodes=lambda: {
                "AB_01": {
                    "channels": {
                        "ch1": {"load_verification": thresholds},
                    }
                }
            },
            get_rated_watts=lambda *args: 0
        )
        command_acks = {}
        load_reports = {}

        async def _send(node, channel, action, seq=None, **kwargs):
            command_acks[(node, seq)] = {"channel": 1, "status": "OK", "state": "ON"}
            # Simulate firmware delay: post LOAD_REPORT after 100ms
            async def _delayed_post():
                await asyncio.sleep(0.1)
                load_reports[(node, seq)] = {
                    "channel": 1,
                    "sample": {"valid": True, "power_w": 45.0, "current_ma": 200, "sample_time": time.time()},
                    "seq": seq,
                }
            asyncio.create_task(_delayed_post())
            return True

        mqtt = SimpleNamespace(
            send_command=AsyncMock(side_effect=_send),
            command_acks=command_acks,
            load_reports=load_reports,
            get_current_power=lambda nid: 0.0,
        )
        verifier = CommandVerifier(mqtt, registry)
        res = await verifier.verify_command("AB_01", "ch1", "turn_on", seq=99)
        self.assertEqual(res.verification, VerifyResult.CONFIRMED_LOAD)
        self.assertEqual(res.power_after, 45.0)
        self.assertEqual(res.delta, 45.0)

    # =========================================================================
    # 10. Bulk "all" voice command runs in parallel via asyncio.gather
    # =========================================================================
    async def test_bulk_voice_command_parallel_execution(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.intent = SimpleNamespace(
            extract=AsyncMock(return_value={"intent": "control", "command": {"device": "all", "action": "turn_on", "location": "living_room"}}),
            validate_intent=lambda x: True,
            active_engine="mock",
        )
        gateway.dialog = DialogManager()
        gateway.broadcast_event = lambda *args, **kwargs: None
        gateway.tts = SimpleNamespace(synthesize=AsyncMock(return_value=None), synthesize_pcm=AsyncMock(return_value=None))

        mock_nodes = {
            "AB_1": {"room": "living_room", "channels": {"ch1": {"device_type": "light"}}},
            "AB_2": {"room": "living_room", "channels": {"ch1": {"device_type": "fan"}}},
        }
        gateway.registry = SimpleNamespace(
            get_online_nodes=lambda: mock_nodes,
            next_seq=lambda nid: 1,
            allowed_rooms=lambda: ["living_room"],
        )

        concurrent_calls = 0
        max_concurrent = 0

        async def _mock_verify(nid, cid, action, seq=0):
            nonlocal concurrent_calls, max_concurrent
            concurrent_calls += 1
            max_concurrent = max(max_concurrent, concurrent_calls)
            await asyncio.sleep(0.05)
            concurrent_calls -= 1
            return CommandResult(str(seq), "ON", "ON", VerifyResult.ACK_ONLY, node_id=nid, channel=cid)

        gateway.verifier = SimpleNamespace(verify_command=_mock_verify)
        res = await gateway.process_voice_command("bật tất cả phòng khách")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["device_results"]), 2)
        self.assertGreaterEqual(max_concurrent, 2)


if __name__ == "__main__":
    unittest.main()
