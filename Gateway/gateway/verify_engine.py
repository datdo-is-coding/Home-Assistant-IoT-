"""
Verify Engine — Command verification via correlated device acknowledgements.
Power telemetry is reported separately; an ACK confirms relay state, not load health.

🎯 CORE GOAL: This is the HEART of the closed-loop system.
"""

import asyncio
import logging
import secrets
from enum import Enum

import config
from display_names import get_room_name, get_device_name, clean_voice_text

logger = logging.getLogger("verify")


class VerifyResult(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CONFIRMED_LOAD = "confirmed_load"
    ACK_ONLY = "ack_only"
    MISMATCH = "mismatch"
    FAULT = "fault"


class CommandVerifier:
    """Require a device ACK before reporting an applied relay command."""

    def __init__(self, mqtt_handler, registry):
        self.mqtt = mqtt_handler
        self.registry = registry
        self.audio_server = None  # set by main.py — ưu tiên WS TEXT frame

    async def _dispatch(self, node_id: str, channel: str, action: str, seq: int) -> str:
        """
        Gửi relay: ưu tiên WS TEXT trực tiếp trên socket audio (rẻ ~27B,
        xen được giữa PCM), fallback MQTT compact.
        Trả về "ws" | "mqtt" | "failed".
        """
        if self.audio_server is not None:
            try:
                if self.audio_server.has_ws(node_id):
                    ok = await self.audio_server.send_relay_ws(node_id, channel, action, seq)
                    if ok:
                        return "ws"
            except Exception as e:
                logger.warning(f"WS dispatch error: {e}")
        ok = await self.mqtt.send_command(node_id, channel, action, seq=seq)
        return "mqtt" if ok else "failed"

    async def execute_action(self, node_id: str, channel: str, action: str, seq: int = 0) -> bool:
        """Thực thi lệnh relay: ưu tiên WebSocket, fallback MQTT."""
        via = await self._dispatch(node_id, channel, action, seq)
        return via != "failed"

    async def verify_command(self, node_id: str, channel: str,
                             action: str, seq: int = 0) -> tuple:
        """
        Send command and verify its request ID and reported relay state.
        
        Returns:
            (VerifyResult, power_before, power_after, delta)
        """
        rated_watts = self.registry.get_rated_watts(node_id, channel)
        
        # 1. Record current power
        before_power = self.mqtt.get_current_power(node_id)
        logger.info(
            f"Verify: {action} {node_id}/{channel} "
            f"(rated={rated_watts}W, before={before_power:.1f}W, seq={seq})"
        )

        seq = seq or secrets.randbelow(0x7ffffffe) + 1
        self.mqtt.command_acks.pop((node_id, seq), None)
        # 2. Send command (WS ưu tiên, fallback MQTT)
        via = await self._dispatch(node_id, channel, action, seq)
        if via == "failed":
            logger.error(f"Dispatch failed: {node_id}/{channel}")
            return VerifyResult.TIMEOUT, before_power, before_power, 0.0

        timeout = max(float(getattr(config, "VERIFY_TIMEOUT_SECONDS", 3.0)), 1.5)
        deadline = asyncio.get_running_loop().time() + timeout
        ack = None
        while asyncio.get_running_loop().time() < deadline:
            ack = self.mqtt.command_acks.pop((node_id, seq), None)
            if ack is not None:
                break
            await asyncio.sleep(0.05)
        if ack is None:
            return VerifyResult.TIMEOUT, before_power, before_power, 0.0
        expected = "ON" if action in ("turn_on", "open", "on") else "OFF"
        channel_number = {"ch1": 1, "ch2": 2, "1": 1, "2": 2, 1: 1, 2: 2}.get(channel)
        if "channel" in ack and ack["channel"] != channel_number:
            return VerifyResult.FAILED, before_power, before_power, 0.0
        states = ack.get("relay_states")
        if isinstance(states, list):
            index = {"ch1": 0, "ch2": 1, "1": 0, "2": 1, 1: 0, 2: 1}.get(channel)
            if index is not None and index < len(states):
                ack["state"] = "ON" if states[index] else "OFF"
        if ack.get("status") != "OK" or ack.get("state") != expected:
            return VerifyResult.FAILED, before_power, before_power, 0.0
        after_power = self.mqtt.get_current_power(node_id)
        
        # Basic load verification
        nodes = getattr(self.registry, "get_all_nodes", lambda: {})()
        ch_info = nodes.get(node_id, {}).get("channels", {}).get(channel, {})
        thresholds = ch_info.get("load_verification", {})
        report = getattr(self.mqtt, "load_reports", {}).get((node_id, seq))
        
        result_state = VerifyResult.ACK_ONLY
        if thresholds and report and report.get("sample", {}).get("valid"):
            result_state = VerifyResult.CONFIRMED_LOAD
            
        return result_state, before_power, after_power, after_power - before_power

    def generate_failure_message(self, action: str, device_type: str,
                                 area: str, result: VerifyResult) -> str:
        """Generate Vietnamese alert message for verification failure."""
        device_name = get_device_name(device_type)
        area_name = get_room_name(area)
        
        loc_part = f" tại {area_name}" if area_name else ""
        if result == VerifyResult.TIMEOUT:
            return clean_voice_text(f"Chưa nhận được xác nhận từ {device_name}{loc_part}.")
        return clean_voice_text(f"Thiết bị {device_name}{loc_part} không xác nhận trạng thái yêu cầu.")
