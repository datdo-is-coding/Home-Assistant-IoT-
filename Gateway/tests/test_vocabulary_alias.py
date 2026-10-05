import unittest
import tempfile
import os
import shutil
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from registry_manager import RegistryManager, canon_device
from asr_engine import ASREngine
from intent_engine import IntentEngine

class TestVocabularyAlias(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gateway.db")
        self.reg_path = os.path.join(self.test_dir, "test_registry.json")
        self.registry = RegistryManager(registry_path=self.reg_path, db_path=self.db_path)
        # Register a test node
        self.registry.data["nodes"]["test-node-01"] = {
            "mac": "AA:BB:CC:DD:EE:01",
            "room": "phong_khach",
            "name": "Ổ cắm phòng khách",
            "status": "online",
            "channels": {
                "ch1": {"device_type": "light", "name": "Đèn", "aliases": ["den"]},
                "ch2": {"device_type": "fan", "name": "Quạt", "aliases": ["quat"]}
            }
        }
        self.registry.save()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_and_remove_alias_persistence(self):
        # 1. Add alias
        ok = self.registry.add_device_alias("test-node-01", "ch1", "o_cam")
        self.assertTrue(ok)

        node = self.registry.get_all_nodes().get("test-node-01")
        self.assertIn("o_cam", node["channels"]["ch1"]["aliases"])

        # 2. Verify persistence across registry reload
        reloaded_reg = RegistryManager(registry_path=self.reg_path, db_path=self.db_path)
        reloaded_node = reloaded_reg.get_all_nodes().get("test-node-01")
        self.assertIn("o_cam", reloaded_node["channels"]["ch1"]["aliases"])

        # 3. Verify intent resolution & device matching
        allowed = self.registry.allowed_devices()
        self.assertIn("o_cam", allowed)

        matches = self.registry.find_device_candidates(device_type="o_cam", area="phong_khach")
        self.assertTrue(len(matches) > 0)
        self.assertEqual(matches[0][0], "test-node-01")
        self.assertEqual(matches[0][1], "ch1")

        # 4. Remove alias
        ok_remove = self.registry.remove_device_alias("test-node-01", "ch1", "o_cam")
        self.assertTrue(ok_remove)

        node = self.registry.get_all_nodes().get("test-node-01")
        self.assertNotIn("o_cam", node["channels"]["ch1"]["aliases"])

        # Verify removal persisted
        reloaded_reg2 = RegistryManager(registry_path=self.reg_path, db_path=self.db_path)
        reloaded_node2 = reloaded_reg2.get_all_nodes().get("test-node-01")
        self.assertNotIn("o_cam", reloaded_node2["channels"]["ch1"]["aliases"])

    def test_asr_hotword_extraction(self):
        self.registry.add_device_alias("test-node-01", "ch1", "o_cam_test")
        asr = ASREngine()
        hotwords = asr._extract_registry_hotwords(self.registry)
        self.assertIn("O CAM TEST", hotwords)

        asr._active_hotwords = hotwords
        self.assertTrue(asr.has_hotword("o_cam_test"))
        self.assertTrue(asr.has_hotword("O CAM TEST"))

        diag = asr.dump_active_vocabulary(self.registry)
        self.assertIn("O CAM TEST", diag["hotwords"])

    def test_compound_device_id_format(self):
        # Test adding with deviceId like "test-node-01::ch2"
        ok = self.registry.add_device_alias("test-node-01::ch2", None, "quat_mat")
        self.assertTrue(ok)
        node = self.registry.get_all_nodes().get("test-node-01")
        self.assertIn("quat_mat", node["channels"]["ch2"]["aliases"])

        # Test removing with compound id
        ok_remove = self.registry.remove_device_alias("test-node-01::ch2", None, "quat_mat")
        self.assertTrue(ok_remove)
        node = self.registry.get_all_nodes().get("test-node-01")
        self.assertNotIn("quat_mat", node["channels"]["ch2"]["aliases"])

from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace
from web_server import WebServer
import asyncio

class TestVocabularyWebServer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.authenticate_token.return_value = {"id": 1, "role": "admin"}
        self.gateway = SimpleNamespace(
            auth=self.auth,
            add_device_alias=AsyncMock(return_value={"success": True, "device_id": "node01", "channel": "ch1", "alias": "o_cam"}),
            remove_device_alias=AsyncMock(return_value={"success": True, "device_id": "node01", "channel": "ch1", "alias": "o_cam"}),
            get_voice_vocabulary_diagnostics=Mock(return_value={"success": True, "total_active_hotwords": 42}),
        )
        self.server = WebServer(self.gateway)

    async def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload else b""
        reader = asyncio.StreamReader()
        reader.feed_data((
            f"{method} {path} HTTP/1.1\r\nHost: gateway.local\r\n"
            "Authorization: Bearer test-token\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
        ).encode() + body)
        reader.feed_eof()
        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()
        await self.server._handle_client(reader, writer)
        response = b"".join(call.args[0] for call in writer.write.call_args_list)
        headers, resp_body = response.split(b"\r\n\r\n", 1)
        return int(headers.split()[1]), json.loads(resp_body)

    async def test_add_alias_endpoint(self):
        status, body = await self._request("POST", "/api/device/alias", {
            "device_id": "node01::ch1", "alias": "o_cam"
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.gateway.add_device_alias.assert_awaited_once_with("node01::ch1", None, "o_cam")

    async def test_remove_alias_endpoint(self):
        status, body = await self._request("POST", "/api/device/alias", {
            "device_id": "node01", "channel": "ch1", "alias": "o_cam", "action": "remove"
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.gateway.remove_device_alias.assert_awaited_once_with("node01", "ch1", "o_cam")

    async def test_voice_vocabulary_diagnostics_endpoint(self):
        status, body = await self._request("GET", "/api/voice/vocabulary")
        self.assertEqual(status, 200)
        self.assertEqual(body["total_active_hotwords"], 42)

if __name__ == "__main__":
    unittest.main()
