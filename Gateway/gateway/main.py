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
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from registry_manager import RegistryManager
from mqtt_handler import MQTTHandler
from intent_engine import IntentEngine
from dialog_manager import DialogManager, DialogSession
from tts_engine import TTSEngine
from asr_engine import ASREngine
from audio_server import AudioServer
from verify_engine import CommandVerifier, VerifyResult
from memory_engine import MemoryEngine
from display_names import get_room_name, get_device_name, clean_voice_text
from web_server import WebServer
from discovery_manager import DiscoveryManager
from persona_engine import PersonaEngine
from proactive_agent import ProactiveAgent
from ota_manager import OTAManager
from auth_manager import AuthManager
from sound_manager import SoundManager

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
        self.dialog = DialogManager(registry=self.registry)
        self.tts = TTSEngine()
        self.asr = ASREngine()
        self.audio_server = AudioServer(self)
        self.memory = MemoryEngine()
        self.verifier = CommandVerifier(self.mqtt, self.registry)
        # verifier cần biết audio_server để chọn WS vs MQTT
        self.verifier.audio_server = self.audio_server
        self.discovery = DiscoveryManager(self)
        self.persona = PersonaEngine()
        self.proactive = ProactiveAgent(self)
        self.ota = OTAManager(self)
        self.auth = AuthManager()
        self.sound = SoundManager(self)
        self.web_server = WebServer(self)

        self.telemetry_writer = None
        if HAS_INFLUX:
            self.telemetry_writer = TelemetryWriter()
        self._running = False

    def broadcast_event(self, event_type: str, data: dict):
        """Send SSE event to WebUI and subscribers."""
        if hasattr(self, "web_server") and self.web_server:
            if hasattr(self.web_server, "broadcast_event"):
                self.web_server.broadcast_event(event_type, data)
            elif hasattr(self.web_server, "broadcast"):
                self.web_server.broadcast(event_type, data)

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

        # MQTT handlers: compact + legacy + Home Assistant Discovery
        self.mqtt.on_message("smarthome/hello", self._on_hello)
        self.mqtt.on_message("smarthome/register", self._on_node_register)  # legacy
        self.mqtt.on_message("smarthome/discovery/#", self._on_native_discovery)
        self.mqtt.on_message("homeassistant/#", self._on_ha_discovery)
        self.mqtt.on_message("smarthome/telemetry/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/tele/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/status/#", self._on_status)
        self.mqtt.on_message("smarthome/ota/progress/#", self._on_ota_progress)

        self._running = True
        asyncio.create_task(self._announce_all_nodes())
        if hasattr(self, "proactive") and self.proactive:
            self.proactive.start()
        if hasattr(self, "sound") and self.sound:
            asyncio.create_task(self._play_bootup_sound())
        logger.info("Starting MQTT client...")
        try:
            await self.mqtt.connect()
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            await asyncio.sleep(5)
            await self.start()

    async def _play_bootup_sound(self):
        try:
            await asyncio.sleep(2.5)
            await self.sound.play_sound(SoundManager.SOUND_BOOTUP)
        except Exception as e:
            logger.debug(f"Bootup sound task error: {e}")

    # ── Voice pipeline (2 lớp, chống ảo giác + Multi-Turn Dialog) ─────────
    async def process_voice_command(
        self,
        user_text: str,
        client_node_id: str = "default",
        detected_room: Optional[str] = None
    ) -> dict:
        result = {
            "user_text": user_text, "intent": None,
            "engine": None,
            "node_id": None, "channel": None, "fullname": None,
            "verify": None, "voice_reply": None, "tts_audio": None,
            "follow_up": False,
        }
        logger.info(f'Voice: "{user_text}" [client={client_node_id}, detected_room={detected_room}]')

        # Thông báo hoạt động người dùng cho Proactive Agent
        if hasattr(self, "proactive") and self.proactive:
            self.proactive.notify_user_activity(user_text)

        # Xử lý lệnh hủy trực tiếp
        if any(w in user_text.lower().strip().split() for w in ("thôi", "hủy", "dừng", "cancel")):
            self.dialog.clear_session(client_node_id)
            reply = "Dạ, em đã hủy lệnh cho anh rồi nè~"
            result["voice_reply"] = reply
            result["follow_up"] = False
            result["verify"] = "cancelled"
            result["tts_audio"] = await self.tts.synthesize(reply)
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "cancelled", "follow_up": False
            })
            return result

        # Xử lý lệnh báo thức / nhạc buổi sáng (Morning Alarm / Wakeup Sound)
        is_alarm = any(w in user_text.lower() for w in (
            "báo thức", "đặt báo thức", "đánh thức", "chuông báo thức",
            "bật nhạc buổi sáng", "nhạc buổi sáng", "morning sound", "âm thanh buổi sáng"
        ))
        if is_alarm:
            self.dialog.clear_session(client_node_id)
            reply = "Dạ, em phát giai điệu báo thức buổi sáng cho anh ngay đây ạ~ Chúc anh một ngày mới ngập tràn năng lượng nha anh!"
            result["voice_reply"] = reply
            result["verify"] = "alarm_played"
            result["follow_up"] = False
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "alarm_played", "follow_up": False
            })
            if hasattr(self, "sound") and self.sound:
                asyncio.create_task(self.sound.play_sound_and_speak(SoundManager.SOUND_MORNING, reply, target_node=client_node_id))
            return result

        # ─── BƯỚC 0: Hội thoại người thật / Hát hò / Hỏi thăm (Persona Engine) ───
        if hasattr(self, "persona") and self.persona and self.persona.is_conversational(user_text):
            self.dialog.clear_session(client_node_id)
            logger.info(f"🗣️ Conversational query detected: '{user_text}'")
            reply = await self.persona.reply(user_text)
            reply = clean_voice_text(reply)
            result["voice_reply"] = reply
            result["engine"] = f"Persona ({'Gemini' if self.persona.has_api_key else 'Local'})"
            result["verify"] = "conversational"
            result["follow_up"] = False

            pcm = await self.tts.synthesize_pcm(reply)
            if pcm:
                result["tts_audio"] = pcm
                result["tts_format"] = "pcm"
            else:
                result["tts_audio"] = await self.tts.synthesize(reply)
                result["tts_format"] = "mp3"

            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "conversational",
                "engine": result["engine"], "follow_up": False
            })
            return result

        # ─── BƯỚC 1: Kiểm tra xem client có đang trong phiên đối thoại dở dang không ───
        active_session = self.dialog.get_active_session(client_node_id)
        if active_session:
            # Nếu người dùng nói một lệnh mới (có từ khóa hành động bật/tắt/mở/đóng...), tự động hủy session cũ
            is_new_command = any(w in user_text.lower() for w in ("bật", "tắt", "mở", "đóng", "cài", "đặt", "chỉnh", "bạn bè"))
            if is_new_command:
                logger.info(f"🔄 User issued fresh command during session for {client_node_id}. Clearing stale session.")
                self.dialog.clear_session(client_node_id)
                active_session = None

        if active_session:
            logger.info(f"🔄 Follow-Up detected for {client_node_id} (filling slot: {active_session.missing_slot})")
            intent = self.dialog.fill_slot(active_session, user_text)
            self.dialog.clear_session(client_node_id)
            result["engine"] = f"{getattr(self.intent, 'active_engine', 'Hybrid')} (Follow-Up)"
        else:
            intent = await self.intent.extract(user_text)
            result["engine"] = getattr(self.intent, "active_engine", "unknown")
            logger.info(f'Engine selected: {result["engine"]}')

            if not intent or not self.intent.validate_intent(intent):
                if hasattr(self, "sound") and self.sound:
                    asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
                reply = "Dạ, em nghe chưa hiểu ý anh lắm. Anh nói lại với em nha~"
                result["voice_reply"] = reply
                result["follow_up"] = True
                result["tts_audio"] = await self.tts.synthesize(reply)
                self.broadcast_event("command_result", {
                    "voice_reply": reply, "verify": "parse_error",
                    "engine": result["engine"], "follow_up": True
                })
                return result

            # ─── BƯỚC 1.5: Kiểm tra nếu intent là unknown (câu nói không rõ hoặc bị từ chối) ───
            cmd = intent.get("command", {})
            if cmd.get("action") == "unknown":
                if hasattr(self, "sound") and self.sound:
                    asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
                reply = intent.get("voice_reply") or "Dạ em nghe chưa rõ khẩu lệnh. Anh muốn em bật tắt thiết bị nào ở phòng nào vậy anh?"
                reply = clean_voice_text(reply)
                result["voice_reply"] = reply
                result["follow_up"] = True
                result["verify"] = "unknown_intent"
                result["tts_audio"] = await self.tts.synthesize(reply)
                self.broadcast_event("command_result", {
                    "voice_reply": reply, "verify": "unknown_intent",
                    "engine": result["engine"], "follow_up": True
                })
                logger.info(f"❓ Unknown intent rejected decisively: {reply} (Follow-Up ACTIVE)")
                return result

            # ─── BƯỚC 2: Kiểm tra thiếu slot / mơ hồ cần hỏi lại người dùng ───
            needs_clarify, clarify_q, missing_slot, intent = self.dialog.inspect_intent(
                intent, detected_room=detected_room, client_key=client_node_id
            )
            if needs_clarify:
                result["intent"] = intent
                result["voice_reply"] = clarify_q
                result["follow_up"] = True
                result["verify"] = "clarification_needed"
                result["tts_audio"] = await self.tts.synthesize(clarify_q)
                self.broadcast_event("command_result", {
                    "voice_reply": clarify_q, "verify": "clarification_needed",
                    "engine": result["engine"], "follow_up": True
                })
                logger.info(f"❓ Clarification requested: {clarify_q} (Follow-Up ACTIVE)")
                return result

        result["intent"] = intent
        cmd = intent["command"]
        device = cmd.get("device")
        location = cmd.get("location")
        action = cmd.get("action", "turn_on")

        # Xử lý lệnh toàn bộ thiết bị (Bulk turn_off)
        if device == "all" and action == "turn_off":
            all_online = self.registry.get_online_nodes()
            room_filter = str(location).lower().strip() if location else None
            turned_off_count = 0
            for nid, node in all_online.items():
                if room_filter and str(node.get("room", "")).lower().strip() != room_filter:
                    continue
                for cid in node.get("channels", {}).keys():
                    seq = self.registry.next_seq(nid)
                    await self.verifier.verify_command(nid, cid, "turn_off", seq=seq)
                    turned_off_count += 1
            r_vn = get_room_name(location)
            reply = f"Dạ, em đã tắt toàn bộ thiết bị ở {r_vn} cho anh rồi nè~" if r_vn else "Dạ, em đã tắt hết tất cả thiết bị trong nhà cho anh rồi nè~"
            result["voice_reply"] = reply
            result["tts_audio"] = await self.tts.synthesize(reply)
            result["verify"] = "success"
            result["follow_up"] = False
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "success", "engine": result["engine"], "follow_up": False
            })
            logger.info(f"Bulk turn_off executed for {turned_off_count} channels (room={location})")
            return result

        # Lớp 2: phân giải node_id/channel TỪ REGISTRY THỰC TẾ — không bao giờ bịa
        lookup = self.registry.find_node_by_device(device, location)
        if not lookup:
            if hasattr(self, "sound") and self.sound:
                asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
            # Phân biệt: mơ hồ (nhiều node cùng tên) vs không tồn tại
            all_online = self.registry.get_online_nodes()
            if not all_online:
                reply = "Dạ anh ơi, hiện em chưa thấy có thiết bị nào trong nhà được kết nối. Anh thêm ở giao diện web giúp em nhé~"
                follow_up = False
            elif device and location:
                dev_name = get_device_name(device)
                room_name = get_room_name(location)
                reply = clean_voice_text(f"Dạ, em không tìm thấy {dev_name} ở {room_name} anh ơi. Anh kiểm tra lại giúp em nha~")
                follow_up = False
            elif device and not location:
                # mơ hồ: có nhiều node cùng device nhưng không nói phòng -> Hỏi lại và mở mic!
                room_names = [get_room_name(r) for r in self.registry.allowed_rooms()]
                dev_name = get_device_name(device)
                reply = clean_voice_text(f"Dạ anh muốn điều khiển {dev_name} ở phòng nào vậy anh? Em thấy có {', '.join(room_names)} nè~")
                follow_up = True
                self.dialog._sessions[client_node_id] = DialogSession(
                    node_id=client_node_id, client_id=client_node_id,
                    pending_intent=intent, missing_slot="location"
                )
            else:
                reply = intent.get("voice_reply") or "Dạ anh muốn điều khiển thiết bị nào và ở phòng nào vậy anh?"
                reply = clean_voice_text(reply)
                follow_up = True
                self.dialog._sessions[client_node_id] = DialogSession(
                    node_id=client_node_id, client_id=client_node_id,
                    pending_intent=intent, missing_slot="device"
                )
            result["voice_reply"] = reply
            result["follow_up"] = follow_up
            result["tts_audio"] = await self.tts.synthesize(reply)
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "not_found", "follow_up": follow_up
            })
            logger.warning(f"Resolver miss: device={device} location={location} (follow_up={follow_up})")
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
            voice_reply = intent.get("voice_reply") or f"Dạ, em đã {('bật' if action=='turn_on' else 'tắt')} {get_device_name(device)} ở {get_room_name(location)} cho anh rồi nè~"
        elif verify_result == VerifyResult.FAILED:
            voice_reply = self.verifier.generate_failure_message(action, device or channel, location or "", verify_result)
        else:
            voice_reply = intent.get("voice_reply") or "Dạ, em đã thực hiện xong cho anh rồi ạ~"

        # Luôn làm sạch voice_reply để loại bỏ id_room hay fullname trước khi phát ra loa
        voice_reply = clean_voice_text(voice_reply)
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

    async def _on_ota_progress(self, topic: str, payload: Any):
        """Broadcast OTA flashing progress from ESP32 nodes to Web UI."""
        node_id = topic.split("/")[-1]
        data = payload if isinstance(payload, dict) else {}
        self.broadcast_event("ota_progress", {
            "node_id": node_id,
            "progress": data.get("progress", 0),
            "status": data.get("status", "flashing"),
            "message": data.get("msg", "")
        })

    async def _on_ha_discovery(self, topic: str, payload: Any):
        """Home Assistant discovery config received over MQTT."""
        self.discovery.handle_ha_discovery(topic, payload)

    async def _on_native_discovery(self, topic: str, payload: Any):
        """Native ESP32 discovery announcement received over MQTT."""
        self.discovery.handle_native_discovery(topic, payload)

    async def _on_ota_progress(self, topic: str, payload: Any):
        """Handle OTA flashing progress updates from nodes."""
        node_id = topic.split("/")[-1] if "/" in topic else "unknown"
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except Exception:
                data = {"raw": payload}
        self.broadcast_event("ota_progress", {
            "node_id": node_id,
            "progress": data.get("progress", 0),
            "status": data.get("status", "progress"),
            "message": data.get("message") or data.get("msg", "")
        })

    async def _announce_all_nodes(self):
        """Broadcast Home Assistant discovery configs for all registered nodes."""
        await asyncio.sleep(2)
        for nid in list(self.registry.get_all_nodes().keys()):
            await self.discovery.publish_ha_discovery_for_node(nid)

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
        # Công bố Home Assistant discovery để HA phát hiện node ngay lập tức
        await self.discovery.publish_ha_discovery_for_node(node_id)
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
    if hasattr(gateway, "proactive") and gateway.proactive:
        await gateway.proactive.stop()
    await gateway.audio_server.stop()
    await gateway.web_server.stop()
    for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
        t.cancel()

if __name__ == "__main__":
    asyncio.run(main())
