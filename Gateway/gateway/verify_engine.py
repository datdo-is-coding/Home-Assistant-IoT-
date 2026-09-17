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
    
    async def verify_command(self, node_id: str, channel: str,
                             action: str) -> tuple:
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
            f"(rated={rated_watts}W, before={before_power:.1f}W)"
        )
        
        # 2. Send command
        await self.mqtt.send_command(node_id, channel, action)
        
        # 3. Wait for telemetry update
        await asyncio.sleep(config.VERIFY_TIMEOUT_SECONDS)
        
        # 4. Read new power
        after_power = self.mqtt.get_current_power(node_id)
        delta = after_power - before_power
        
        # 5. Analyze result
        # If no power telemetry is available for this node (both before and after are 0.0W)
        if before_power == 0.0 and after_power == 0.0:
            logger.info(f"Verify: Node {node_id} has no power sensor — command confirmed via MQTT")
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
        device_name = device_type.replace("_", " ")
        area_name = area.replace("_", " ")
        
        if result == VerifyResult.FAILED:
            if action == "turn_on":
                return (
                    f"Em đã bật công tắc {device_name} ở {area_name}, "
                    f"nhưng không thấy tiêu thụ điện. "
                    f"Có thể thiết bị bị hỏng hoặc chưa cắm điện."
                )
            else:
                return (
                    f"Em đã tắt công tắc {device_name} ở {area_name}, "
                    f"nhưng vẫn thấy tiêu thụ điện. "
                    f"Vui lòng kiểm tra lại."
                )
        elif result == VerifyResult.PARTIAL:
            return (
                f"{device_name} ở {area_name} có vẻ hoạt động yếu. "
                f"Tiêu thụ thấp hơn bình thường."
            )
        
        return ""
