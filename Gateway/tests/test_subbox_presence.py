"""SubBox presence through the real MQTT dispatcher, registry and API snapshot."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from main import SmartHomeGateway
from mqtt_handler import MQTTHandler
from registry_manager import RegistryManager
from web_server import WebServer


class SubBoxPresence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.gateway = gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry = RegistryManager(
            registry_path=str(Path(temporary.name) / "missing.json"),
            db_path=str(Path(temporary.name) / "gateway.db"),
        )
        self.node_id = "SB288485350B54"
        gateway.registry.data["nodes"][self.node_id] = {
            "status": "online", "last_seen": "2026-01-01T00:00:00+07:00",
            "room": "Phòng Ngủ", "channels": {},
        }
        gateway.registry.save(changed_node=self.node_id)
        gateway.asr = SimpleNamespace(initialize=Mock())
        gateway.kws = SimpleNamespace(
            on_result=Mock(), on_config_ack=Mock(), sync_config=AsyncMock()
        )
        gateway.audio_server = SimpleNamespace(start=AsyncMock())
        gateway.web_server = WebServer(gateway)
        gateway.web_server.start = AsyncMock()
        self.events = asyncio.Queue()
        gateway.web_server.sse_queues[self.events] = {"role": "admin"}
        gateway.telemetry_writer = None
        gateway.mqtt = MQTTHandler()
        gateway.mqtt.connect = AsyncMock()
        gateway._announce_all_nodes = AsyncMock()
        await gateway.start()
        await asyncio.sleep(0)

    async def receive(self, payload, node_id=None):
        await self.gateway.mqtt._handle_message(SimpleNamespace(
            topic=f"home/subbox/{node_id or self.node_id}/state",
            payload=json.dumps(payload).encode(),
        ))

    def status(self):
        return self.gateway.web_server._nodes_snapshot()["nodes"][self.node_id]["status"]

    async def test_live_heartbeat_restores_stale_subbox_in_api_and_sse(self):
        self.assertEqual(self.status(), "offline")
        await self.receive({"subbox_id": self.node_id, "status": "ONLINE", "uptime_s": 5})
        self.assertEqual(self.status(), "online")
        event = self.events.get_nowait()
        self.assertIn("event: node_status", event)
        payload = json.loads(event.split("data: ", 1)[1])
        self.assertEqual(payload["node_id"], self.node_id)
        self.assertTrue(payload["online"])
        registry = self.gateway.registry
        for _ in range(50):
            reloaded = RegistryManager(registry_path=registry.path, db_path=registry.db_path)
            if reloaded.get_all_nodes() == registry.get_all_nodes():
                break
            await asyncio.sleep(0.02)
        self.assertEqual(reloaded.get_all_nodes(), registry.get_all_nodes())

    async def test_silent_subbox_expires_after_ninety_seconds(self):
        await self.receive({"subbox_id": self.node_id, "status": "ONLINE"})
        self.assertEqual(self.status(), "online")
        self.gateway.registry.data["nodes"][self.node_id]["last_seen"] = (
            datetime.now(timezone.utc) - timedelta(seconds=91)
        ).isoformat()
        self.assertEqual(self.status(), "offline")

    async def test_invalid_or_unknown_heartbeat_does_not_change_registry(self):
        before = deepcopy(self.gateway.registry.data)
        for payload, topic_id in (
            (None, self.node_id),
            ([], self.node_id),
            ({"status": "ONLINE"}, self.node_id),
            ({"subbox_id": [], "status": "ONLINE"}, self.node_id),
            ({"subbox_id": "SBother", "status": "ONLINE"}, self.node_id),
            ({"subbox_id": "SBunknown", "status": "ONLINE"}, "SBunknown"),
            ({"subbox_id": self.node_id, "status": "OFFLINE"}, self.node_id),
        ):
            with self.subTest(payload=payload):
                await self.receive(payload, topic_id)
                self.assertEqual(self.gateway.registry.data, before)
                self.assertTrue(self.events.empty())

    async def test_heartbeat_does_not_reenable_device_needing_reprovision(self):
        self.gateway.registry.data["nodes"][self.node_id]["status"] = "NEEDS_REPROVISION"
        before = deepcopy(self.gateway.registry.data)
        await self.receive({"subbox_id": self.node_id, "status": "ONLINE"})
        self.assertEqual(self.gateway.registry.data, before)
        self.assertTrue(self.events.empty())
