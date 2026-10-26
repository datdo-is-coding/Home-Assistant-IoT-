"""
Gateway Beacon — Automatic Gateway Discovery Service
===================================================
Broadcasts Gateway IP and service ports via UDP on port 5005 every 3 seconds,
and listens for discovery probe requests from SubBox / IoT nodes to provide
instant unicast replies.
"""

import asyncio
import json
import logging
import re
import socket
import subprocess
import time
from typing import Optional, Dict, Any

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("beacon")


class GatewayBeaconProtocol(asyncio.DatagramProtocol):
    """Protocol handler for UDP Datagrams on Beacon port."""

    def __init__(self, beacon: "GatewayBeacon"):
        self.beacon = beacon
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        self.beacon.handle_datagram(data, addr)

    def error_received(self, exc: Exception):
        logger.debug("GatewayBeacon socket error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]):
        pass


class GatewayBeacon:
    """
    Automatic UDP Beacon and Discovery Responder for Aetheria Smart Home Gateway.
    """

    _cached_ip: Optional[str] = None
    _cached_ip_time: float = 0.0

    def __init__(self, gateway=None, port: int = 5005, interval: float = 3.0):
        self.gateway = gateway
        self.port = port
        self.interval = interval

        self.ws_port = int(getattr(config, "WS_AUDIO_PORT", 8765)) if config else 8765
        self.mqtt_port = int(getattr(config, "MQTT_PORT", 1883)) if config else 1883
        if config and getattr(config, "MQTT_TLS_ENABLED", False):
            self.mqtt_tls_port = int(getattr(config, "DEVICE_MQTT_TLS_PORT", getattr(config, "MQTT_TLS_PORT", 8883)))
        else:
            self.mqtt_tls_port = 0
        self.http_port = int(getattr(config, "WEB_PORT", 8000)) if config else 8000
        self.version = "2.0"

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.protocol: Optional[GatewayBeaconProtocol] = None
        self._sock: Optional[socket.socket] = None
        self._last_probe_time: Dict[str, float] = {}

    @classmethod
    def get_local_ip(cls) -> str:
        """Resolve current LAN IP address without contacting external servers."""
        if config:
            gw_ip = getattr(config, "GATEWAY_IP", "")
            if gw_ip and gw_ip != "0.0.0.0":
                return gw_ip

        now = time.monotonic()
        if cls._cached_ip and (now - cls._cached_ip_time < 5.0):
            return cls._cached_ip

        ip = cls._resolve_local_ip()
        cls._cached_ip = ip
        cls._cached_ip_time = now
        return ip

    @classmethod
    def _resolve_local_ip(cls) -> str:
        for probe_dest, probe_port in (
            ("10.255.255.255", 1),
            ("172.31.255.255", 1),
            ("192.168.255.255", 1),
            ("8.8.8.8", 1),
        ):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect((probe_dest, probe_port))
                    candidate = s.getsockname()[0]
                    if (
                        candidate
                        and not candidate.startswith("127.")
                        and not candidate.startswith("169.254.")
                        and candidate != "0.0.0.0"
                    ):
                        return candidate
            except Exception:
                continue

        # Inspect system interfaces via ip -4 addr show to find non-loopback IPv4 address on eth0, wlan0, or en0
        try:
            proc = subprocess.run(
                ["ip", "-4", "addr", "show"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if proc.returncode == 0:
                current_iface = ""
                for line in proc.stdout.splitlines():
                    match_iface = re.match(r"^\d+:\s+([a-zA-Z0-9_-]+):", line)
                    if match_iface:
                        current_iface = match_iface.group(1)
                    match_inet = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", line)
                    if match_inet and current_iface:
                        addr = match_inet.group(1)
                        if (
                            not addr.startswith("127.")
                            and not addr.startswith("169.254.")
                            and addr != "0.0.0.0"
                        ):
                            if any(current_iface.startswith(pfx) for pfx in ("eth", "wlan", "en", "wl")):
                                return addr
        except Exception:
            pass

        try:
            candidate = socket.gethostbyname(socket.gethostname())
            if (
                candidate
                and not candidate.startswith("127.")
                and not candidate.startswith("169.254.")
                and candidate != "0.0.0.0"
            ):
                return candidate
        except Exception:
            pass

        return "127.0.0.1"

    def get_beacon_payload(self) -> Dict[str, Any]:
        """Construct the gateway discovery beacon payload."""
        return {
            "service": "aetheria_gateway",
            "ip": self.get_local_ip(),
            "ws_port": self.ws_port,
            "mqtt_port": self.mqtt_port,
            "mqtt_tls_port": self.mqtt_tls_port,
            "http_port": self.http_port,
            "version": self.version,
        }

    async def start(self):
        """Bind UDP socket and start broadcast background loop."""
        if self._running:
            return

        self._running = True
        try:
            loop = asyncio.get_running_loop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock = sock
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self.port))
            sock.setblocking(False)

            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: GatewayBeaconProtocol(self),
                sock=sock,
            )
            self._task = asyncio.create_task(self._broadcast_loop())
            logger.info(
                "GatewayBeacon active on UDP port %d (LAN IP: %s, broadcast every %.1fs)",
                self.port,
                self.get_local_ip(),
                self.interval,
            )
        except Exception as e:
            logger.error("Failed to start GatewayBeacon on UDP port %d: %s", self.port, e)
            if self._sock:
                self._sock.close()
                self._sock = None
            self._running = False

    async def stop(self):
        """Stop broadcast loop and release UDP socket."""
        if not self._running:
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("GatewayBeacon stop error: %s", e)
            self._task = None

        if self.transport and not self.transport.is_closing():
            try:
                self.transport.close()
            except Exception:
                pass
            self.transport = None

        self._sock = None
        logger.info("GatewayBeacon stopped.")

    async def _broadcast_loop(self):
        """Periodically broadcast beacon message to LAN."""
        while self._running:
            try:
                payload = json.dumps(self.get_beacon_payload()).encode("utf-8")
                if self.transport and not self.transport.is_closing():
                    self.transport.sendto(payload, ("255.255.255.255", self.port))
            except Exception as e:
                logger.debug("Beacon broadcast send error: %s", e)

            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    def handle_datagram(self, data: bytes, addr):
        """
        Handle incoming probe request from client.
        Replies directly if request is DISCOVER_GATEWAY or probe JSON.
        """
        try:
            # Ignore self-broadcasts and other gateway beacons
            if b'"service": "aetheria_gateway"' in data or b'"service":"aetheria_gateway"' in data:
                return

            text = data.decode("utf-8", errors="ignore").strip()
            is_probe = False

            if "DISCOVER_GATEWAY" in text:
                is_probe = True
            else:
                try:
                    js = json.loads(text)
                    if isinstance(js, dict):
                        if (
                            js.get("action") == "discover"
                            or js.get("probe")
                            or js.get("service") == "aetheria_probe"
                        ):
                            is_probe = True
                except Exception:
                    pass

            if is_probe and self.transport and not self.transport.is_closing():
                client_ip = addr[0] if isinstance(addr, (list, tuple)) and len(addr) > 0 else str(addr)
                now = time.monotonic()
                if now - self._last_probe_time.get(client_ip, 0.0) < 0.5:
                    logger.debug("Rate-limiting discovery probe response to %s", client_ip)
                    return
                if len(self._last_probe_time) > 256:
                    self._last_probe_time = {k: v for k, v in self._last_probe_time.items() if now - v < 5.0}
                self._last_probe_time[client_ip] = now

                logger.info("Responding to discovery probe from %s:%s", addr[0], addr[1])
                payload = json.dumps(self.get_beacon_payload()).encode("utf-8")
                self.transport.sendto(payload, addr)
        except Exception as e:
            logger.debug("Error handling beacon datagram from %s: %s", addr, e)
