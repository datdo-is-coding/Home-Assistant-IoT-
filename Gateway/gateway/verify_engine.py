"""
Verify Engine — Closed-loop command verification via telemetry feedback.
After sending a command, monitors power telemetry to confirm device responded.

🎯 CORE GOAL: This is the HEART of the closed-loop system.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional

import config
from display_names import get_room_name, get_device_name, clean_voice_text

logger = logging.getLogger("verify")


class VerifyResult(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CommandVerifier:
    """Verify commands by comparing power telemetry before/after."""

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

    async def verify_command(self, node_id: str, channel: str,
                             action: str, seq: int = 0) -> tuple:
        """
        Send command and verify via telemetry feedback.
        
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

        # 2. Send command (WS ưu tiên, fallback MQTT)
        via = await self._dispatch(node_id, channel, action, seq)
        if via == "failed":
            logger.error(f"Dispatch failed: {node_id}/{channel}")
            return VerifyResult.TIMEOUT, before_power, before_power, 0.0

        # Nếu node không có công suất trước đó hoặc không gắn PZEM -> Xác nhận tức thì (0ms)
        node_info = self.registry.get_all_nodes().get(node_id, {})
        has_pzem = node_info.get("sensors", {}).get("pzem", False)
        if before_power == 0.0 and not has_pzem:
            logger.info(f"Verify: Node {node_id} command confirmed instantly via {via}")
            return VerifyResult.SUCCESS, 0.0, 0.0, 0.0
        
        # Nếu có telemetry đang chạy, chỉ đợi tối đa 0.2s để không làm trễ phản hồi giọng nói của loa
        verify_timeout = min(getattr(config, "VERIFY_TIMEOUT_SECONDS", 0.2), 0.2)
        if verify_timeout > 0:
            await asyncio.sleep(verify_timeout)
        
        # 4. Read new power
        after_power = self.mqtt.get_current_power(node_id)
        delta = after_power - before_power
        
        # 5. Analyze result
        if before_power == 0.0 and after_power == 0.0:
            result = VerifyResult.SUCCESS
        else:
            result = self._analyze(action, delta, rated_watts)
        
        logger.info(
            f"Verify result: {result.value} "
            f"(before={before_power:.1f}W, after={after_power:.1f}W, "
            f"delta={delta:+.1f}W)"
        )
        
        return result, before_power, after_power, delta
    
    def _analyze(self, action: str, delta: float,
                 rated_watts: float) -> VerifyResult:
        """Analyze power delta to determine if command succeeded."""
        threshold = max(rated_watts * 0.3, 3.0)  # Min 3W threshold
        
        if action in ("turn_on", "open"):
            if delta > threshold:
                return VerifyResult.SUCCESS
            elif delta > 0:
                return VerifyResult.PARTIAL
            else:
                return VerifyResult.FAILED
        
        elif action in ("turn_off", "close"):
            if delta < -threshold:
                return VerifyResult.SUCCESS
            elif delta < 0:
                return VerifyResult.PARTIAL
            else:
                return VerifyResult.FAILED
        
        return VerifyResult.FAILED
    
    def generate_failure_message(self, action: str, device_type: str,
                                 area: str, result: VerifyResult) -> str:
        """Generate Vietnamese alert message for verification failure."""
        device_name = get_device_name(device_type)
        area_name = get_room_name(area)
        
        if result == VerifyResult.FAILED:
            if action == "turn_on":
                msg = (
                    f"Dạ anh ơi, em đã bật công tắc {device_name} ở {area_name} rồi, "
                    f"nhưng không thấy tiêu thụ điện nè. "
                    f"Anh kiểm tra xem phích cắm hoặc bóng đèn có sao không nha anh~"
                )
            else:
                msg = (
                    f"Dạ anh ơi, em đã ngắt công tắc {device_name} ở {area_name} rồi, "
                    f"nhưng đường điện vẫn còn báo công suất. "
                    f"Anh kiểm tra lại công tắc giúp em nha~"
                )
            return clean_voice_text(msg)
        elif result == VerifyResult.PARTIAL:
            msg = (
                f"Dạ anh ơi, {device_name} ở {area_name} dường như hoạt động hơi yếu hơn bình thường, "
                f"anh để ý thêm giúp em nhé~"
            )
            return clean_voice_text(msg)
        
        return ""

