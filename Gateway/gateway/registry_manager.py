"""
Device Registry Manager — CRUD operations for device_registry.json
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import config

logger = logging.getLogger("registry")
TZ_VN = timezone(timedelta(hours=7))


class RegistryManager:
    """Manages dynamic device registration and lookup."""
    
    def __init__(self, registry_path: str = None):
        self.path = registry_path or config.REGISTRY_FILE
        self.data = {"nodes": {}}
        self.load()
    
    def load(self):
        """Load registry from JSON file."""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            logger.info(f"Registry loaded: {len(self.data.get('nodes', {}))} nodes")
        else:
            self.save()
            logger.info("Created empty registry file")
    
    def save(self):
        """Persist registry to JSON file."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def register_node(self, node_id: str, mac: str, channels: dict = None,
                      area: str = None, description: str = None) -> dict:
        """
        Register a new node or update existing.
        Called when ESP32 sends registration message via MQTT.
        """
        now = datetime.now(TZ_VN).isoformat()
        
        if node_id in self.data["nodes"]:
            # Update existing node
            node = self.data["nodes"][node_id]
            node["last_seen"] = now
            node["mac"] = mac
            node["status"] = "online"
            if area:
                node["area"] = area
            if description:
                node["description"] = description
            if channels:
                node["channels"].update(channels)
            logger.info(f"Node updated: {node_id} (area: {node.get('area')})")
        else:
            # New node
            self.data["nodes"][node_id] = {
                "mac": mac,
                "area": area or "unknown",
                "description": description or f"Node {node_id}",
                "channels": channels or {},
                "sensors": {"pzem": True, "temperature": False},
                "registered_at": now,
                "last_seen": now,
                "status": "online",
            }
            logger.info(f"New node registered: {node_id} (area: {area})")
        
        self.save()
        return self.data["nodes"][node_id]
    
    def configure_node(self, node_id: str, area: str, description: str,
                       channel_config: dict) -> bool:
        """
        Configure a pending node with area and device mapping.
        Called when user says: "Node mới ở ban công, ổ 1 là đèn ban công"
        """
        if node_id not in self.data["nodes"]:
            logger.error(f"Node not found: {node_id}")
            return False
        
        node = self.data["nodes"][node_id]
        node["area"] = area
        node["description"] = description
        node["status"] = "online"
        
        for ch_id, ch_info in channel_config.items():
            node["channels"][ch_id] = ch_info
        
        self.save()
        logger.info(f"Node configured: {node_id} → {area}")
        return True
    
    def find_node_by_device(self, device_type: str, area: str = None) -> Optional[tuple]:
        """
        Find node_id and channel for a given device_type + area.
        Handles aliases and fuzzy matching.
        e.g.:
          device_type="den" or "den_ngu", area="phong_ngu" -> ("esp32s3_master", "ch1")
          device_type="quat" or "quat_ngu" or "quat_tran", area="phong_ngu" -> ("esp32s3_master", "ch2")
          area=None or "" -> fallback to any online node matching device
        """
        dev_norm = (device_type or "").lower().strip()
        area_norm = (area or "").lower().strip()

        # Helper to check if a channel matches device query
        def matches_channel(ch_info: dict) -> bool:
            c_type = ch_info.get("device_type", "").lower()
            c_desc = ch_info.get("description", "").lower()
            aliases = [str(a).lower() for a in ch_info.get("aliases", [])]

            if dev_norm in [c_type, c_desc] or dev_norm in aliases:
                return True
            # Partial substring matching: "den" in "den_ngu", "quat" in "quat_tran"
            if (c_type and c_type in dev_norm) or (dev_norm and dev_norm in c_type):
                return True
            if any(a in dev_norm or dev_norm in a for a in aliases):
                return True
            return False

        # Helper to check if node matches area
        def matches_area(node: dict) -> bool:
            if not area_norm or area_norm in ["all", "any", "none"]:
                return True  # No specific area specified -> match
            n_area = node.get("area", "").lower()
            aliases = [str(a).lower() for a in node.get("aliases", [])]
            if area_norm == n_area or area_norm in n_area or n_area in area_norm:
                return True
            if any(area_norm in a or a in area_norm for a in aliases):
                return True
            return False

        # Pass 1: Matching area + matching device
        for node_id, node in self.data["nodes"].items():
            if node.get("status") != "online":
                continue
            if matches_area(node):
                for ch_id, ch_info in node.get("channels", {}).items():
                    if matches_channel(ch_info):
                        return (node_id, ch_id)

        # Pass 2: Fallback if area didn't match, search across any online node
        if area_norm:
            for node_id, node in self.data["nodes"].items():
                if node.get("status") != "online":
                    continue
                for ch_id, ch_info in node.get("channels", {}).items():
                    if matches_channel(ch_info):
                        return (node_id, ch_id)

        return None
    
    def get_rated_watts(self, node_id: str, channel: str) -> float:
        """Get rated watts for a specific channel (used by verify engine)."""
        node = self.data["nodes"].get(node_id, {})
        ch = node.get("channels", {}).get(channel, {})
        return ch.get("rated_watts", 0)
    
    def update_heartbeat(self, node_id: str):
        """Update last_seen timestamp for a node."""
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["last_seen"] = (
                datetime.now(TZ_VN).isoformat()
            )
            self.data["nodes"][node_id]["status"] = "online"
    
    def get_all_nodes(self) -> dict:
        """Return all registered nodes."""
        return self.data.get("nodes", {})
    
    def get_online_nodes(self) -> dict:
        """Return only online nodes."""
        return {
            nid: n for nid, n in self.data.get("nodes", {}).items()
            if n.get("status") == "online"
        }
    
    def mark_offline(self, node_id: str):
        """Mark a node as offline (heartbeat timeout)."""
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["status"] = "offline"
            logger.warning(f"Node marked offline: {node_id}")
