"""
Verify Engine — Command verification via correlated device acknowledgements.
Power telemetry is reported separately; an ACK confirms relay state, not load health.

🎯 CORE GOAL: This is the HEART of the closed-loop system.
"""

import asyncio
import logging
import secrets
import time
from enum import Enum
from typing import Any, Dict, Optional

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


class CommandResult:
    """Standardized command verification result DTO."""

    def __init__(
        self,
        command_id: str,
        requested_state: str,
        confirmed_state: Optional[str],
        verification: VerifyResult,
        error: Optional[str] = None,
        power_before: float = 0.0,
        power_after: float = 0.0,
        delta: float = 0.0,
        channel: Optional[str] = None,
        node_id: Optional[str] = None,
    ):
        self.command_id = str(command_id)
        self.requested_state = requested_state
        self.confirmed_state = confirmed_state
        self.verification = verification
        self.error = error
        self.power_before = float(power_before)
        self.power_after = float(power_after)
        self.delta = float(delta)
        self.channel = channel
        self.node_id = node_id

    @property
    def is_success(self) -> bool:
        return (
            self.verification in (
                VerifyResult.SUCCESS,
                VerifyResult.CONFIRMED_LOAD,
                VerifyResult.ACK_ONLY,
                VerifyResult.ALREADY_IN_STATE,
            )
            and self.error is None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "requested_state": self.requested_state,
            "confirmed_state": self.confirmed_state,
            "verification": self.verification.value if isinstance(self.verification, Enum) else str(self.verification),
            "is_success": self.is_success,
            "error": self.error,
            "power_before": self.power_before,
            "power_after": self.power_after,
            "delta": self.delta,
            "channel": self.channel,
            "node_id": self.node_id,
        }

    def __iter__(self):
        return iter((self.verification, self.power_before, self.power_after, self.delta))

    def __getitem__(self, index):
        return (self.verification, self.power_before, self.power_after, self.delta)[index]

    def __len__(self):
        return 4

    def __repr__(self):
        return (
            f"CommandResult(cmd_id={self.command_id}, req={self.requested_state}, "
            f"conf={self.confirmed_state}, verify={self.verification}, err={self.error})"
        )


