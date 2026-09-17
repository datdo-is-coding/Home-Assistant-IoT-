"""
Discovery Manager — Home Assistant Compatible MQTT Discovery & Zero-Touch Device Pairing
========================================================================================
Handles:
  1. Listening for Home Assistant format discovery configs:
     `homeassistant/switch/<node_id>/<object_id>/config`
     `homeassistant/sensor/<node_id>/<object_id>/config`
  2. Listening for native device announcements:
     `smarthome/discovery/<node_id>` and `smarthome/hello`
  3. Managing discovered pending devices for 1-Click pairing on Web UI.
  4. Publishing Home Assistant discovery topics for all registered nodes in Gateway
     so external Home Assistant instances can also automatically see all IoT devices.
"""

import json
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("discovery")


class DiscoveryManager:
    """Manages Home Assistant style MQTT discovery and device auto-pairing."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        # node_id -> discovery metadata dict
        self.discovered_devices: Dict[str, Dict[str, Any]] = {}

    def handle_ha_discovery(self, topic: str, payload: Any):
        """
        Parse incoming MQTT message with Home Assistant Discovery format:
        topic: homeassistant/<component>/<node_id>/<object_id>/config
        """
        try:
            parts = topic.split("/")
            if len(parts) < 5 or parts[-1] != "config":
                return

            component = parts[1]      # switch, light, sensor, etc.
            node_id = parts[2]
            object_id = parts[3]

            if not payload:
                # HA convention: empty payload means device unregistration
                self.discovered_devices.pop(node_id, None)
                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                    self.gateway.broadcast_event("discovery_removed", {"node_id": node_id})
                return

            if isinstance(payload, dict):
                data = payload
            elif isinstance(payload, str):
                if not payload.strip():
                    self.discovered_devices.pop(node_id, None)
                    return
                data = json.loads(payload)
            else:
                return

            dev_info = data.get("device", {})
            mac = None
            for ident in dev_info.get("identifiers", []):
                if ":" in ident or "-" in ident:
                    mac = ident.upper()
                    break

            device_name = dev_info.get("name") or data.get("name") or node_id
            model = dev_info.get("model", "ESP32")

            existing = self.discovered_devices.get(node_id, {
                "node_id": node_id,
                "mac": mac,
                "name": device_name,
                "model": model,
                "components": {},
                "discovered_at": time.time(),
            })
            existing["components"][object_id] = {
                "type": component,
                "name": data.get("name", object_id),
                "cmd_t": data.get("command_topic"),
                "stat_t": data.get("state_topic"),
            }
            self.discovered_devices[node_id] = existing

            logger.info(f"✨ HA Discovery: Found device '{node_id}' ({device_name}) with {component}/{object_id}")

            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("device_discovered", existing)

        except Exception as e:
            logger.warning(f"Error parsing HA discovery message ({topic}): {e}")

    def handle_native_discovery(self, topic: str, payload: Any):
        """
        Parse native DTV discovery message:
        topic: smarthome/discovery/<node_id>
        payload: {"mac":"...","ip":"...","chip":"ESP32-S3","channels":{"ch1":"light","ch2":"fan"},"room":"phong_ngu"}
        """
        try:
            node_id = topic.split("/")[-1]
            if isinstance(payload, dict):
                data = payload
            elif isinstance(payload, str):
                data = json.loads(payload) if payload.strip() else {}
            else:
                data = {}
            mac = (data.get("mac") or "").upper()

            disc = {
                "node_id": node_id,
                "mac": mac,
                "name": data.get("name") or f"ESP32 ({node_id})",
                "ip": data.get("ip"),
                "chip": data.get("chip", "ESP32"),
                "channels": data.get("channels", {"ch1": "light", "ch2": "fan"}),
                "sensors": data.get("sensors", []),
                "suggested_room": data.get("room"),
                "discovered_at": time.time()
            }
            self.discovered_devices[node_id] = disc
            logger.info(f"✨ Native Discovery: Found '{node_id}' [{mac}] IP {disc.get('ip')}")

            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("device_discovered", disc)

        except Exception as e:
            logger.warning(f"Error parsing native discovery message: {e}")

    def get_discovered_devices(self) -> Dict[str, Any]:
        """Return all discovered devices that are not yet in permanent registry."""
        reg_nodes = {}
        if self.gateway and hasattr(self.gateway, "registry") and self.gateway.registry:
            reg_nodes = self.gateway.registry.get_all_nodes()

        unregistered = {}
        for nid, dev in self.discovered_devices.items():
            if nid not in reg_nodes:
                unregistered[nid] = dev
        return unregistered

    async def pair_device(self, node_id: str, room: str, rl1: str = "light", rl2: str = "fan") -> dict:
        """
        1-Click pairing: registers a discovered device into the permanent registry
        and broadcasts HA discovery configs.
        """
        if not self.gateway or not hasattr(self.gateway, "registry"):
            return {"success": False, "error": "Registry not available"}

        dev = self.discovered_devices.get(node_id, {})
        mac = (dev.get("mac") or f"00:00:00:{abs(hash(node_id))%0xFFFFFF:06X}").upper()

        reg = getattr(self.gateway, "registry", None)
        if reg and mac not in reg.get_pending():
            reg.data.setdefault("pending", {})[mac] = {
                "mac": mac,
                "rl": [0, 0],
                "seen": time.time(),
                "ip": dev.get("ip"),
                "node_id": node_id
            }

        # Register into permanent registry
        res = await self.gateway.provision_pending(
            mac=mac, room=room, rl1=rl1, rl2=rl2, node_short=node_id
        )

        if res.get("success"):
            # Remove from discovered cache
            self.discovered_devices.pop(node_id, None)
            # Publish HA Discovery announcements
            await self.publish_ha_discovery_for_node(res.get("node_id", node_id))
            if hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("device_paired", {"node_id": res.get("node_id")})

        return res

    async def publish_ha_discovery_for_node(self, node_id: str):
        """
        Publish standard Home Assistant discovery topics over MQTT
        so that any external Home Assistant instance auto-discovers this node.
        """
        if not self.gateway or not hasattr(self.gateway, "mqtt") or not self.gateway.mqtt:
            return

        reg = getattr(self.gateway, "registry", None)
        if not reg: return
        node = reg.get_all_nodes().get(node_id)
        if not node: return

        room = node.get("room", "livingroom")
        mac = node.get("mac", "30:ED:A0:BD:69:D4")
        channels = node.get("channels", {})

        dev_block = {
            "identifiers": [mac, node_id],
            "name": f"DTV SmartNode {node_id}",
            "model": "ESP32-S3 Voice/Relay Node",
            "manufacturer": "DTV IoT",
            "suggested_area": room,
            "sw_version": "2.1.0"
        }

        # Publish for each relay channel
        for ch_key, ch_val in channels.items():
            device_type = ch_val if isinstance(ch_val, str) else ch_val.get("device_type", "light")
            component = "light" if "light" in device_type or "den" in device_type else "switch"
            
            discovery_topic = f"homeassistant/{component}/{node_id}/{ch_key}/config"
            payload = {
                "name": f"{room.replace('_', ' ').title()} {device_type.replace('_', ' ').title()}",
                "unique_id": f"{node_id}_{ch_key}",
                "command_topic": f"smarthome/cmd/{node_id}",
                "state_topic": f"smarthome/status/{node_id}",
                "payload_on": json.dumps({"t": "rl", "ch": 1 if ch_key=="ch1" else 2, "s": 1}),
                "payload_off": json.dumps({"t": "rl", "ch": 1 if ch_key=="ch1" else 2, "s": 0}),
                "state_on": "1",
                "state_off": "0",
                "device": dev_block
            }
            try:
                await self.gateway.mqtt.client.publish(
                    discovery_topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=True
                )
                logger.info(f"📢 Published HA Discovery: {discovery_topic}")
            except Exception as e:
                logger.warning(f"Failed to publish HA discovery for {node_id}/{ch_key}: {e}")
