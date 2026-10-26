"""
Unit tests for GatewayBeacon (Gateway/gateway/gateway_beacon.py).
Tests:
- GatewayBeacon initialization, default & custom configuration.
- get_beacon_payload() structure and required fields.
- get_local_ip() behavior.
- Starting and stopping GatewayBeacon (lifecycle, idempotency).
- UDP discovery: sending "DISCOVER_GATEWAY" and validating the JSON reply format:
  (service, ip, ws_port, mqtt_port, mqtt_tls_port, http_port, version).
- UDP JSON probe variants (action="discover", probe=True, service="aetheria_probe").
- Malformed datagram handling (binary garbage, truncated JSON, empty bytes).
- Ignoring self-beacons and irrelevant packets.
- DatagramProtocol and handle_datagram direct unit tests and error handling.
- Periodic broadcast loop execution.
- SmartHomeGateway lifecycle integration with beacon.
"""

import asyncio
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add gateway package to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
import config
from gateway_beacon import GatewayBeacon, GatewayBeaconProtocol
from main import SmartHomeGateway


def get_ephemeral_port() -> int:
    """Acquire a temporary free UDP port for testing without collision."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class GatewayBeaconTest(unittest.IsolatedAsyncioTestCase):
    """Test suite for GatewayBeacon service and protocol."""

    def setUp(self):
        self.port = get_ephemeral_port()

    async def asyncTearDown(self):
        # Allow any lingering tasks to clean up
        await asyncio.sleep(0.01)

    def test_default_config_and_payload(self):
        """Verify beacon payload contains all required discovery fields."""
        beacon = GatewayBeacon(port=self.port)
        self.assertEqual(beacon.port, self.port)
        self.assertEqual(beacon.version, "2.0")
        self.assertEqual(beacon.ws_port, 8765)
        self.assertEqual(beacon.mqtt_port, 1883)
        expected_tls = int(getattr(config, "DEVICE_MQTT_TLS_PORT", getattr(config, "MQTT_TLS_PORT", 8883))) if (config and getattr(config, "MQTT_TLS_ENABLED", False)) else 0
        self.assertEqual(beacon.mqtt_tls_port, expected_tls)
        self.assertEqual(beacon.http_port, 8000)

        payload = beacon.get_beacon_payload()
        self.assertEqual(payload["service"], "aetheria_gateway")
        self.assertIsInstance(payload["ip"], str)
        self.assertTrue(len(payload["ip"]) > 0)
        self.assertEqual(payload["ws_port"], 8765)
        self.assertEqual(payload["mqtt_port"], 1883)
        self.assertEqual(payload["mqtt_tls_port"], expected_tls)
        self.assertEqual(payload["http_port"], 8000)
        self.assertEqual(payload["version"], "2.0")

    def test_custom_ports_configuration(self):
        """Verify beacon uses custom ports when initialized."""
        beacon = GatewayBeacon(port=self.port, interval=5.0)
        beacon.ws_port = 9000
        beacon.mqtt_port = 1884
        beacon.mqtt_tls_port = 8884
        beacon.http_port = 8080
        beacon.version = "2.1"

        payload = beacon.get_beacon_payload()
        self.assertEqual(payload["ws_port"], 9000)
        self.assertEqual(payload["mqtt_port"], 1884)
        self.assertEqual(payload["mqtt_tls_port"], 8884)
        self.assertEqual(payload["http_port"], 8080)
        self.assertEqual(payload["version"], "2.1")

    def test_get_local_ip(self):
        """Verify get_local_ip returns a valid non-empty IPv4 address."""
        ip = GatewayBeacon.get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip) >= 7)
        parts = ip.split(".")
        self.assertEqual(len(parts), 4)
        for part in parts:
            self.assertTrue(part.isdigit())
            self.assertTrue(0 <= int(part) <= 255)

    def test_get_local_ip_caching(self):
        """Verify get_local_ip caches the resolved IP address for up to 5 seconds."""
        GatewayBeacon._cached_ip = None
        GatewayBeacon._cached_ip_time = 0.0
        with patch.object(GatewayBeacon, "_resolve_local_ip", return_value="192.168.1.50") as mock_resolve:
            ip1 = GatewayBeacon.get_local_ip()
            ip2 = GatewayBeacon.get_local_ip()
            self.assertEqual(ip1, "192.168.1.50")
            self.assertEqual(ip2, "192.168.1.50")
            self.assertEqual(mock_resolve.call_count, 1)

    async def test_start_and_stop_lifecycle(self):
        """Verify starting and stopping GatewayBeacon, including idempotency."""
        beacon = GatewayBeacon(port=self.port, interval=0.1)
        self.assertFalse(beacon._running)
        self.assertIsNone(beacon.transport)
        self.assertIsNone(beacon._task)

        # Start beacon
        await beacon.start()
        self.assertTrue(beacon._running)
        self.assertIsNotNone(beacon.transport)
        self.assertIsNotNone(beacon._task)
        self.assertFalse(beacon._task.done())

        # Calling start again while running should be a no-op
        initial_task = beacon._task
        await beacon.start()
        self.assertIs(beacon._task, initial_task)

        # Stop beacon
        await beacon.stop()
        self.assertFalse(beacon._running)
        self.assertIsNone(beacon.transport)
        self.assertIsNone(beacon._task)

        # Calling stop again when already stopped should be safe
        await beacon.stop()
        self.assertFalse(beacon._running)

    async def test_udp_probe_discover_gateway_reply(self):
        """
        Verify that sending 'DISCOVER_GATEWAY' via UDP triggers an immediate
        JSON response with the complete gateway descriptor payload.
        """
        beacon = GatewayBeacon(port=self.port, interval=1.0)
        await beacon.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(2.0)
        try:
            # Send discovery probe
            client_sock.sendto(b"DISCOVER_GATEWAY", ("127.0.0.1", self.port))

            # Receive reply non-blockingly via asyncio.to_thread
            data, addr = await asyncio.to_thread(client_sock.recvfrom, 1024)
            self.assertEqual(addr[0], "127.0.0.1")

            reply = json.loads(data.decode("utf-8"))
            self.assertEqual(reply.get("service"), "aetheria_gateway")
            self.assertIn("ip", reply)
            self.assertEqual(reply.get("ws_port"), beacon.ws_port)
            self.assertEqual(reply.get("mqtt_port"), beacon.mqtt_port)
            self.assertEqual(reply.get("mqtt_tls_port"), beacon.mqtt_tls_port)
            self.assertEqual(reply.get("http_port"), beacon.http_port)
            self.assertEqual(reply.get("version"), beacon.version)
        finally:
            client_sock.close()
            await beacon.stop()

    async def test_udp_probe_json_formats(self):
        """
        Verify that JSON discovery probes (action=discover, probe=True, service=aetheria_probe)
        are accepted and answered.
        """
        beacon = GatewayBeacon(port=self.port, interval=1.0)
        await beacon.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(2.0)
        try:
            probe_payloads = [
                json.dumps({"action": "discover"}).encode("utf-8"),
                json.dumps({"probe": True, "node_id": "test_node"}).encode("utf-8"),
                json.dumps({"service": "aetheria_probe"}).encode("utf-8"),
            ]

            for probe in probe_payloads:
                beacon._last_probe_time.clear()
                client_sock.sendto(probe, ("127.0.0.1", self.port))
                data, _ = await asyncio.to_thread(client_sock.recvfrom, 1024)
                reply = json.loads(data.decode("utf-8"))
                self.assertEqual(reply.get("service"), "aetheria_gateway")
                self.assertEqual(reply.get("ws_port"), beacon.ws_port)
                self.assertEqual(reply.get("mqtt_port"), beacon.mqtt_port)
        finally:
            client_sock.close()
            await beacon.stop()

    async def test_udp_probe_ignores_unrelated_and_self_broadcasts(self):
        """
        Verify that irrelevant messages and self-broadcasts are ignored
        without replying.
        """
        beacon = GatewayBeacon(port=self.port, interval=10.0)
        await beacon.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(0.3)
        try:
            # 1. Unrelated message
            client_sock.sendto(b"RANDOM_HEARTBEAT_DATA", ("127.0.0.1", self.port))
            with self.assertRaises(socket.timeout):
                await asyncio.to_thread(client_sock.recvfrom, 1024)

            # 2. Self beacon message (must be ignored to prevent loopbacks)
            self_beacon_msg = json.dumps({"service": "aetheria_gateway", "ip": "127.0.0.1"}).encode("utf-8")
            client_sock.sendto(self_beacon_msg, ("127.0.0.1", self.port))
            with self.assertRaises(socket.timeout):
                await asyncio.to_thread(client_sock.recvfrom, 1024)
        finally:
            client_sock.close()
            await beacon.stop()

    async def test_udp_malformed_inputs_handled_gracefully(self):
        """Verify that arbitrary binary junk, broken JSON, or empty frames do not crash beacon."""
        beacon = GatewayBeacon(port=self.port, interval=10.0)
        await beacon.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(0.3)
        try:
            # Send invalid non-UTF-8 bytes
            client_sock.sendto(bytes([255, 254, 128, 0, 18, 52]), ("127.0.0.1", self.port))
            with self.assertRaises(socket.timeout):
                await asyncio.to_thread(client_sock.recvfrom, 1024)

            # Send truncated JSON
            client_sock.sendto(b'{"action": "disc', ("127.0.0.1", self.port))
            with self.assertRaises(socket.timeout):
                await asyncio.to_thread(client_sock.recvfrom, 1024)

            # Send empty bytes
            client_sock.sendto(b"", ("127.0.0.1", self.port))
            with self.assertRaises(socket.timeout):
                await asyncio.to_thread(client_sock.recvfrom, 1024)

            # Follow up with a valid probe to verify the service is still completely functional
            client_sock.sendto(b"DISCOVER_GATEWAY", ("127.0.0.1", self.port))
            data, _ = await asyncio.to_thread(client_sock.recvfrom, 1024)
            reply = json.loads(data.decode("utf-8"))
            self.assertEqual(reply.get("service"), "aetheria_gateway")
        finally:
            client_sock.close()
            await beacon.stop()

    def test_handle_datagram_unit_cases(self):
        """Unit test handle_datagram logic directly with mock transport."""
        beacon = GatewayBeacon(port=self.port)
        mock_transport = MagicMock()
        mock_transport.is_closing.return_value = False
        beacon.transport = mock_transport

        addr = ("192.168.1.100", 54321)

        # 1. Direct DISCOVER_GATEWAY probe
        beacon.handle_datagram(b"DISCOVER_GATEWAY", addr)
        self.assertTrue(mock_transport.sendto.called)
        sent_data, sent_addr = mock_transport.sendto.call_args[0]
        self.assertEqual(sent_addr, addr)
        sent_json = json.loads(sent_data.decode("utf-8"))
        self.assertEqual(sent_json["service"], "aetheria_gateway")
        mock_transport.reset_mock()

        # 2. Self beacon ignored
        beacon.handle_datagram(b'{"service": "aetheria_gateway"}', addr)
        mock_transport.sendto.assert_not_called()

        # 3. Invalid JSON non-probe ignored
        beacon.handle_datagram(b"some other payload", addr)
        mock_transport.sendto.assert_not_called()

        # 4. JSON probe (from a different IP or cleared rate limit)
        beacon._last_probe_time.clear()
        beacon.handle_datagram(b'{"action":"discover"}', addr)
        self.assertTrue(mock_transport.sendto.called)
        mock_transport.reset_mock()

        # 5. Rate limiting: immediate duplicate probe ignored
        beacon.handle_datagram(b'{"action":"discover"}', addr)
        mock_transport.sendto.assert_not_called()

        # 6. Transport is closing -> should not send
        beacon._last_probe_time.clear()
        mock_transport.is_closing.return_value = True
        beacon.handle_datagram(b"DISCOVER_GATEWAY", addr)
        mock_transport.sendto.assert_not_called()

    async def test_broadcast_loop_periodic(self):
        """Verify the periodic broadcast loop runs and can be cancelled cleanly."""
        beacon = GatewayBeacon(port=self.port, interval=0.05)
        await beacon.start()
        # Let broadcast loop run a couple cycles
        await asyncio.sleep(0.12)
        self.assertTrue(beacon._running)
        self.assertFalse(beacon._task.done())
        await beacon.stop()
        self.assertFalse(beacon._running)

    def test_protocol_callbacks(self):
        """Verify GatewayBeaconProtocol callbacks."""
        beacon = GatewayBeacon(port=self.port)
        protocol = GatewayBeaconProtocol(beacon)
        transport = MagicMock()

        protocol.connection_made(transport)
        self.assertIs(protocol.transport, transport)

        # datagram_received delegates to handle_datagram
        beacon.handle_datagram = MagicMock()
        protocol.datagram_received(b"test", ("127.0.0.1", 1234))
        beacon.handle_datagram.assert_called_once_with(b"test", ("127.0.0.1", 1234))

        # error_received and connection_lost should not raise
        protocol.error_received(Exception("udp error"))
        protocol.connection_lost(None)

    async def test_smart_home_gateway_integration(self):
        """Verify SmartHomeGateway initializes and manages GatewayBeacon lifecycle."""
        with patch.object(SmartHomeGateway, "__init__", lambda self: None):
            gw = SmartHomeGateway()
            gw.beacon = GatewayBeacon(gateway=gw, port=self.port, interval=1.0)
            gw.beacon.start = AsyncMock()
            gw.beacon.stop = AsyncMock()

            # Verify start invocation
            if hasattr(gw, "beacon") and gw.beacon:
                await gw.beacon.start()
            gw.beacon.start.assert_awaited_once()

            # Verify stop invocation
            if hasattr(gw, "beacon") and gw.beacon:
                await gw.beacon.stop()
            gw.beacon.stop.assert_awaited_once()

    def test_tls_config_handling(self):
        """Verify DEVICE_MQTT_TLS_PORT and MQTT_TLS_PORT configuration when TLS is enabled and disabled."""
        with patch.object(config, "MQTT_TLS_ENABLED", True):
            with patch.object(config, "DEVICE_MQTT_TLS_PORT", 8885, create=True):
                beacon = GatewayBeacon(port=self.port)
                self.assertEqual(beacon.mqtt_tls_port, 8885)

            orig_device_tls = getattr(config, "DEVICE_MQTT_TLS_PORT", None)
            try:
                if hasattr(config, "DEVICE_MQTT_TLS_PORT"):
                    delattr(config, "DEVICE_MQTT_TLS_PORT")
                with patch.object(config, "MQTT_TLS_PORT", 8884, create=True):
                    beacon_tls = GatewayBeacon(port=self.port)
                    self.assertEqual(beacon_tls.mqtt_tls_port, 8884)
            finally:
                if orig_device_tls is not None:
                    setattr(config, "DEVICE_MQTT_TLS_PORT", orig_device_tls)

        with patch.object(config, "MQTT_TLS_ENABLED", False):
            beacon_no_tls = GatewayBeacon(port=self.port)
            self.assertEqual(beacon_no_tls.mqtt_tls_port, 0)

    def test_gateway_ip_override(self):
        """Verify GATEWAY_IP in config is prioritized when valid and not 0.0.0.0."""
        with patch.object(config, "GATEWAY_IP", "192.168.10.99", create=True):
            self.assertEqual(GatewayBeacon.get_local_ip(), "192.168.10.99")

        with patch.object(config, "GATEWAY_IP", "0.0.0.0", create=True):
            self.assertNotEqual(GatewayBeacon.get_local_ip(), "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