class ChannelTelemetry:
    """Standardized channel telemetry DTO."""

    def __init__(
        self,
        channel_id: str,
        sample_time: float,
        validity: bool,
        power_w: float = 0.0,
        voltage_v: float = 0.0,
        current_a: float = 0.0,
        energy_wh: float = 0.0,
    ):
        self.channel_id = str(channel_id)
        self.sample_time = float(sample_time)
        self.validity = bool(validity)
        self.power_w = float(power_w)
        self.voltage_v = float(voltage_v)
        self.current_a = float(current_a)
        self.energy_wh = float(energy_wh)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "sample_time": self.sample_time,
            "validity": self.validity,
            "power_w": self.power_w,
            "voltage_v": self.voltage_v,
            "current_a": self.current_a,
            "energy_wh": self.energy_wh,
        }


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
                             action: str, seq: int = 0) -> CommandResult:
        """
        Send command and verify its request ID and reported relay state.

        Returns:
            CommandResult (also unpackable as (VerifyResult, power_before, power_after, delta))
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
                return CommandResult(
                    command_id=str(seq or 0),
                    requested_state=expected,
                    confirmed_state=expected,
                    verification=VerifyResult.ALREADY_IN_STATE,
                    power_before=before_power,
                    power_after=before_power,
                    delta=0.0,
                    channel=channel,
                    node_id=node_id,
                )

        seq = seq or secrets.randbelow(0x7ffffffe) + 1
        self.mqtt.command_acks.pop((node_id, seq), None)

        via = await self._dispatch(node_id, channel, action, seq)
        self._last_dispatch = via
        if via == "failed":
            logger.error(f"Dispatch failed: {node_id}/{channel}")
            return CommandResult(
                command_id=str(seq),
                requested_state=expected,
                confirmed_state=None,
                verification=VerifyResult.TIMEOUT,
                error="dispatch_failed",
                power_before=before_power,
                power_after=before_power,
                delta=0.0,
                channel=channel,
                node_id=node_id,
            )

        timeout = max(float(getattr(config, "VERIFY_TIMEOUT_SECONDS", 3.0)), 1.5)
        deadline = asyncio.get_running_loop().time() + timeout
        ack = None
        while asyncio.get_running_loop().time() < deadline:
            ack = self.mqtt.command_acks.pop((node_id, seq), None)
            if ack is not None:
                break
            await asyncio.sleep(0.05)
        if ack is None:
            return CommandResult(
                command_id=str(seq),
                requested_state=expected,
                confirmed_state=None,
                verification=VerifyResult.TIMEOUT,
                error="ack_timeout",
                power_before=before_power,
                power_after=before_power,
                delta=0.0,
                channel=channel,
                node_id=node_id,
            )
        logger.info(f"Verify ACK for {node_id}/{channel}: ack={ack}")
        if "channel" in ack and ack["channel"] != channel_number:
            return CommandResult(
                command_id=str(seq),
                requested_state=expected,
                confirmed_state=None,
                verification=VerifyResult.FAILED,
                error="ack_channel_mismatch",
                power_before=before_power,
                power_after=before_power,
                delta=0.0,
                channel=channel,
                node_id=node_id,
            )
        states = ack.get("relay_states")
        if isinstance(states, list):
            index = channel_number - 1 if channel_number is not None else None
            if index is not None and index < len(states):
                ack["state"] = "ON" if states[index] else "OFF"
        if ack.get("status") != "OK" or ack.get("state") != expected:
            return CommandResult(
                command_id=str(seq),
                requested_state=expected,
                confirmed_state=None,
                verification=VerifyResult.FAILED,
                error="ack_state_mismatch",
                power_before=before_power,
                power_after=before_power,
                delta=0.0,
                channel=channel,
                node_id=node_id,
            )
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
        if thresholds and report is None and hasattr(self.mqtt, "load_reports"):
            wait_deadline = asyncio.get_event_loop().time() + 1.2
            while asyncio.get_event_loop().time() < wait_deadline:
                report = self.mqtt.load_reports.get((node_id, seq))
                if report is not None:
                    break
                await asyncio.sleep(0.05)

        if isinstance(report, dict):
            rep_ch = {"ch1": 1, "ch2": 2, "ch3": 3, 1: 1, 2: 2, 3: 3, "1": 1, "2": 2, "3": 3}.get(report.get("channel"))
            if rep_ch is None or rep_ch == channel_number:
                sample = report.get("sample")
                sample_p = sample.get("power_w") if isinstance(sample, dict) else report.get("power_w")
                if sample_p is not None:
                    try:
                        after_power = float(sample_p)
                    except (ValueError, TypeError):
                        pass

        result_state = VerifyResult.ACK_ONLY
        if thresholds and isinstance(report, dict):
            rep_seq = report.get("seq", report.get("request_id", seq))
            rep_ch = {"ch1": 1, "ch2": 2, "ch3": 3, 1: 1, 2: 2, 3: 3, "1": 1, "2": 2, "3": 3}.get(report.get("channel"))
            sample = report.get("sample")
            # 1. Match exact channel and seq
            channel_match = (rep_ch == channel_number) if (rep_ch is not None and channel_number is not None) else False
            seq_match = (rep_seq == seq)
            # 2. Sample valid must be True explicitly
            sample_valid = isinstance(sample, dict) and (sample.get("valid") is True)

            # 3. Staleness check: sample_time or timestamp <= 15s
            sample_time_val = None
            if isinstance(sample, dict):
                sample_time_val = sample.get("sample_time", sample.get("timestamp"))

            is_stale = False
            if sample_time_val is not None:
                try:
                    st = float(sample_time_val)
                    if st > 1e11:  # ms to seconds
                        st = st / 1000.0
                    now_s = time.time()
                    if (now_s - st) > 15.0 or (now_s - st) < -60.0:
                        is_stale = True
                except (ValueError, TypeError):
                    is_stale = True

            if channel_match and seq_match and sample_valid and not is_stale:
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
                        if p_val <= 0 or delta <= 0:
                            load_confirmed = False
                    if p_val <= 0:
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

        return CommandResult(
            command_id=str(seq),
            requested_state=expected,
            confirmed_state=expected,
            verification=result_state,
            error=None,
            power_before=before_power,
            power_after=after_power,
            delta=after_power - before_power,
            channel=channel,
            node_id=node_id,
        )

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
            return clean_voice_text("Chưa xác nhận được trạng thái thiết bị.")
        if result == VerifyResult.FAILED:
            return clean_voice_text("Thiết bị chưa thực hiện được lệnh.")
        if result == VerifyResult.FAULT:
            return clean_voice_text("Thiết bị gặp sự cố phần cứng.")
        return clean_voice_text(f"Thiết bị {device_name}{loc_part} không xác nhận trạng thái yêu cầu.")
