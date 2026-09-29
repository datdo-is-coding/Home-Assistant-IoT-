"""
DTV Smart Home Gateway — MQTT Handler
Manages connection to EMQX broker, topic subscriptions,
command dispatch, and telemetry caching.
"""

import asyncio
import json
import logging
import secrets
import time
import ssl
import math
import re
from typing import Callable, Dict, List, Any, Optional

try:
    import aiomqtt
except ImportError:
    aiomqtt = None

import config

logger = logging.getLogger("mqtt_handler")


def topic_matches(pattern: str, topic: str) -> bool:
    """
    Check if an MQTT topic matches a subscription pattern.
    Supports MQTT wildcards: '+' (single level) and '#' (multi level).
    """
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")

    i = 0
    for p in pattern_parts:
        if p == "#":
            return True
        if i >= len(topic_parts):
            return False
        if p != "+" and p != topic_parts[i]:
            return False
        i += 1
    return i == len(topic_parts)


class MQTTHandler:
    """Async MQTT Handler for DTV Smart Home Gateway."""

    def __init__(self):
        self.callbacks: Dict[str, List[Callable]] = {}
        self.client: Optional[Any] = None
        self._connected = asyncio.Event()
        self._running = False
        self.latest_telemetry: Dict[str, Dict[str, Any]] = {}
        self.latest_power: Dict[str, float] = {}
        self.session_id = secrets.randbits(32)
        self.node_routes = {}
        self.command_acks = {}
        self.load_reports = {}
        self.node_identities = {}
        self.conflicting_nodes = set()
        self.on_message("home/subbox/+/event/actionbox", self._on_actionbox)

    async def _on_actionbox(self, topic, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("node_id"), str):
            return
        node_id = payload["node_id"]
        uid = payload.get('hardware_uid')
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', node_id)
                or not isinstance(uid, str) or not re.fullmatch(r'[0-9A-Fa-f]{12}', uid)
                or payload.get('protocol_version') != 3
                or type(payload.get('config_version')) is not int or payload['config_version'] < 1):
            return
        uid = uid.upper()
        existing = self.node_identities.get(node_id)
        if existing and existing['hardware_uid'] != uid:
            self.conflicting_nodes.add(node_id)
            self.node_routes.pop(node_id, None)
            return
        if node_id in self.conflicting_nodes:
            return
        self.node_identities[node_id] = {'hardware_uid': uid, 'config_version': payload['config_version'], 'protocol_version': 3}
        self.node_routes[node_id] = (topic.split("/")[2], time.monotonic())
        channels = payload.get("channels")
        if isinstance(channels, list):
            powers = [c.get('power_w', 0) for c in channels if isinstance(c, dict)]
            if all(type(p) in (int, float) and math.isfinite(p) for p in powers):
                self.latest_power[node_id] = sum(powers)
        request = payload.get("request_id")
        if type(request) is int and payload.get('session_id') == self.session_id:
            if payload.get('type') == 'LOAD_REPORT':
                cache = self.load_reports
            elif payload.get('status') in ('OK', 'ERROR'):
                cache = self.command_acks
            else:
                return
            cache[(node_id, request)] = {**payload, '_received_at': time.monotonic()}
            while len(cache) > 128:
                cache.pop(next(iter(cache)))

    def subbox_route(self, node_id):
        route = self.node_routes.get(node_id)
        return route[0] if node_id not in self.conflicting_nodes and route and time.monotonic() - route[1] < 30 else None


    def on_message(self, topic_pattern: str, callback: Callable):
        """Register an async or sync callback for a topic pattern."""
        if topic_pattern not in self.callbacks:
            self.callbacks[topic_pattern] = []
        self.callbacks[topic_pattern].append(callback)
        logger.debug(f"Registered MQTT callback for pattern: {topic_pattern}")

    def record_compact_ack(self, node_id, payload):
        seq, states = payload.get("seq"), payload.get("rl")
        if isinstance(seq, int) and isinstance(states, list):
            self.command_acks[(node_id, seq)] = {"status": "OK", "relay_states": states}
            while len(self.command_acks) > 128:
                self.command_acks.pop(next(iter(self.command_acks)))

    def get_current_power(self, node_id: str) -> float:
        """Get the latest recorded power (watts) for a node."""
        return self.latest_power.get(node_id, 0.0)

    async def send_command(self, node_id: str, channel: str, action: str,
                           seq: int = None, settle_ms: int = 500) -> bool:
        """
        Send a control command to a node via MQTT (compact v2).
        Topic: smarthome/cmd/{node_id}
        Payload: {"t":"rl","ch":1,"s":1,"seq":n}   (protocol_spec.md)

        Kênh cũ smarthome/command/{node_id} vẫn gửi {channel, action} cho firmware
        legacy chưa nâng cấp lên compact protocol.
        """
        if action not in ('turn_on', 'on', 'open', 'turn_off', 'off', 'close') or node_id in self.conflicting_nodes:
            return False
        route = self.subbox_route(node_id)
        if route:
            channel_number = {"ch1": 1, "ch2": 2, "1": 1, "2": 2, 1: 1, 2: 2}.get(channel)
            command = {"turn_on": "TURN_ON", "on": "TURN_ON", "open": "TURN_ON",
                       "turn_off": "TURN_OFF", "off": "TURN_OFF", "close": "TURN_OFF"}.get(action)
            if not channel_number or not command:
                return False
            return await self.publish(f"home/subbox/{route}/command", {
                "version": 3, **self.node_identities[node_id], "node_id": node_id, "channel": channel_number,
                "settle_ms": settle_ms,
                "cmd": command, "request_id": seq or secrets.randbelow(0x7ffffffe) + 1, "session_id": self.session_id,
            }, qos=1)
        # A known three-tier device must never fall back to unrelated legacy topics.
        if node_id in self.node_identities:
            return False
        # Map channel names -> channel number
        ch_number = {"ch1": 1, "ch2": 2, "1": 1, "2": 2, 1: 1, 2: 2}.get(channel, 0)
        if ch_number in (1, 2):
            s = 1 if action in ("turn_on", "open", "on", "1", 1) else 0
            payload = {"t": "rl", "ch": ch_number, "s": s, "seq": seq or 0}
            topic = config.TOPIC_CMD_SHORT.format(node_id=node_id)
            ok = await self.publish(topic, payload)

            # Đồng thời gửi industrial topic (home/devices/{node_id}/relay/{ch}/set)
            ind_topic = f"home/devices/{node_id}/relay/{ch_number}/set"
            await self.publish(ind_topic, {"state": s})

            # 3-Tier Zone routing topic (picked up by T2 Zone Controller for T1 nodes)
            zone_node_topic = f"home/nodes/{node_id}/relay/{ch_number}/set"
            await self.publish(zone_node_topic, {"state": s})

            if ok:
                logger.info(f"📤 CMD[compact+ind+zone] {node_id} ch{ch_number}={s} seq={seq}")
            return ok
        # legacy
        topic = config.TOPIC_COMMAND.format(node_id=node_id)
        payload = {"channel": channel, "action": action}
        return await self.publish(topic, payload)

    async def send_cfg(self, mac_or_id: str, cfg_payload: dict) -> bool:
        """Gửi gói provision/cfg xuống node. QoS 1, retain=False để tránh node bị reboot loop vô tận khi broker lưu tin nhắn cũ."""
        topic = config.TOPIC_CFG.format(mac_or_id=mac_or_id)
        return await self.publish(topic, cfg_payload, qos=1, retain=False)

    async def send_desired_config(self, device_id: str, desired_payload: dict) -> bool:
        """
        Gửi Desired Configuration Twin xuống node theo Spec Section 4.
        Topic: home/devices/{device_id}/config/desired
        QoS 1, retain=True để thiết bị nhận ngay khi reconnect.
        """
        topic = getattr(config, "TOPIC_DEV_CONFIG_DESIRED", "home/devices/{device_id}/config/desired").format(device_id=device_id)
        ok = await self.publish(topic, desired_payload, qos=1, retain=True)
        if ok:
            logger.info(f"📤 Published Desired Twin to {topic}: v={desired_payload.get('version')}")
        return ok

    async def send_relay_set(self, device_id: str, channel: int, state: int) -> bool:
        """
        Điều khiển relay theo chuẩn Industrial Topic: home/devices/{device_id}/relay/{channel}/set
        Đồng thời gửi:
          - home/nodes/{device_id}/relay/{channel}/set (cho T2 Zone Controller route xuống T1)
          - smarthome/cmd/{device_id} (compact backward-compat)
        """
        if channel not in (1, 2) or state not in (0, 1):
            return False
        return await self.send_command(device_id, channel, 'turn_on' if state else 'turn_off')
        # Legacy fan-out removed: one selected route owns each command.
        topic = getattr(config, "TOPIC_DEV_RELAY_SET", "home/devices/{device_id}/relay/{channel}/set").format(
            device_id=device_id, channel=channel
        )
        payload = {"state": 1 if state else 0}
        ok = await self.publish(topic, payload, qos=1)

        # 3-Tier Zone routing topic (picked up by T2 Zone Controller for T1 nodes)
        zone_node_topic = f"home/nodes/{device_id}/relay/{channel}/set"
        await self.publish(zone_node_topic, payload, qos=1)

        # Compact backward-compat
        compact_topic = config.TOPIC_CMD_SHORT.format(node_id=device_id)
        await self.publish(compact_topic, {"t": "rl", "ch": channel, "s": 1 if state else 0, "seq": 0})
        return ok

    async def send_compact_status(self, node_id: str) -> bool:
        """Yêu cầu node echo trạng thái relay hiện tại."""
        topic = config.TOPIC_CMD_SHORT.format(node_id=node_id)
        return await self.publish(topic, {"t": "q", "seq": 0})

    async def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        """Publish a message to an MQTT topic."""
        if not self.client:
            logger.warning(f"Cannot publish to {topic}: MQTT client not initialized")
            return False

        if isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload, ensure_ascii=False)
        else:
            payload_str = str(payload)

        try:
            if not self._connected.is_set():
                logger.warning(f"MQTT not currently connected, waiting up to 5s before publish to {topic}...")
                await asyncio.wait_for(self._connected.wait(), timeout=5.0)

            await self.client.publish(topic, payload=payload_str, qos=qos, retain=retain)
            logger.debug('Published topic=%s bytes=%s', topic, len(payload_str))
            return True
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    async def connect(self):
        """
        Connect to MQTT broker and start listening loop.
        Auto-reconnects on connection loss.
        """
        if aiomqtt is None:
            raise RuntimeError("aiomqtt is not installed. Please run: pip install aiomqtt")

        self._running = True
        logger.info(f"Connecting to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}...")

        while self._running:
            try:
                client_kwargs = {
                    "hostname": config.MQTT_BROKER,
                    "port": config.MQTT_PORT,
                    "identifier": config.MQTT_CLIENT_ID,
                }
                if config.MQTT_USERNAME and config.MQTT_PASSWORD:
                    client_kwargs["username"] = config.MQTT_USERNAME
                    client_kwargs["password"] = config.MQTT_PASSWORD
                if getattr(config, 'MQTT_TLS_ENABLED', True):
                    ca = getattr(config, 'MQTT_CA_FILE', '')
                    if not ca:
                        raise ValueError('MQTT_CA_FILE is required for TLS')
                    context = ssl.create_default_context(cafile=ca)
                    if getattr(config, 'MQTT_CERT_FILE', ''):
                        context.load_cert_chain(config.MQTT_CERT_FILE, config.MQTT_KEY_FILE)
                    client_kwargs['tls_context'] = context

                async with aiomqtt.Client(**client_kwargs) as client:
                    self.client = client
                    self._connected.set()
                    logger.info("✅ Connected to MQTT broker (EMQX)")

                    # Subscribe to all registered topic patterns
                    for pattern in self.callbacks.keys():
                        await client.subscribe(pattern)
                        logger.info(f"📥 Subscribed to: {pattern}")

                    # Message listening loop
                    async for message in client.messages:
                        if not self._running:
                            break
                        asyncio.create_task(self._handle_message(message))

            except aiomqtt.MqttError as e:
                self._connected.clear()
                logger.warning(f"MQTT connection error: {e}. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected.clear()
                logger.error(f"Unexpected MQTT error: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)

        self._connected.clear()
        self.client = None
        logger.info("MQTT handler stopped")

    async def _handle_message(self, message):
        """Process an incoming MQTT message and dispatch to registered callbacks."""
        topic = str(message.topic)
        payload_raw = message.payload

        try:
            if isinstance(payload_raw, bytes):
                payload_str = payload_raw.decode("utf-8")
            else:
                payload_str = str(payload_raw)

            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                payload = payload_str
        except Exception as e:
            logger.warning(f"Failed to decode payload on {topic}: {e}")
            return

        # Update telemetry & power cache
        # e.g. topic: smarthome/telemetry/node_xxx, smarthome/tele/node_xxx, home/devices/node_xxx/telemetry
        node_id = None
        if topic.startswith("smarthome/telemetry/") or topic.startswith("smarthome/tele/"):
            node_id = topic.split("/")[-1]
        elif topic.startswith("home/devices/") and topic.endswith("/telemetry"):
            parts = topic.split("/")
            if len(parts) >= 4:
                node_id = parts[2]
        elif topic.startswith("home/") and (topic.endswith("/power") or topic.endswith("/status")):
            parts = topic.split("/")
            if len(parts) >= 4:
                node_id = parts[2]

        if node_id and isinstance(payload, dict):
            self.latest_telemetry[node_id] = payload
            power = payload.get("power", payload.get("p", None))
            if power is not None:
                try:
                    self.latest_power[node_id] = float(power)
                except (ValueError, TypeError):
                    pass

        # Compact relay ack: {"t":"ack","id":"...","rl":[1,0],"seq":n} on smarthome/status/{id}
        if topic.startswith("smarthome/status/") and isinstance(payload, dict) and payload.get("t") in ("ack","hello"):
            payload["_compact"] = True

        # Dispatch to matching callbacks
        matched = False
        for pattern, cbs in list(self.callbacks.items()):
            if topic_matches(pattern, topic):
                matched = True
                for cb in cbs:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(topic, payload)
                        else:
                            cb(topic, payload)
                    except Exception as e:
                        logger.error(f"Error in callback for {topic}: {e}", exc_info=True)

        if not matched:
            logger.debug(f"No callback matched for topic {topic}")

    async def disconnect(self):
        """Stop the MQTT handler."""
        self._running = False
        self._connected.clear()
