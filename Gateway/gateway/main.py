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
from display_names import get_room_name, get_device_name, clean_voice_text
from web_server import WebServer
from discovery_manager import DiscoveryManager
from ota_manager import OTAManager
from auth_manager import AuthManager
from sound_manager import SoundManager

# Optional AI Modules (chỉ load khi AI_ENABLED = True)
if getattr(config, "AI_ENABLED", False):
    try:
        from memory_engine import MemoryEngine
    except Exception:
        MemoryEngine = None
    try:
        from persona_engine import PersonaEngine
    except Exception:
        PersonaEngine = None
    try:
        from proactive_agent import ProactiveAgent
    except Exception:
        ProactiveAgent = None
else:
    MemoryEngine = None
    PersonaEngine = None
    ProactiveAgent = None

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
        self.verifier = CommandVerifier(self.mqtt, self.registry)
        # verifier cần biết audio_server để chọn WS vs MQTT
        self.verifier.audio_server = self.audio_server
        self.discovery = DiscoveryManager(self)
        self.ota = OTAManager(self)
        self.auth = AuthManager()
        self.sound = SoundManager(self)
        self.web_server = WebServer(self)

        # AI Optional Modules — Tạm thời bỏ qua/tắt mặc định, ưu tiên thuần relay voice control
        self.memory = MemoryEngine() if (getattr(config, "AI_ENABLED", False) and MemoryEngine) else None
        self.persona = PersonaEngine() if (getattr(config, "PERSONA_ENABLED", False) and PersonaEngine) else None
        self.proactive = ProactiveAgent(self) if (getattr(config, "PROACTIVE_ENABLED", False) and ProactiveAgent) else None

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

        logger.info("Initializing ASR engine (with dynamic registry hotwords)...")
        self.asr.initialize(self.registry)

        await self.audio_server.start()
        await self.web_server.start()

        if self.telemetry_writer:
            self.telemetry_writer.initialize()

        # MQTT handlers: compact + legacy + Home Assistant Discovery
        self._subbox_voice_requests = {}
        self.mqtt.on_message("home/subbox/+/voice/request", self._on_subbox_voice)
        self.mqtt.on_message("home/subbox/+/event/actionbox", self._on_subbox_actionbox)
        self.mqtt.on_message("smarthome/hello", self._on_hello)
        self.mqtt.on_message("smarthome/register", self._on_node_register)  # legacy
        self.mqtt.on_message("smarthome/discovery/#", self._on_native_discovery)
        self.mqtt.on_message("homeassistant/#", self._on_ha_discovery)
        self.mqtt.on_message("smarthome/telemetry/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/tele/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/status/#", self._on_status)
        self.mqtt.on_message("smarthome/ota/progress/#", self._on_ota_progress)
        self.mqtt.on_message("smarthome/ota_progress/#", self._on_ota_progress)

        # Spec v1.0 Industrial Device OS Topics:
        self.mqtt.on_message("home/discovery/unclaimed", self._on_unclaimed_device)
        self.mqtt.on_message("home/devices/+/status", self._on_device_status)
        self.mqtt.on_message("home/devices/+/telemetry", self._on_device_telemetry)
        self.mqtt.on_message("home/devices/+/config/reported", self._on_reported_config)
        self.mqtt.on_message("home/devices/+/relay/+/state", self._on_device_relay_state)

        self._running = True
        asyncio.create_task(self._announce_all_nodes())
        if hasattr(self, "proactive") and self.proactive:
            self.proactive.start()
        # ESP32 nodes play bootup sound locally on hardware init; avoid re-broadcasting over WS on gateway start
        # if hasattr(self, "sound") and self.sound:
        #     asyncio.create_task(self._play_bootup_sound())
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
            reply = "Đã hủy lệnh."
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
            reply = "Đang phát chuông báo thức."
            result["voice_reply"] = reply
            result["verify"] = "alarm_played"
            result["follow_up"] = False
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "alarm_played", "follow_up": False
            })
            if hasattr(self, "sound") and self.sound:
                asyncio.create_task(self.sound.play_sound_and_speak(SoundManager.SOUND_MORNING, reply, target_node=client_node_id))
            return result

        # ─── BƯỚC 0: Hội thoại người thật (CHỈ chạy khi bật option AI / Persona) ───
        if getattr(config, "PERSONA_ENABLED", False) and hasattr(self, "persona") and self.persona and self.persona.is_conversational(user_text):
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
            intent = await self.intent.extract(user_text, session_key=client_node_id)
            result["engine"] = getattr(self.intent, "active_engine", "unknown")
            logger.info(f'Engine selected: {result["engine"]}')

            if not intent or not self.intent.validate_intent(intent):
                if hasattr(self, "sound") and self.sound:
                    asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
                reply = "Chưa rõ khẩu lệnh."
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
                reply = intent.get("voice_reply") or "Chưa rõ khẩu lệnh."
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

        # Xử lý lệnh toàn bộ thiết bị (Bulk turn_on / turn_off)
        if device == "all" and action in ("turn_on", "turn_off"):
            all_online = self.registry.get_online_nodes()
            room_filter = str(location).lower().strip() if location else None
            affected_count = 0
            failed_count = 0
            for nid, node in all_online.items():
                if room_filter and str(node.get("room", "")).lower().strip() != room_filter:
                    continue
                for cid in node.get("channels", {}).keys():
                    seq = self.registry.next_seq(nid)
                    verified, *_ = await self.verifier.verify_command(nid, cid, action, seq=seq)
                    if verified == VerifyResult.SUCCESS:
                        affected_count += 1
                    else:
                        failed_count += 1
            r_vn = get_room_name(location)
            act_vn = "bật" if action == "turn_on" else "tắt"
            if r_vn:
                reply = f"Đã {act_vn} thiết bị ở {r_vn}."
            else:
                reply = f"Đã {act_vn} tất cả thiết bị."
            if not affected_count:
                reply = "Chưa có thiết bị nào xác nhận lệnh."
            elif failed_count:
                reply = f"Có {affected_count} thiết bị xác nhận, {failed_count} thiết bị chưa xác nhận."
            result["verify"] = "success" if affected_count and not failed_count else "partial" if affected_count else "timeout"
            result["voice_reply"] = reply

            fb_mode = getattr(config, "AUDIO_FEEDBACK_MODE", "hybrid").lower()
            if result["verify"] == "success" and fb_mode in ("hybrid", "chime") and hasattr(self, "sound") and self.sound:
                chime = self.sound.get_pcm_data(SoundManager.SOUND_LISTEN_SUCCESS)
                if chime:
                    result["tts_audio"] = chime
                    result["tts_format"] = "pcm"
                    result["audio_effect"] = SoundManager.SOUND_LISTEN_SUCCESS
            if not result.get("tts_audio"):
                pcm = await self.tts.synthesize_pcm(reply)
                result["tts_audio"] = pcm or await self.tts.synthesize(reply)
                result["tts_format"] = "pcm" if pcm else "mp3"

            result["follow_up"] = False
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": result["verify"], "engine": result["engine"], "follow_up": False
            })
            logger.info(f"Bulk {action} executed for {affected_count} channels (room={location})")
            return result

        # Lớp 2: phân giải node_id/channel TỪ REGISTRY THỰC TẾ — không bao giờ bịa
        lookup = self.registry.find_node_by_device(device, location)
        if not lookup:
            if hasattr(self, "sound") and self.sound:
                asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
            # Phân biệt: mơ hồ (nhiều node cùng tên) vs không tồn tại
            all_online = self.registry.get_online_nodes()
            if not all_online:
                reply = "Chưa có thiết bị kết nối."
                follow_up = False
            elif device and location:
                dev_name = get_device_name(device)
                room_name = get_room_name(location)
                reply = clean_voice_text(f"Không tìm thấy {dev_name} ở {room_name}.")
                follow_up = False
            elif device and not location:
                # mơ hồ: có nhiều node cùng device nhưng không nói phòng -> Hỏi lại và mở mic!
                room_names = [get_room_name(r) for r in self.registry.allowed_rooms()]
                dev_name = get_device_name(device)
                reply = clean_voice_text(f"Điều khiển {dev_name} ở phòng nào?")
                follow_up = True
                self.dialog._sessions[client_node_id] = DialogSession(
                    node_id=client_node_id, client_id=client_node_id,
                    pending_intent=intent, missing_slot="location"
                )
            else:
                reply = intent.get("voice_reply") or "Chưa rõ thiết bị cần điều khiển."
                reply = clean_voice_text(reply)
                follow_up = True
                self.dialog._sessions[client_node_id] = DialogSession(
                    node_id=client_node_id, client_id=client_node_id,
                    pending_intent=intent, missing_slot="device"
                )
            result["voice_reply"] = reply
            result["follow_up"] = follow_up
            pcm = await self.tts.synthesize_pcm(reply)
            result["tts_audio"] = pcm or await self.tts.synthesize(reply)
            result["tts_format"] = "pcm" if pcm else "mp3"
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

        action_str = "bật" if action == "turn_on" else "tắt"
        dev_str = get_device_name(device or channel)
        room_str = get_room_name(location)
        if verify_result == VerifyResult.SUCCESS:
            if room_str:
                voice_reply = intent.get("voice_reply") or f"Đã {action_str} {dev_str} {room_str}."
            else:
                voice_reply = intent.get("voice_reply") or f"Đã {action_str} {dev_str}."
        else:
            voice_reply = self.verifier.generate_failure_message(action, device or channel, location or "", verify_result)

        # Luôn làm sạch voice_reply để loại bỏ id_room hay fullname trước khi phát ra loa
        voice_reply = clean_voice_text(voice_reply)
        result["voice_reply"] = voice_reply

        # ─── Acoustic Feedback Engine (Tinh tế, êm dịu, sang trọng) ───
        fb_mode = getattr(config, "AUDIO_FEEDBACK_MODE", "hybrid").lower()
        if fb_mode in ("hybrid", "chime") and verify_result == VerifyResult.SUCCESS:
            chime_pcm = self.sound.get_pcm_data(SoundManager.SOUND_LISTEN_SUCCESS) if hasattr(self, "sound") and self.sound else None
            if chime_pcm:
                result["tts_audio"] = chime_pcm
                result["tts_format"] = "pcm"
                result["audio_effect"] = SoundManager.SOUND_LISTEN_SUCCESS
            else:
                pcm = await self.tts.synthesize_pcm(voice_reply)
                result["tts_audio"] = pcm or await self.tts.synthesize(voice_reply)
                result["tts_format"] = "pcm" if pcm else "mp3"
        elif fb_mode == "chime" and verify_result == VerifyResult.FAILED:
            wrong_pcm = self.sound.get_pcm_data(SoundManager.SOUND_WRONG) if hasattr(self, "sound") and self.sound else None
            if wrong_pcm:
                result["tts_audio"] = wrong_pcm
                result["tts_format"] = "pcm"
                result["audio_effect"] = SoundManager.SOUND_WRONG
        else:
            pcm = await self.tts.synthesize_pcm(voice_reply)
            if pcm:
                result["tts_audio"] = pcm
                result["tts_format"] = "pcm"
            else:
                result["tts_audio"] = await self.tts.synthesize(voice_reply)
                result["tts_format"] = "mp3"

        if hasattr(self, "memory") and self.memory:
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
    async def _on_subbox_voice(self, topic, payload):
        if not isinstance(payload, dict):
            return
        text, origin, request = payload.get("text"), payload.get("origin_node"), payload.get("request_id")
        if not isinstance(text, str) or not text.strip() or len(text) > 256 or not isinstance(origin, str) or not isinstance(request, int):
            return
        subbox = topic.split("/")[2]
        key = (subbox, origin, request)
        response_topic = f"home/subbox/{subbox}/voice/response"
        if key in self._subbox_voice_requests:
            cached = self._subbox_voice_requests[key]
            if cached is not None:
                await self.mqtt.publish(response_topic, cached)
            return
        if len(self._subbox_voice_requests) >= 128:
            oldest = next((k for k, v in self._subbox_voice_requests.items() if v is not None), None)
            if oldest is None:
                return
            self._subbox_voice_requests.pop(oldest)
        self._subbox_voice_requests[key] = None
        try:
            result = await self.process_voice_command(text, client_node_id=f"{subbox}:{origin}")
            response = {"origin_node": origin, "request_id": request,
                        "voice_reply": result.get("voice_reply", ""), "verify": result.get("verify")}
        except Exception:
            logger.exception("SubBox voice request failed")
            response = {"origin_node": origin, "request_id": request, "voice_reply": "Không thể xử lý yêu cầu."}
        self._subbox_voice_requests[key] = response
        await self.mqtt.publish(response_topic, response)

    async def _on_subbox_actionbox(self, topic, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("channels"), list):
            return
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            return
        channels = payload["channels"]
        if node_id not in self.registry.get_all_nodes():
            # Discovery uses the existing provisioning UI; never invent an approved device.
            if node_id not in self.registry.data.get("pending", {}):
                identity = self.mqtt.node_identities.get(node_id)
                if not identity or node_id in self.mqtt.conflicting_nodes:
                    return
                uid = identity["hardware_uid"]
                self.registry.on_hello({"id": node_id, "hardware": "ActionBox", "state": "FACTORY_NEW",
                    "serial": uid, "mac": ":".join(uid[i:i+2] for i in range(0, 12, 2))})
            return
        states = {c.get("channel"): c.get("state") == "ON" for c in channels if isinstance(c, dict)}
        if 1 in states and 2 in states:
            self.registry.update_relay_state(node_id, [int(states[1]), int(states[2])])
        self.registry.update_heartbeat(node_id)

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
                self.mqtt.record_compact_ack(node_id, payload)
                rl = payload.get("rl", [])
                if rl and hasattr(self.registry, "update_relay_state"):
                    self.registry.update_relay_state(node_id, rl)
                self.broadcast_event("node_status", {
                    "node_id": node_id, "rl_state": rl, "seq": payload.get("seq"),
                    "ch1": rl[0] if len(rl)>0 else None, "ch2": rl[1] if len(rl)>1 else None
                })
            else:
                self.broadcast_event("node_status", payload)

    async def _on_ota_progress(self, topic: str, payload: Any):
        """Broadcast OTA flashing progress from ESP32 nodes to Web UI and update task state."""
        node_id = topic.split("/")[-1] if "/" in topic else "unknown"
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except Exception:
                data = {"raw": payload}

        if isinstance(data, dict) and data.get("node_id"):
            node_id = data["node_id"]

        progress = data.get("progress", 0) if isinstance(data, dict) else 0
        status = data.get("status", "flashing") if isinstance(data, dict) else "flashing"
        msg = (data.get("message") or data.get("msg") or "") if isinstance(data, dict) else ""

        if hasattr(self, "ota") and self.ota:
            self.ota.update_task_progress(node_id, progress, status, msg)

        logger.info(f"⚡ [OTA Progress] {node_id}: {progress}% - {status} ({msg})")

        self.broadcast_event("ota_progress", {
            "node_id": node_id,
            "progress": progress,
            "status": status,
            "message": msg
        })

    async def _on_ha_discovery(self, topic: str, payload: Any):
        """Home Assistant discovery config received over MQTT."""
        self.discovery.handle_ha_discovery(topic, payload)

    async def _on_native_discovery(self, topic: str, payload: Any):
        """Native ESP32 discovery announcement received over MQTT."""
        self.discovery.handle_native_discovery(topic, payload)

    async def _announce_all_nodes(self):
        """Broadcast Home Assistant discovery configs for all registered nodes."""
        await asyncio.sleep(2)
        for nid in list(self.registry.get_all_nodes().keys()):
            await self.discovery.publish_ha_discovery_for_node(nid)

    # ── WebUI gọi: provision node pending ───────────────────────────────
    async def provision_pending(self, mac_or_id: str, room: str, rl1: str, rl2: str,
                                node_short: str = None, name: str = None,
                                location: str = None, description: str = None) -> dict:
        node = self.registry.provision_node(
            mac_or_id, room, rl1, rl2,
            node_short=node_short, name=name, location=location, description=description
        )
        if not node:
            return {"success": False, "error": "Target node not in pending or invalid"}
        node_id = node.get("device_id") or node.get("node_id")
        mac = node.get("mac", "")
        cfg = self.registry.get_provision_payload(node_id)
        # Gửi qua MQTT retain cho cả MAC và device_id
        if mac:
            await self.mqtt.send_cfg(mac, cfg)
        await self.mqtt.send_cfg(node_id, cfg)
        # Công bố Home Assistant discovery để HA phát hiện node ngay lập tức
        await self.discovery.publish_ha_discovery_for_node(node_id)
        self.broadcast_event("node_provisioned", {"node_id": node_id, "device_id": node_id, "cfg": cfg})
        if mac:
            self.broadcast_event("pending_remove", {"mac": mac.upper(), "device_id": node_id})
        return {"success": True, "device_id": node_id, "node_id": node_id, "cfg": cfg}

    # ── Device OS Twin Handlers (Spec Section 4, 8 & 9) ─────────────────
    async def _on_unclaimed_device(self, topic: str, payload: Any):
        """Thiết bị xuất xưởng / unprovisioned phát hiện qua home/discovery/unclaimed"""
        if not isinstance(payload, dict):
            try:
                payload = json.loads(payload)
            except Exception:
                return
        logger.info(f"🆕 [Discovery] Unclaimed Device: {payload.get('device_id')} ({payload.get('serial')})")
        res = self.registry.on_hello(payload, ws_available=False)
        self.broadcast_event("pending_device", payload)

    async def _on_device_status(self, topic: str, payload: Any):
        """Nhận LWT / online status từ home/devices/{device_id}/status"""
        parts = topic.split("/")
        if len(parts) < 4:
            return
        device_id = parts[2]
        self.registry.update_heartbeat(device_id)

        status_str = "online"
        if isinstance(payload, dict):
            status_str = payload.get("state", payload.get("status", "online"))
        elif isinstance(payload, str):
            status_str = payload.lower()

        if status_str == "offline":
            self.registry.mark_offline(device_id)
            self.broadcast_event("node_status", {"node_id": device_id, "online": False, "status": "offline"})
        else:
            self.broadcast_event("node_status", {"node_id": device_id, "online": True, "status": "online"})

    async def _on_device_telemetry(self, topic: str, payload: Any):
        """Nhận telemetry định kỳ từ home/devices/{device_id}/telemetry"""
        parts = topic.split("/")
        if len(parts) < 4:
            return
        device_id = parts[2]
        if not isinstance(payload, dict):
            try:
                payload = json.loads(payload)
            except Exception:
                return
        self.registry.record_telemetry(device_id, payload)
        self.broadcast_event("node_telemetry", {"node_id": device_id, "device_id": device_id, **payload})

    async def _on_reported_config(self, topic: str, payload: Any):
        """Nhận reported configuration từ node: home/devices/{device_id}/config/reported"""
        parts = topic.split("/")
        if len(parts) < 5:
            return
        device_id = parts[2]
        if not isinstance(payload, dict):
            try:
                payload = json.loads(payload)
            except Exception:
                return
        sync_status = self.registry.on_reported_config(device_id, payload)
        self.broadcast_event("node_config_sync", {
            "device_id": device_id,
            "reported": payload,
            "sync_status": sync_status
        })

    async def _on_device_relay_state(self, topic: str, payload: Any):
        """Nhận trạng thái relay độc lập: home/devices/{device_id}/relay/{channel}/state"""
        parts = topic.split("/")
        if len(parts) < 5:
            return
        device_id = parts[2]
        channel = parts[4]
        state = 0
        if isinstance(payload, dict):
            state = payload.get("state", 0)
        elif isinstance(payload, (int, str)):
            state = 1 if str(payload) in ("1", "true", "on") else 0

        self.registry.update_heartbeat(device_id)
        cur_rl = None
        if hasattr(self.registry, "update_relay_state") and device_id in self.registry.data.get("nodes", {}):
            n = self.registry.data["nodes"][device_id]
            cur_rl = list(n.get("relay_state", [0, 0]))
            ch_idx = 0 if channel in ("1", "ch1", 1) else 1
            if ch_idx < len(cur_rl):
                cur_rl[ch_idx] = 1 if state else 0
            self.registry.update_relay_state(device_id, cur_rl)

        evt = {
            "node_id": device_id,
            "channel": channel,
            "state": state
        }
        if cur_rl is not None:
            evt["rl_state"] = cur_rl
        self.broadcast_event("node_status", evt)

    async def update_device_desired_config(self, device_id: str, desired_dict: dict) -> dict:
        """Cập nhật Desired Configuration Twin và phát MQTT QoS 1 retain"""
        new_v, desired_payload = self.registry.update_desired_config(device_id, desired_dict)
        # Gửi topic industrial
        await self.mqtt.send_desired_config(device_id, desired_payload)
        # Gửi thêm legacy cfg topic
        legacy_cfg = self.registry.get_provision_payload(device_id)
        if legacy_cfg:
            await self.mqtt.send_cfg(device_id, legacy_cfg)
        self.broadcast_event("node_config_desired", {
            "device_id": device_id,
            "desired": desired_payload,
            "sync_status": "SYNCING"
        })
        return {"success": True, "device_id": device_id, "version": new_v, "sync_status": "SYNCING"}

    async def update_device(self, device_id: str, update_dict: dict) -> dict:
        """Cập nhật thông tin và cấu hình thiết bị, đồng bộ tức thì xuống ESP32."""
        updated = self.registry.update_device(device_id, update_dict)
        cfg_payload = self.registry.get_provision_payload(device_id)
        if cfg_payload and self.mqtt:
            await self.mqtt.send_cfg(device_id, cfg_payload)
            await self.mqtt.send_desired_config(device_id, cfg_payload)
        if hasattr(self, "asr") and self.asr:
            try:
                self.asr.reload_hotwords(self.registry)
            except Exception as e:
                logger.warning(f"Failed to reload ASR hotwords after device update: {e}")
        self.broadcast_event("node_status", {"node_id": device_id, "updated": True})
        return updated

    async def add_device_alias(self, device_id: str, channel: str, alias: str) -> dict:
        """Thêm khẩu lệnh/từ vựng cho thiết bị, cập nhật STT hotwords và broadcast event."""
        ok = self.registry.add_device_alias(device_id, channel, alias)
        if ok and hasattr(self, "asr") and self.asr:
            try:
                self.asr.reload_hotwords(self.registry)
                logger.info(f"[VOCAB][STT] vocabulary updated, active vocabulary contains '{alias}' = {self.asr.has_hotword(alias)}")
            except Exception as e:
                logger.warning(f"Failed to reload ASR hotwords: {e}")
        self.broadcast_event("node_status", {"node_id": device_id.split("::")[0], "updated": True})
        return {"success": ok, "device_id": device_id, "channel": channel, "alias": alias}

    async def remove_device_alias(self, device_id: str, channel: str, alias: str) -> dict:
        """Xóa khẩu lệnh/từ vựng cho thiết bị, cập nhật STT hotwords và broadcast event."""
        ok = self.registry.remove_device_alias(device_id, channel, alias)
        if ok and hasattr(self, "asr") and self.asr:
            try:
                self.asr.reload_hotwords(self.registry)
                logger.info(f"[VOCAB][STT] vocabulary updated, active vocabulary contains '{alias}' = {self.asr.has_hotword(alias)}")
            except Exception as e:
                logger.warning(f"Failed to reload ASR hotwords: {e}")
        self.broadcast_event("node_status", {"node_id": device_id.split("::")[0], "updated": True})
        return {"success": ok, "device_id": device_id, "channel": channel, "alias": alias}

    def get_voice_vocabulary_diagnostics(self) -> dict:
        """Thu thập thông tin chẩn đoán từ vựng và nhận diện giọng nói."""
        asr_diag = self.asr.dump_active_vocabulary(self.registry) if hasattr(self, "asr") and self.asr else {"initialized": False, "hotwords_count": 0, "hotwords": []}
        stored = []
        for nid, n in self.registry.get_all_nodes().items():
            for cid, ch in n.get("channels", {}).items():
                aliases = ch.get("aliases", [])
                stored.append({
                    "device_id": f"{nid}::{cid}",
                    "node_id": nid,
                    "channel": cid,
                    "name": ch.get("name", cid),
                    "device_type": ch.get("device_type", ""),
                    "aliases": list(aliases),
                })
        return {
            "success": True,
            "gateway_connected": True,
            "stt_engine": asr_diag,
            "stored_vocabulary": stored,
            "total_stored_items": len(stored),
            "total_active_hotwords": asr_diag.get("hotwords_count", 0),
        }

    async def delete_device(self, device_id: str) -> bool:
        """Xóa hoàn toàn thiết bị khỏi registry, đóng kết nối socket, broadcast event."""
        ok = self.registry.delete_node(device_id)
        if hasattr(self, "audio_server") and hasattr(self.audio_server, "_ws_nodes"):
            ws = self.audio_server._ws_nodes.pop(device_id, None)
            if ws and hasattr(self.audio_server, "_active_speakers"):
                self.audio_server._active_speakers.discard(ws)
        self.broadcast_event("device_deleted", {"device_id": device_id})
        return ok



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
