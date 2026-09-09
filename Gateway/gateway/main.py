"""
DTV Smart Home Gateway — Main Entry Point
The central orchestrator that connects all engines.

🎯 CORE GOAL: This is the brain. Every decision flows through here.
"""

import asyncio
import logging
import signal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from registry_manager import RegistryManager
from mqtt_handler import MQTTHandler
from intent_engine import IntentEngine
from tts_engine import TTSEngine
from asr_engine import ASREngine
from audio_server import AudioServer
from verify_engine import CommandVerifier, VerifyResult
from memory_engine import MemoryEngine

try:
    from telemetry_writer import TelemetryWriter
    HAS_INFLUX = True
except ImportError:
    HAS_INFLUX = False

logger = logging.getLogger("gateway")


class SmartHomeGateway:
    """Main gateway orchestrator."""
    
    def __init__(self):
        # Core engines
        self.registry = RegistryManager()
        self.mqtt = MQTTHandler()
        self.intent = IntentEngine()
        self.tts = TTSEngine()
        self.asr = ASREngine()
        self.audio_server = AudioServer(self)
        self.memory = MemoryEngine()
        self.verifier = CommandVerifier(self.mqtt, self.registry)
        
        # Optional engines
        self.telemetry_writer = None
        if HAS_INFLUX:
            self.telemetry_writer = TelemetryWriter()
        
        self._running = False
    
    async def start(self):
        """Start all gateway services."""
        logger.info("=" * 60)
        logger.info("  DTV SMART HOME GATEWAY — Starting Up")
        logger.info("=" * 60)
        
        # Initialize ASR
        logger.info("Initializing ASR engine...")
        self.asr.initialize()
        
        # Start Audio WebSocket Server
        await self.audio_server.start()
        
        # Initialize optional services
        if self.telemetry_writer:
            self.telemetry_writer.initialize()
        
        # Register MQTT message handlers
        self.mqtt.on_message("smarthome/register", self._on_node_register)
        self.mqtt.on_message("smarthome/telemetry/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/status/#", self._on_status)
        
        self._running = True
        logger.info("Starting MQTT client...")
        
        try:
            await self.mqtt.connect()
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            logger.info("Gateway will retry in 5 seconds...")
            await asyncio.sleep(5)
            await self.start()
    
    async def process_voice_command(self, user_text: str) -> dict:
        """
        Full voice command processing pipeline:
        1. Intent extraction (LLM)
        2. Device lookup (Registry)
        3. Command dispatch (MQTT)
        4. Verification (Telemetry feedback)
        5. Voice response (TTS)
        6. Memory logging
        """
        result = {
            "user_text": user_text,
            "intent": None,
            "node_id": None,
            "channel": None,
            "verify": None,
            "voice_reply": None,
            "tts_audio": None,
        }
        
        # Step 1: Extract intent from text
        logger.info(f'Processing voice command: "{user_text}"')
        intent = await self.intent.extract(user_text)
        
        if not intent or not self.intent.validate_intent(intent):
            reply = "Xin lỗi, em không hiểu lệnh. Bạn nói lại được không?"
            result["voice_reply"] = reply
            result["tts_audio"] = await self.tts.synthesize(reply)
            return result
        
        result["intent"] = intent
        command = intent["command"]
        
        # Step 2: Find the target device in registry
        lookup = self.registry.find_node_by_device(
            command["device"], command["location"]
        )
        
        if not lookup:
            reply = (
                f"Em không tìm thấy thiết bị {command['device']} "
                f"ở {command['location']}. "
                f"Vui lòng kiểm tra lại hoặc đăng ký thiết bị."
            )
            result["voice_reply"] = reply
            result["tts_audio"] = await self.tts.synthesize(reply)
            return result
        
        node_id, channel = lookup
        result["node_id"] = node_id
        result["channel"] = channel
        
        # Step 3 & 4: Send command and verify
        verify_result, p_before, p_after, delta = \
            await self.verifier.verify_command(
                node_id, channel, command["action"]
            )
        result["verify"] = verify_result.value
        
        # Step 5: Generate voice response
        if verify_result == VerifyResult.SUCCESS:
            voice_reply = intent.get("voice_reply", "Đã thực hiện.")
        elif verify_result == VerifyResult.FAILED:
            voice_reply = self.verifier.generate_failure_message(
                command["action"], command["device"],
                command["location"], verify_result
            )
        else:
            voice_reply = intent.get("voice_reply", "Đã thực hiện.")
        
        result["voice_reply"] = voice_reply
        result["tts_audio"] = await self.tts.synthesize(voice_reply)
        
        # Step 6: Log to memory
        self.memory.record_command(
            user_text=user_text,
            action=command["action"],
            device=command["device"],
            area=command["location"],
            node_id=node_id,
            channel=channel,
            verify_result=verify_result.value,
            power_before=p_before,
            power_after=p_after,
        )
        
        logger.info(
            f"Command complete: {command['action']} "
            f"{command['device']}@{command['location']} "
            f"→ {verify_result.value}"
        )
        
        return result
    
    # ── MQTT Callbacks ──────────────────────────────────
    
    async def _on_node_register(self, topic: str, payload: dict):
        mac = payload.get("mac", "unknown")
        node_id = payload.get("node_id", f"node_{mac.replace(':', '')[-6:]}")
        channels = payload.get("channels", {})
        self.registry.register_node(node_id, mac, channels)
        logger.info(f"📡 Node registered: {node_id} (MAC: {mac})")
    
    async def _on_telemetry(self, topic: str, payload: dict):
        node_id = topic.split("/")[-1]
        self.registry.update_heartbeat(node_id)
        if self.telemetry_writer:
            node_info = self.registry.get_all_nodes().get(node_id, {})
            area = node_info.get("area", "unknown")
            for ch_id, ch_info in node_info.get("channels", {}).items():
                self.telemetry_writer.write_telemetry(
                    node_id=node_id,
                    area=area,
                    device_type=ch_info.get("device_type", "unknown"),
                    channel=ch_id,
                    telemetry=payload,
                )
    
    async def _on_status(self, topic: str, payload: dict):
        node_id = topic.split("/")[-1]
        self.registry.update_heartbeat(node_id)


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(name)-12s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


async def main():
    setup_logging()
    gateway = SmartHomeGateway()
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown(gateway)))
        except NotImplementedError:
            pass
    
    await gateway.start()


async def _shutdown(gateway):
    logger.info("Shutting down gateway...")
    gateway._running = False
    await gateway.audio_server.stop()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in tasks:
        t.cancel()


if __name__ == "__main__":
    asyncio.run(main())
