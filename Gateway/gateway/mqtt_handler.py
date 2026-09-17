"""
DTV Smart Home Gateway — MQTT Handler
Manages connection to EMQX broker, topic subscriptions,
command dispatch, and telemetry caching.
"""

import asyncio
import json
import logging
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

    def on_message(self, topic_pattern: str, callback: Callable):
        """Register an async or sync callback for a topic pattern."""
        if topic_pattern not in self.callbacks:
            self.callbacks[topic_pattern] = []
        self.callbacks[topic_pattern].append(callback)
        logger.debug(f"Registered MQTT callback for pattern: {topic_pattern}")

    def get_current_power(self, node_id: str) -> float:
        """Get the latest recorded power (watts) for a node."""
        return self.latest_power.get(node_id, 0.0)

    async def send_command(self, node_id: str, channel: str, action: str,
                           seq: int = None) -> bool:
        """
        Send a control command to a node via MQTT (compact v2).
        Topic: smarthome/cmd/{node_id}
        Payload: {"t":"rl","ch":1,"s":1,"seq":n}   (protocol_spec.md)

        Kênh cũ smarthome/command/{node_id} vẫn gửi {channel, action} cho firmware
        legacy chưa nâng cấp lên compact protocol.
        """
        # Map channel names -> channel number
        ch_number = {"ch1": 1, "ch2": 2, 1: 1, 2: 2}.get(channel, 0)
        if ch_number in (1, 2):
            s = 1 if action in ("turn_on", "open", "on") else 0
            payload = {"t": "rl", "ch": ch_number, "s": s, "seq": seq or 0}
            topic = config.TOPIC_CMD_SHORT.format(node_id=node_id)
            ok = await self.publish(topic, payload)
            if ok:
                logger.info(f"📤 CMD[compact] {node_id} ch{ch_number}={s} seq={seq}")
            return ok
        # legacy
        topic = config.TOPIC_COMMAND.format(node_id=node_id)
        payload = {"channel": channel, "action": action}
        return await self.publish(topic, payload)

    async def send_cfg(self, mac_or_id: str, cfg_payload: dict) -> bool:
        """Gửi gói provision/cfg xuống node. QoS 1 + retain để node offline vẫn nhận khi boot."""
        topic = config.TOPIC_CFG.format(mac_or_id=mac_or_id)
        return await self.publish(topic, cfg_payload, qos=1, retain=True)

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
            logger.info(f"📤 Published to {topic}: {payload_str}")
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
        # e.g. topic: smarthome/telemetry/esp32s3_master  or smarthome/tele/{node_id}
        if topic.startswith("smarthome/telemetry/") or topic.startswith("smarthome/tele/"):
            node_id = topic.split("/")[-1]
            if isinstance(payload, dict):
                self.latest_telemetry[node_id] = payload
                # compact keys: p / power
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
