import unittest
import tempfile
import os
import shutil
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from registry_manager import RegistryManager
from main import SmartHomeGateway
from discovery_manager import DiscoveryManager

class TestActionBox3Relay(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gateway.db")
        self.reg_path = os.path.join(self.test_dir, "test_registry.json")
        self.registry = RegistryManager(registry_path=self.reg_path, db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_provision_node_3_relays(self):
        self.registry.data["pending"]["AA:BB:CC:DD:EE:11"] = {
            "device_id": "node_ee11",
            "mac": "AA:BB:CC:DD:EE:11",
            "hardware": "esp32s3",
            "serial": "S3-2026-000011",
            "rl": [0, 0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="AA:BB:CC:DD:EE:11",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3="switch",
            name="Loa Phong Khach"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.get("rl3"), "switch")
        self.assertIn("relay_3ch", node.get("capabilities", []))
        self.assertNotIn("relay_2ch", node.get("capabilities", []))
        self.assertEqual(len(node.get("channels", {})), 3)
        self.assertIn("ch3", node["channels"])
        self.assertEqual(node["channels"]["ch3"]["gpio"], 5)
        self.assertEqual(node["channels"]["ch3"]["device_type"], "switch")
        self.assertIn("ch3", node["configuration"]["relays"])
        self.assertEqual(node["relay_state"], [0, 0, 0])

        cfg = self.registry.get_provision_payload(node["device_id"])
        self.assertEqual(cfg.get("rl3"), "switch")

    def test_update_device_3_relays(self):
        self.registry.data["pending"]["AA:BB:CC:DD:EE:22"] = {
            "device_id": "node_ee22",
            "mac": "AA:BB:CC:DD:EE:22",
            "hardware": "esp32",
            "serial": "S3-2026-000022",
            "rl": [0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="AA:BB:CC:DD:EE:22",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3=None,
            name="Node 2CH"
        )
        self.assertIn("relay_2ch", node.get("capabilities", []))
        self.assertEqual(len(node.get("channels", {})), 2)

        updated = self.registry.update_device(node["device_id"], {
            "ch3_type": "switch",
            "ch3_name": "Công tắc phụ",
            "ch3_aliases": ["công tắc", "ổ cắm phụ"]
        })
        self.assertIn("ch3", updated["channels"])
        self.assertEqual(updated["channels"]["ch3"]["name"], "Công tắc phụ")
        self.assertIn("công tắc", updated["channels"]["ch3"]["aliases"])
        self.assertIn("ch3", updated["configuration"]["relays"])
        self.assertIn("relay_3ch", updated["capabilities"])

    def test_update_desired_config_3_relays(self):
        v, payload = self.registry.update_desired_config("node_twin", {
            "name": "Twin Node",
            "room": "phong_khach",
            "rl1": "light",
            "rl2": "fan",
            "rl3": "switch"
        })
        self.assertEqual(payload.get("rl3"), "switch")
        node = self.registry.get_all_nodes()["node_twin"]
        self.assertIn("ch3", node["channels"])
        self.assertIn("ch3", node["configuration"]["relays"])

    def test_sqlite_sync_dynamic_num_relays(self):
        self.registry.data["pending"]["AA:BB:CC:DD:EE:33"] = {
            "device_id": "node_ee33",
            "mac": "AA:BB:CC:DD:EE:33",
            "hardware": "esp32s3",
            "serial": "S3-2026-000033",
            "rl": [0, 0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="AA:BB:CC:DD:EE:33",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3="switch"
        )
        actual_id = node["device_id"]
        with self.registry._get_db() as conn:
            row = conn.execute("SELECT relay_channels FROM device_capabilities WHERE device_id=?", (actual_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["relay_channels"], 3)

    async def test_subbox_actionbox_dynamic_channels(self):
        gw = SmartHomeGateway()
        gw.registry = self.registry

        self.registry.data["pending"]["AA:BB:CC:DD:EE:44"] = {
            "device_id": "node_ee44",
            "mac": "AA:BB:CC:DD:EE:44",
            "hardware": "esp32",
            "serial": "S3-2026-000044",
            "rl": [0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="AA:BB:CC:DD:EE:44",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3=None
        )
        nid = node["device_id"]

        payload = {
            "node_id": nid,
            "channels": [
                {"channel": 1, "state": "ON"},
                {"channel": 2, "state": "OFF"},
                {"channel": 3, "state": "ON"}
            ]
        }
        await gw._on_subbox_actionbox("home/subbox/test/event/actionbox", payload)

        updated_node = self.registry.get_all_nodes()[nid]
        self.assertEqual(updated_node["relay_state"], [1, 0, 1])
        self.assertIn("ch3", updated_node["channels"])
        self.assertIn("relay_3ch", updated_node["capabilities"])

    async def test_discovery_manager_channel_number_extraction(self):
        gw = Mock()
        gw.registry = self.registry
        gw.mqtt = Mock()
        gw.mqtt.client = Mock()
        gw.mqtt.client.publish = AsyncMock()

        dm = DiscoveryManager(gw)
        self.registry.data["pending"]["AA:BB:CC:DD:EE:55"] = {
            "device_id": "node_ee55",
            "mac": "AA:BB:CC:DD:EE:55",
            "hardware": "esp32s3",
            "serial": "S3-2026-000055",
            "rl": [0, 0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="AA:BB:CC:DD:EE:55",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3="switch"
        )
        nid = node["device_id"]
        await dm.publish_ha_discovery_for_node(nid)

        calls = gw.mqtt.client.publish.call_args_list
        self.assertEqual(len(calls), 3)

        payloads = [json.loads(c.args[1]) for c in calls]
        payload_map = {p["unique_id"]: p for p in payloads}

        self.assertIn(f"{nid}_ch1", payload_map)
        self.assertIn(f"{nid}_ch2", payload_map)
        self.assertIn(f"{nid}_ch3", payload_map)

        ch1_p = payload_map[f"{nid}_ch1"]
        self.assertEqual(ch1_p["value_template"], "{{ value_json.rl[0] }}")
        ch3_p = payload_map[f"{nid}_ch3"]
        self.assertEqual(ch3_p["value_template"], "{{ value_json.rl[2] }}")
        cmd_on = json.loads(ch3_p["payload_on"])
        self.assertEqual(cmd_on["ch"], 3)

    async def test_web_server_provision_parses_rl3(self):
        import asyncio
        from web_server import WebServer

        gw = Mock()
        gw.registry = self.registry
        gw.auth = Mock()
        gw.auth.authenticate_token.return_value = {"id": 1, "role": "admin"}
        gw.provision_pending = AsyncMock(return_value={"success": True, "device_id": "test_dev"})

        server = WebServer(gw)
        body = json.dumps({
            "device_id": "test_dev",
            "room": "phong_khach",
            "rl1": "light",
            "rl2": "fan",
            "rl3": "switch"
        }).encode()

        reader = asyncio.StreamReader()
        reader.feed_data((
            "POST /api/provision HTTP/1.1\r\nHost: gateway.local\r\n"
            "Authorization: Bearer test-token\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        ).encode() + body)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()
        await server._handle_client(reader, writer)

        gw.provision_pending.assert_awaited_once_with(
            "test_dev",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3="switch",
            node_short=None,
            name=None,
            location=None,
            description=None
        )

    def test_provision_node_legacy_2ch_default(self):

        self.registry.data["pending"]["node_legacy"] = {
            "device_id": "node_legacy",
            "mac": "11:22:33:44:55:66",
            "hardware": "esp32",
            "serial": "LEGACY-001",
            "rl": [0, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="node_legacy",
            room="phong_ngu",
            rl1="light",
            rl2="fan",
            rl3=None
        )
        self.assertIsNotNone(node)
        self.assertNotIn("ch3", node.get("channels", {}))
        self.assertIn("relay_2ch", node.get("capabilities", []))
        self.assertNotIn("relay_3ch", node.get("capabilities", []))
        self.assertEqual(len(node.get("channels", {})), 2)
        self.assertEqual(node["relay_state"], [0, 0])

        self.registry.data["pending"]["node_v2"] = {
            "device_id": "node_v2",
            "mac": "22:33:44:55:66:77",
            "hardware": "ActionBox",
            "serial": "AB2-001",
            "rl": [0, 0, 0]
        }
        node_v2 = self.registry.provision_node(
            mac_or_id="node_v2",
            room="phong_khach",
            rl1="light",
            rl2="fan",
            rl3=None
        )
        self.assertIsNotNone(node_v2)
        self.assertIn("ch3", node_v2.get("channels", {}))
        self.assertIn("relay_3ch", node_v2.get("capabilities", []))
        self.assertEqual(len(node_v2.get("channels", {})), 3)
        self.assertEqual(node_v2["channels"]["ch3"]["gpio"], 5)
        self.assertEqual(node_v2["relay_state"], [0, 0, 0])

    def test_update_device_pads_relay_state(self):
        self.registry.data["pending"]["node_pad"] = {
            "device_id": "node_pad",
            "mac": "33:44:55:66:77:88",
            "hardware": "esp32",
            "rl": [1, 0]
        }
        node = self.registry.provision_node(
            mac_or_id="node_pad",
            room="phong_khach",
            rl3=None
        )
        self.assertEqual(node["relay_state"], [1, 0])

        updated = self.registry.update_device(node["device_id"], {
            "ch3_type": "switch",
            "ch3_name": "Phụ"
        })
        self.assertEqual(updated["relay_state"], [1, 0, 0])

    async def test_mqtt_command_routing_channel_3(self):
        from mqtt_handler import MQTTHandler
        mqtt = MQTTHandler()
        mqtt.publish = AsyncMock(return_value=True)

        ok = await mqtt.send_command("AB100", "ch3", "turn_on", seq=42)
        self.assertTrue(ok)
        calls = mqtt.publish.call_args_list
        self.assertEqual(len(calls), 3)

        c1_topic, c1_payload = calls[0].args
        self.assertEqual(c1_payload["ch"], 3)
        self.assertEqual(c1_payload["s"], 1)
        self.assertEqual(c1_payload["seq"], 42)

        c2_topic, c2_payload = calls[1].args
        self.assertEqual(c2_topic, "home/devices/AB100/relay/3/set")
        self.assertEqual(c2_payload, {"state": 1})

        c3_topic, c3_payload = calls[2].args
        self.assertEqual(c3_topic, "home/nodes/AB100/relay/3/set")
        self.assertEqual(c3_payload, {"state": 1})

    async def test_audio_server_command_routing_channel_3(self):
        from audio_server import AudioServer
        gw = Mock()
        server = AudioServer(gw)
        ws = Mock()
        ws.send = AsyncMock()
        ws.open = True
        ws.closed = False
        ws.asr_only = False
        ws.audio_relay = False
        ws.playback_only = False
        server._ws_nodes["AB100"] = ws

        ok = await server.send_relay_ws("AB100", "ch3", "turn_on", seq=99)
        self.assertTrue(ok)
        ws.send.assert_awaited_once()
        sent = json.loads(ws.send.call_args.args[0])
        self.assertEqual(sent["ch"], 3)
        self.assertEqual(sent["s"], 1)
        self.assertEqual(sent["seq"], 99)

    async def test_dialog_and_intent_channel_3(self):
        from dialog_manager import DialogManager, DialogSession
        from intent_engine import IntentEngine
        dm = DialogManager(registry=self.registry)
        session = DialogSession(
            node_id="AB100",
            client_id="client1",
            pending_intent={"command": {"action": "turn_on"}},
            missing_slot="channel"
        )
        filled = dm.fill_slot(session, "kênh 3")
        self.assertEqual(filled["command"]["device"], "ch3")

        ie = IntentEngine(registry=self.registry)
        parsed = await ie.extract("bật kênh 3")
        self.assertEqual(parsed.intent, "turn_on")
        self.assertEqual(parsed.target.device_type, "ch3")
        self.assertEqual(parsed["command"]["action"], "turn_on")
        self.assertEqual(parsed["command"]["device"], "ch3")

if __name__ == '__main__':
    unittest.main()
