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
    ALREADY_IN_STATE = "already_in_state"

class CommandVerifier:
    """Require a device ACK before reporting an applied relay command."""

    def __init__(self, mqtt_handler, registry):
        self.mqtt = mqtt_handler
        self.registry = registry
        self.audio_server = None
        self._last_dispatch = None

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

        before_power = self.mqtt.get_current_power(node_id)
        logger.info(
            f"Verify: {action} {node_id}/{channel} "
            f"(rated={rated_watts}W, before={before_power:.1f}W, seq={seq})"
        )

        expected = "ON" if action in ("turn_on", "open", "on") else "OFF"
        channel_number = {"ch1": 1, "ch2": 2, "ch3": 3, "1": 1, "2": 2, "3": 3, 1: 1, 2: 2, 3: 3}.get(channel)

        nodes = getattr(self.registry, "get_all_nodes", lambda: {})()
        node = nodes.get(node_id)
        if node is not None and channel_number is not None:
            relay_states = node.get("relay_state", [])
            channel_index = channel_number - 1
            if 0 <= channel_index < len(relay_states) and relay_states[channel_index] == (1 if expected == "ON" else 0):
                logger.info(f"Verify: {node_id}/{channel} is already {expected} (no pulse needed)")
                return VerifyResult.ALREADY_IN_STATE, before_power, before_power, 0.0

        seq = seq or secrets.randbelow(0x7ffffffe) + 1
        self.mqtt.command_acks.pop((node_id, seq), None)

        via = await self._dispatch(node_id, channel, action, seq)
        self._last_dispatch = via
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
        logger.info(f"Verify ACK for {node_id}/{channel}: ack={ack}")
        if "channel" in ack and ack["channel"] != channel_number:
            return VerifyResult.FAILED, before_power, before_power, 0.0
        states = ack.get("relay_states")
        if isinstance(states, list):
            index = channel_number - 1 if channel_number is not None else None
            if index is not None and index < len(states):
                ack["state"] = "ON" if states[index] else "OFF"
        if ack.get("status") != "OK" or ack.get("state") != expected:
            return VerifyResult.FAILED, before_power, before_power, 0.0
        after_power = self.mqtt.get_current_power(node_id)

        if node is not None and channel_number is not None and hasattr(self.registry, "update_relay_state"):
            relay_states = list(node.get("relay_state", [0, 0]))
            caps = node.get("capabilities", [])
            min_len = 3 if ("relay_3ch" in caps or len(node.get("channels", {})) >= 3) else 2
            while len(relay_states) < max(channel_number, min_len):
                relay_states.append(0)
            relay_states[channel_number - 1] = 1 if expected == "ON" else 0
            self.registry.update_relay_state(node_id, relay_states)
        ch_info = nodes.get(node_id, {}).get("channels", {}).get(channel, {})
        thresholds = ch_info.get("load_verification", {})
        report = getattr(self.mqtt, "load_reports", {}).get((node_id, seq))

        result_state = VerifyResult.ACK_ONLY
        if thresholds and isinstance(report, dict):
            rep_ch = {"ch1": 1, "ch2": 2, "ch3": 3, 1: 1, 2: 2, 3: 3, "1": 1, "2": 2, "3": 3}.get(report.get("channel"))
            sample = report.get("sample")
            # 1. Match exact channel
            channel_match = (rep_ch == channel_number) if (rep_ch is not None and channel_number is not None) else True
            # 2. Sample valid must be True
            sample_valid = isinstance(sample, dict) and (sample.get("valid") is True)

            if channel_match and sample_valid:
                sample_p = sample.get("power_w")
                sample_curr = sample.get("current_ma")
                p_val = float(sample_p) if sample_p is not None else float(after_power)
                curr_val = float(sample_curr) if sample_curr is not None else None
                delta = after_power - before_power

                load_confirmed = True
                if expected == "ON":
                    min_on_w = thresholds.get("min_on_power_w")
                    if min_on_w is not None:
                        if p_val < float(min_on_w):
                            load_confirmed = False
                    elif "on_min_ma" in thresholds:
                        on_min_ma = float(thresholds["on_min_ma"])
                        if curr_val is not None and curr_val < on_min_ma:
                            load_confirmed = False
                        if p_val <= 0 and (curr_val is None or curr_val <= 0):
                            load_confirmed = False
                    else:
                        if p_val <= 0 and delta <= 0:
                            load_confirmed = False
                else:
                    max_off_w = thresholds.get("max_off_power_w")
                    if max_off_w is not None:
                        if p_val > float(max_off_w):
                            load_confirmed = False
                    elif "off_max_ma" in thresholds:
                        off_max_ma = float(thresholds["off_max_ma"])
                        if curr_val is not None and curr_val > off_max_ma:
                            load_confirmed = False

                if load_confirmed:
                    result_state = VerifyResult.CONFIRMED_LOAD

        return result_state, before_power, after_power, after_power - before_power

    def generate_failure_message(self, action: str, device_type: str,
                                 area: str, result: VerifyResult) -> str:
        """Generate Vietnamese alert message for verification failure."""
        if getattr(self, "_last_dispatch", None) == "failed":
            return clean_voice_text("Thiết bị đang mất kết nối.")

        device_name = get_device_name(device_type)
        area_name = get_room_name(area)
        loc_part = f" {area_name}" if area_name else ""
        action_str = "bật" if action in ("turn_on", "open", "on") else "tắt"

        if result == VerifyResult.CONFIRMED_LOAD:
            return clean_voice_text(f"{device_name}{loc_part} đã {action_str}.")
        if result in (VerifyResult.ACK_ONLY, VerifyResult.SUCCESS):
            return clean_voice_text(f"Đã đặt {device_name}{loc_part} sang {action_str}.")
        if result == VerifyResult.ALREADY_IN_STATE:
            return clean_voice_text(f"{device_name}{loc_part} đang ở trạng thái {action_str}.")
        if result == VerifyResult.TIMEOUT:
            return clean_voice_text(f"Chưa xác nhận được trạng thái thiết bị.")
        if result == VerifyResult.FAILED:
            return clean_voice_text(f"Thiết bị chưa thực hiện được lệnh.")
        if result == VerifyResult.FAULT:
            return clean_voice_text(f"Thiết bị gặp sự cố phần cứng.")
        return clean_voice_text(f"Thiết bị {device_name}{loc_part} không xác nhận trạng thái yêu cầu.")
