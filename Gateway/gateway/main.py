"""
DTV Smart Home Gateway — Main Entry Point v2

Nâng cấp:
- Registry v2: quản lý theo phòng + fullname livingroom-node01-fan
- Intent 2 lớp: LLM chỉ trích ý định, Registry mới phân giải node_id/channel
- Relay dispatch: ưu tiên WebSocket TEXT frame (xen giữa PCM), fallback MQTT compact
- Pending/provision flow: node mới (cfg:null) → WebUI đăng ký → Gateway gửi cfg → node NVS
"""

import asyncio
import logging
import signal
import sys
import os
import json

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
from web_server import WebServer

try:
    from telemetry_writer import TelemetryWriter
    HAS_INFLUX = True
except ImportError:
    HAS_INFLUX = False

logger = logging.getLogger("gateway")


class SmartHomeGateway:
    def __init__(self):
        self.registry = RegistryManager()
        self.mqtt = MQTTHandler()
        self.intent = IntentEngine(registry=self.registry)
        # đảm bảo intent luôn có registry mới nhất
        self.intent.set_registry(self.registry)
        self.tts = TTSEngine()
        self.asr = ASREngine()
        self.audio_server = AudioServer(self)
        self.memory = MemoryEngine()
        self.verifier = CommandVerifier(self.mqtt, self.registry)
        # verifier cần biết audio_server để chọn WS vs MQTT
        self.verifier.audio_server = self.audio_server
        self.web_server = WebServer(self)

        self.telemetry_writer = None
        if HAS_INFLUX:
            self.telemetry_writer = TelemetryWriter()
        self._running = False

    async def start(self):
        logger.info("=" * 60)
        logger.info("  DTV SMART HOME GATEWAY v2 — Starting Up")
        logger.info("  Inventory: %s", self.registry.inventory_for_prompt())
        logger.info("=" * 60)

        logger.info("Initializing ASR engine...")
        self.asr.initialize()

        await self.audio_server.start()
        await self.web_server.start()

        if self.telemetry_writer:
            self.telemetry_writer.initialize()

        # MQTT handlers: compact + legacy
        self.mqtt.on_message("smarthome/hello", self._on_hello)
        self.mqtt.on_message("smarthome/register", self._on_node_register)  # legacy
        self.mqtt.on_message("smarthome/telemetry/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/tele/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/status/#", self._on_status)

        self._running = True
        logger.info("Starting MQTT client...")
        try:
            await self.mqtt.connect()
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            await asyncio.sleep(5)
            await self.start()

    # ── Voice pipeline (2 lớp, chống ảo giác) ──────────────────────────
    async def process_voice_command(self, user_text: str) -> dict:
        result = {
            "user_text": user_text, "intent": None,
            "engine": None,
            "node_id": None, "channel": None, "fullname": None,
            "verify": None, "voice_reply": None, "tts_audio": None,
        }
        logger.info(f'Voice: "{user_text}"')
        intent = await self.intent.extract(user_text)
        result["engine"] = getattr(self.intent, "active_engine", "unknown")
        logger.info(f'Engine selected: {result["engine"]}')

        if not intent or not self.intent.validate_intent(intent):
            reply = "Xin lỗi, em không hiểu lệnh. Bạn nói lại được không?"
            result["voice_reply"] = reply
            result["tts_audio"] = await self.tts.synthesize(reply)
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "parse_error",
                "engine": result["engine"]
            })
            return result

        result["intent"] = intent
        cmd = intent["command"]
        device = cmd.get("device")
        location = cmd.get("location")
        action = cmd.get("action", "turn_on")

        # Lớp 2: phân giải node_id/channel TỪ REGISTRY THỰC TẾ — không bao giờ bịa
        lookup = self.registry.find_node_by_device(device, location)
        if not lookup:
            # Phân biệt: mơ hồ (nhiều node cùng tên) vs không tồn tại
            all_online = self.registry.get_online_nodes()
            if not all_online:
                reply = "Hiện chưa có thiết bị nào được đăng ký. Vui lòng thêm node mới ở giao diện web."
            elif device and location:
                reply = f"Em không tìm thấy {device} ở {location}. Vui lòng kiểm tra lại hoặc đăng ký thiết bị ở web."
            elif device and not location:
                # mơ hồ: có nhiều node cùng device nhưng không nói phòng
                reply = f"Bạn muốn điều khiển {device} ở phòng nào ạ? Hiện có {', '.join(self.registry.allowed_rooms())}."
            else:
                reply = intent.get("voice_reply") or "Bạn muốn điều khiển thiết bị nào và ở phòng nào ạ?"
            result["voice_reply"] = reply
            result["tts_audio"] = await self.tts.synthesize(reply)
            self.broadcast_event("command_result", {"voice_reply": reply, "verify": "not_found"})
            logger.warning(f"Resolver miss: device={device} location={location}")
            return result

        node_id, channel = lookup
        fullname = self.registry.resolve_fullname(node_id, channel)
        result.update({"node_id": node_id, "channel": channel, "fullname": fullname})
        logger.info(f"Resolver OK: {device}@{location} → {fullname} ({node_id}/{channel}) {action}")

        # Dispatch + verify (WS ưu tiên, fallback MQTT)
        seq = self.registry.next_seq(node_id)
        verify_result, p_before, p_after, delta = await self.verifier.verify_command(
            node_id, channel, action, seq=seq
        )
        result["verify"] = verify_result.value

        if verify_result == VerifyResult.SUCCESS:
            voice_reply = intent.get("voice_reply") or f"Đã {('bật' if action=='turn_on' else 'tắt')} {device} ở {location or ''} ạ."
        elif verify_result == VerifyResult.FAILED:
            voice_reply = self.verifier.generate_failure_message(action, device or channel, location or "", verify_result)
        else:
            voice_reply = intent.get("voice_reply") or "Đã thực hiện."

        result["voice_reply"] = voice_reply
        # PCM ưu tiên cho ESP32 I2S
        pcm = await self.tts.synthesize_pcm(voice_reply)
        if pcm:
            result["tts_audio"] = pcm
            result["tts_format"] = "pcm"
        else:
            result["tts_audio"] = await self.tts.synthesize(voice_reply)
            result["tts_format"] = "mp3"

        self.memory.record_command(
            user_text=user_text, action=action, device=device or channel,
            area=location or self.registry.get_all_nodes().get(node_id, {}).get("room",""),
            node_id=node_id, channel=channel,
            verify_result=verify_result.value, power_before=p_before, power_after=p_after,
        )
        # broadcast để WebUI cập nhật relay ngay
        self.broadcast_event("command_result", {
            "voice_reply": voice_reply, "verify": verify_result.value,
            "node_id": node_id, "channel": channel, "fullname": fullname, "action": action,
            "engine": result.get("engine", "local"),
        })
        logger.info(f"Done: {action} {fullname} via [{result.get('engine')}] → {verify_result.value} Δ{delta:+.1f}W")
        return result

    def broadcast_event(self, event_name: str, data: dict):
        if hasattr(self, "web_server") and self.web_server:
            self.web_server.broadcast_event(event_name, data)

    # ── MQTT Callbacks ─────────────────────────────────────────────────
    async def _on_hello(self, topic: str, payload: dict):
        """Node mới hoặc đã provision gửi hello qua MQTT (compact)."""
        if not isinstance(payload, dict):
            return
        hello = payload if payload.get("t") == "hello" else {"t": "hello", **payload}
        res = self.registry.on_hello(hello, ws_available=False)
        self.broadcast_event("node_hello", hello)
        # nếu pending → WebUI sẽ hiện nút đăng ký
        if res.get("action") == "pending":
            self.broadcast_event("pending_node", {"mac": res["mac"], "hello": hello})
            logger.info(f"📥 Pending node (MQTT): {res['mac']}")
        elif res.get("action") == "cfg_mismatch":
            cfg = self.registry.get_provision_payload(res["node_id"])
            if cfg:
                await self.mqtt.send_cfg(res["node_id"], cfg)
        elif res.get("action") == "known":
            self.broadcast_event("node_status", {"node_id": res["node_id"], "online": True})

    async def _on_node_register(self, topic: str, payload: dict):
        """Legacy register (giữ tương thích)."""
        if not isinstance(payload, dict):
            return
        # nếu đã có hello flow thì bỏ qua legacy để tránh trùng
        if payload.get("t") == "hello":
            await self._on_hello(topic, payload)
            return
        mac = payload.get("mac", "unknown")
        node_id = payload.get("node_id", f"node_{mac.replace(':','')[-6:]}")
        channels = payload.get("channels", {})
        area = payload.get("area")
        description = payload.get("description")
        self.registry.register_node(node_id, mac, channels, area, description)
        logger.info(f"📡 Legacy register: {node_id} ({mac})")
        self.broadcast_event("node_status", {"node_id": node_id, "online": True, "channels": channels, "area": area})

    async def _on_telemetry(self, topic: str, payload: dict):
        node_id = topic.split("/")[-1]
        self.registry.update_heartbeat(node_id)
        if isinstance(payload, dict):
            # chuẩn hoá compact keys p→power cho WebUI
            norm = dict(payload)
            if "p" in norm and "power" not in norm: norm["power"] = norm["p"]
            if "v" in norm and "voltage" not in norm: norm["voltage"] = norm["v"]
            if "i" in norm and "current" not in norm: norm["current"] = norm["i"]
            self.broadcast_event("node_telemetry", {"node_id": node_id, **norm})
        if self.telemetry_writer:
            node_info = self.registry.get_all_nodes().get(node_id, {})
            area = node_info.get("room", node_info.get("area", "unknown"))
            for ch_id, ch_info in node_info.get("channels", {}).items():
                self.telemetry_writer.write_telemetry(
                    node_id=node_id, area=area,
                    device_type=ch_info.get("device_type", "unknown"),
                    channel=ch_id, telemetry=payload,
                )

    async def _on_status(self, topic: str, payload: dict):
        node_id = topic.split("/")[-1]
        self.registry.update_heartbeat(node_id)
        if isinstance(payload, dict):
            # compact ack: {"t":"ack","id":"...","rl":[1,0],"seq":n}
            if payload.get("t") == "ack":
                rl = payload.get("rl", [])
                self.broadcast_event("node_status", {
                    "node_id": node_id, "rl_state": rl, "seq": payload.get("seq"),
                    "ch1": rl[0] if len(rl)>0 else None, "ch2": rl[1] if len(rl)>1 else None
                })
            else:
                self.broadcast_event("node_status", payload)

    # ── WebUI gọi: provision node pending ───────────────────────────────
    async def provision_pending(self, mac: str, room: str, rl1: str, rl2: str, node_short: str = None) -> dict:
        node = self.registry.provision_node(mac, room, rl1, rl2, node_short=node_short)
        if not node:
            return {"success": False, "error": "MAC not in pending or invalid"}
        node_id = node["node_id"]
        cfg = self.registry.get_provision_payload(node_id)
        # gửi qua MQTT retain + nếu node đang giữ WS thì hello tiếp theo sẽ nhận
        await self.mqtt.send_cfg(mac, cfg)          # cho node chưa có id
        await self.mqtt.send_cfg(node_id, cfg)      # cho lần sau
        self.broadcast_event("node_provisioned", {"node_id": node_id, "cfg": cfg})
        self.broadcast_event("pending_remove", {"mac": mac.upper()})
        return {"success": True, "node_id": node_id, "cfg": cfg}


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
    logger.info("Shutting down...")
    gateway._running = False
    await gateway.audio_server.stop()
    await gateway.web_server.stop()
    for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
        t.cancel()

if __name__ == "__main__":
    asyncio.run(main())
