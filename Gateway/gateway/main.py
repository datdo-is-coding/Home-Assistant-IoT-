"""
DTV Smart Home Gateway — Main Entry Point v2

Nâng cấp:
- Registry v2: quản lý theo phòng + fullname livingroom-node01-fan
- Intent 2 lớp: LLM chỉ trích ý định, Registry mới phân giải node_id/channel
- Relay dispatch: ưu tiên WebSocket TEXT frame (xen giữa PCM), fallback MQTT compact
- Pending/provision flow: node mới (cfg:null) → WebUI đăng ký → Gateway gửi cfg → node NVS
"""

import asyncio
import time
from datetime import datetime, timezone
import logging
import signal
import sys
import os
import json
import re
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from registry_manager import RegistryManager, ROOM_ALIASES, slug
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
from device_lifecycle import DeviceLifecycleManager

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

        self.intent.set_registry(self.registry)
        self.dialog = DialogManager(registry=self.registry)
        self.tts = TTSEngine()
        self.asr = ASREngine()
        self.audio_server = AudioServer(self)
        self.verifier = CommandVerifier(self.mqtt, self.registry)

        self.verifier.audio_server = self.audio_server
        self.discovery = DiscoveryManager(self)
        self.ota = OTAManager(self)
        self.auth = AuthManager()
        self.sound = SoundManager(self)
        self.web_server = WebServer(self)
        self.lifecycle = DeviceLifecycleManager(
            db_path=self.registry.db_path,
            registry=self.registry,
            mqtt=self.mqtt,
            discovery=self.discovery,
            broadcaster=self.broadcast_event,
            auth=self.auth,
        )

        self.memory = MemoryEngine() if (getattr(config, "AI_ENABLED", False) and MemoryEngine) else None
        self.persona = PersonaEngine() if (getattr(config, "PERSONA_ENABLED", False) and PersonaEngine) else None
        self.proactive = ProactiveAgent(self) if (getattr(config, "PROACTIVE_ENABLED", False) and ProactiveAgent) else None

        self.telemetry_writer = None
        if HAS_INFLUX:
            self.telemetry_writer = TelemetryWriter()
        self._running = False

    async def start(self):
        logger.info("=" * 60)
        logger.info("  DTV SMART HOME GATEWAY v2 — Starting Up")
        logger.info("  Inventory: %s", self.registry.inventory_for_prompt())
        logger.info("=" * 60)

        logger.info("Initializing ASR engine (with dynamic registry hotwords)...")
        self.asr.initialize(self.registry)
        if config.TTS_PROVIDER.strip().lower() == "vieneu":
            await self.tts.vieneu.initialize()

        await self.audio_server.start()
        await self.web_server.start()

        if self.telemetry_writer:
            self.telemetry_writer.initialize()

        self._subbox_voice_requests = {}
        self.mqtt.on_message("home/subbox/+/state", self._on_subbox_state)
        self.mqtt.on_message("home/subbox/+/voice/request", self._on_subbox_voice)
        self.mqtt.on_message("home/subbox/+/event/actionbox", self._on_subbox_actionbox)
        self.mqtt.on_message("smarthome/hello", self._on_hello)
        self.mqtt.on_message("smarthome/register", self._on_node_register)
        self.mqtt.on_message("smarthome/discovery/#", self._on_native_discovery)
        self.mqtt.on_message("homeassistant/#", self._on_ha_discovery)
        self.mqtt.on_message("smarthome/telemetry/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/tele/#", self._on_telemetry)
        self.mqtt.on_message("smarthome/status/#", self._on_status)
        self.mqtt.on_message("smarthome/ota/progress/#", self._on_ota_progress)
        self.mqtt.on_message("smarthome/ota_progress/#", self._on_ota_progress)

        self.mqtt.on_message("home/discovery/unclaimed", self._on_unclaimed_device)
        self.mqtt.on_message("home/devices/+/status", self._on_device_status)
        self.mqtt.on_message("home/devices/+/telemetry", self._on_device_telemetry)
        self.mqtt.on_message("home/devices/+/config/reported", self._on_reported_config)
        self.mqtt.on_message("home/devices/+/applied", self._on_device_applied_msg)
        self.mqtt.on_message("home/devices/+/relay/+/state", self._on_device_relay_state)
        self.mqtt.on_message("home/devices/+/operation/ack", self._on_device_operation_ack)
        self.mqtt.on_message("smarthome/operation/ack/#", self._on_device_operation_ack)

        self._running = True
        asyncio.create_task(self._announce_all_nodes())
        if hasattr(self, "proactive") and self.proactive:
            self.proactive.start()

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

    def _voice_inventory_reply(self, user_text: str) -> Optional[str]:
        text = slug(user_text).replace("_", " ")
        if not re.fullmatch(
            r"(?:(?:cho toi biet|cho minh biet) )?"
            r"(?:(?:(?:trong nha|nha minh|nha toi|he thong) )?(?:hien |dang )?"
            r"co (?:nhung |cac )?thiet bi (?:nao|gi)(?: trong nha)?"
            r"|liet ke (?:cac |nhung )?thiet bi(?: trong nha)?)"
            r"(?: nhi| vay| a)?", text
        ):
            return None

        groups = {}
        pending = self.registry.get_pending()
        for node_id, node in self.registry.get_all_nodes().items():
            # SubBox channels are legacy metadata, not household relay outputs.
            if (node_id in pending or str(node_id).upper().startswith("SB")
                    or "subbox" in str(node_id).lower()
                    or node.get("status") not in ("online", "offline")):
                continue
            room = slug(node.get("room", ""))
            room = next((key for key, aliases in ROOM_ALIASES.items() if room in aliases), room)
            for channel in node.get("channels", {}).values():
                name = get_device_name(channel)
                label = f"{name} ở {get_room_name(room)}" if room != "unknown" else name
                key = (node.get("status") != "online", label)
                groups[key] = groups.get(key, 0) + 1

        total = sum(groups.values())
        if not total:
            return "Nhà bạn chưa có thiết bị nào được đăng ký."
        shown = sorted(groups.items())[:5]
        items = [f"{str(count) + ' ' if count > 1 else ''}{label}"
                 + (", đang ngoại tuyến" if offline else "")
                 for (offline, label), count in shown]
        reply = f"Nhà bạn có {total} thiết bị đã đăng ký: " + "; ".join(items) + "."
        remaining = total - sum(count for _, count in shown)
        if remaining:
            reply += f" Còn {remaining} thiết bị khác, bạn có thể xem đầy đủ trong ứng dụng."
        return reply

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

        if hasattr(self, "proactive") and self.proactive:
            self.proactive.notify_user_activity(user_text)

        inventory_reply = self._voice_inventory_reply(user_text)
        if inventory_reply is not None:
            self.dialog.clear_session(client_node_id)
            result.update(voice_reply=inventory_reply, engine="Registry inventory",
                          verify="inventory", tts_format="pcm")
            result["tts_audio"] = await self.tts.synthesize_pcm(inventory_reply)
            self.broadcast_event("command_result", {
                "voice_reply": inventory_reply, "verify": "inventory", "follow_up": False
            })
            logger.info("Voice inventory: %s", inventory_reply)
            return result

        if any(w in user_text.lower().strip().split() for w in ("thôi", "hủy", "dừng", "cancel")):
            self.dialog.clear_session(client_node_id)
            reply = "Đã hủy lệnh."
            result["voice_reply"] = reply
            result["follow_up"] = False
            result["verify"] = "cancelled"
            result["tts_audio"] = await self.tts.synthesize_pcm(reply)
            self.broadcast_event("command_result", {
                "voice_reply": reply, "verify": "cancelled", "follow_up": False
            })
            return result

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

        active_session = self.dialog.get_active_session(client_node_id)
        if active_session:

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
                result["tts_audio"] = await self.tts.synthesize_pcm(reply)
                self.broadcast_event("command_result", {
                    "voice_reply": reply, "verify": "parse_error",
                    "engine": result["engine"], "follow_up": True
                })
                return result

            cmd = intent.get("command", {})
            if cmd.get("action") == "unknown":
                if hasattr(self, "sound") and self.sound:
                    asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))
                reply = intent.get("voice_reply") or "Chưa rõ khẩu lệnh."
                reply = clean_voice_text(reply)
                result["voice_reply"] = reply
                result["follow_up"] = True
                result["verify"] = "unknown_intent"
                result["tts_audio"] = await self.tts.synthesize_pcm(reply)
                self.broadcast_event("command_result", {
                    "voice_reply": reply, "verify": "unknown_intent",
                    "engine": result["engine"], "follow_up": True
                })
                logger.info(f"❓ Unknown intent rejected decisively: {reply} (Follow-Up ACTIVE)")
                return result

            needs_clarify, clarify_q, missing_slot, intent = self.dialog.inspect_intent(
                intent, detected_room=detected_room, client_key=client_node_id
            )
            if needs_clarify:
                result["intent"] = intent
                result["voice_reply"] = clarify_q
                result["follow_up"] = True
                result["verify"] = "clarification_needed"
                result["tts_audio"] = await self.tts.synthesize_pcm(clarify_q)
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

        is_scene = (intent.get("intent") == "scene" or action == "scene")
        if is_scene:
            scene_name = intent.get("scene") or cmd.get("value") or "sleep"
            scene_res = await self.execute_scene(scene_name)
            result.update({
                "device_results": scene_res["device_results"],
                "success": scene_res["success"],
                "verify": scene_res["verify"],
                "voice_reply": scene_res["voice_reply"],
                "follow_up": False,
            })
            pcm = await self.tts.synthesize_pcm(scene_res["voice_reply"])
            result["tts_audio"] = pcm or await self.tts.synthesize(scene_res["voice_reply"])
            result["tts_format"] = "pcm" if pcm else "mp3"
            self.broadcast_event("command_result", {
                "voice_reply": scene_res["voice_reply"],
                "verify": result["verify"],
                "engine": result["engine"],
                "device_results": scene_res["device_results"],
                "follow_up": False
            })
            return result

        if device == "all" and action in ("turn_on", "turn_off"):
            all_online = self.registry.get_online_nodes()
            room_filter = str(location).lower().strip() if location else None
            affected_count = 0
            failed_count = 0
            device_results = []
            targets = []
            for nid, node in all_online.items():
                if room_filter and str(node.get("room", "")).lower().strip() != room_filter:
                    continue
                for cid in node.get("channels", {}).keys():
                    seq = self.registry.next_seq(nid)
                    targets.append((nid, cid, seq))

            if targets:
                tasks = [
                    self.verifier.verify_command(nid, cid, action, seq=seq)
                    for nid, cid, seq in targets
                ]
                gathered_results = await asyncio.gather(*tasks, return_exceptions=True)
                for (nid, cid, seq), cmd_res in zip(targets, gathered_results):
                    if isinstance(cmd_res, Exception):
                        res_dict = {
                            "command_id": str(seq),
                            "node_id": nid,
                            "channel": cid,
                            "requested_state": "ON" if action in ("turn_on", "open", "on") else "OFF",
                            "confirmed_state": None,
                            "verification": "failed",
                            "is_success": False,
                            "error": str(cmd_res),
                        }
                    else:
                        res_dict = cmd_res.to_dict() if hasattr(cmd_res, "to_dict") else {
                            "command_id": str(seq),
                            "node_id": nid,
                            "channel": cid,
                            "requested_state": "ON" if action in ("turn_on", "open", "on") else "OFF",
                            "confirmed_state": "ON" if (cmd_res[0] in (VerifyResult.SUCCESS, VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE)) else None,
                            "verification": cmd_res[0].value if hasattr(cmd_res[0], "value") else str(cmd_res[0]),
                            "is_success": cmd_res[0] in (VerifyResult.SUCCESS, VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE),
                        }
                    device_results.append(res_dict)
                    if res_dict.get("is_success"):
                        affected_count += 1
                    else:
                        failed_count += 1
            r_vn = get_room_name(location)
            act_vn = "bật" if action == "turn_on" else "tắt"
            if not affected_count and not failed_count:
                reply = "Chưa có thiết bị nào trong phòng." if r_vn else "Chưa có thiết bị kết nối."
            elif not affected_count:
                reply = "Chưa có thiết bị nào xác nhận lệnh."
            elif failed_count:
                reply = f"Có {affected_count} thiết bị xác nhận, {failed_count} thiết bị chưa xác nhận."
            else:
                if r_vn:
                    reply = f"Đã {act_vn} thiết bị ở {r_vn}."
                else:
                    reply = f"Đã {act_vn} tất cả thiết bị."

            result["device_results"] = device_results
            result["success"] = (affected_count > 0 and failed_count == 0)
            result["verify"] = "success" if (affected_count and not failed_count) else "partial" if affected_count else "timeout"
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

        lookup = self.registry.find_node_by_device(device, location)
        if not lookup:
            if hasattr(self, "sound") and self.sound:
                asyncio.create_task(self.sound.play_sound(SoundManager.SOUND_WRONG, target_node=client_node_id))

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

        seq = self.registry.next_seq(node_id)
        cmd_res = await self.verifier.verify_command(
            node_id, channel, action, seq=seq
        )
        verify_result, p_before, p_after, delta = cmd_res
        result["verify"] = verify_result.value
        result["device_results"] = [
            cmd_res.to_dict() if hasattr(cmd_res, "to_dict") else {
                "command_id": str(seq),
                "requested_state": "ON" if action in ("turn_on", "open", "on") else "OFF",
                "confirmed_state": "ON" if verify_result in (VerifyResult.SUCCESS, VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE) else None,
                "verification": verify_result.value,
                "is_success": verify_result in (VerifyResult.SUCCESS, VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE),
                "error": None,
                "power_before": p_before,
                "power_after": p_after,
                "delta": delta,
                "channel": channel,
                "node_id": node_id,
            }
        ]

        action_str = "bật" if action in ("turn_on", "open", "on") else "tắt"
        dev_str = get_device_name(device or channel)
        room_str = get_room_name(location)
        target_desc = f"{dev_str} {room_str}".strip() if room_str else dev_str

        if verify_result == VerifyResult.CONFIRMED_LOAD:
            voice_reply = f"{target_desc} đã {action_str}."
        elif verify_result in (VerifyResult.ACK_ONLY, VerifyResult.SUCCESS):
            voice_reply = f"Đã đặt {target_desc} sang {action_str}."
        elif verify_result == VerifyResult.ALREADY_IN_STATE:
            voice_reply = f"{target_desc} đang ở trạng thái {action_str}."
        elif verify_result == VerifyResult.TIMEOUT:
            voice_reply = "Chưa xác nhận được trạng thái thiết bị."
        elif verify_result == VerifyResult.FAILED:
            voice_reply = "Thiết bị chưa thực hiện được lệnh."
        else:
            voice_reply = self.verifier.generate_failure_message(action, device or channel, location or "", verify_result)

        voice_reply = clean_voice_text(voice_reply)
        result["voice_reply"] = voice_reply
        result["success"] = (
            cmd_res.is_success if hasattr(cmd_res, "is_success") else
            verify_result in (
                VerifyResult.SUCCESS, VerifyResult.ACK_ONLY,
                VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE
            )
        )

        if hasattr(self, "tts") and self.tts:
            try:
                try:
                    pcm = await self.tts.synthesize_pcm(voice_reply, sample_rate=config.AUDIO_SAMPLE_RATE)
                except TypeError:
                    pcm = await self.tts.synthesize_pcm(voice_reply)
                if pcm:
                    result["tts_audio"] = pcm
                    result["tts_format"] = "pcm"
                else:
                    result["tts_audio"] = await self.tts.synthesize(voice_reply)
                    result["tts_format"] = "mp3"
            except Exception as e:
                logger.error(f"TTS synthesis error: {e}")

        if hasattr(self, "memory") and self.memory:
            self.memory.record_command(
                user_text=user_text, action=action, device=device or channel,
                area=location or self.registry.get_all_nodes().get(node_id, {}).get("room",""),
                node_id=node_id, channel=channel,
                verify_result=verify_result.value, power_before=p_before, power_after=p_after,
            )

        self.broadcast_event("command_result", {
            "voice_reply": voice_reply, "verify": verify_result.value,
            "node_id": node_id, "channel": channel, "fullname": fullname, "action": action,
            "engine": result.get("engine", "local"),
        })
        logger.info(f"Done: {action} {fullname} via [{result.get('engine')}] → {verify_result.value} Δ{delta:+.1f}W")
        return result

    async def execute_scene(self, scene_name: str) -> dict:
        """Thực thi Scene và thu thập kết quả từng thiết bị."""
        all_online = self.registry.get_online_nodes()
        affected_count = 0
        failed_count = 0
        device_results = []

        targets = []
        for nid, node in all_online.items():
            channels = node.get("channels", {})
            for cid, ch_info in channels.items():
                dev_type = str(ch_info.get("device_type", "")).lower()
                if scene_name in ("sleep", "night", "leave_home", "away"):
                    target_action = "turn_off"
                elif scene_name in ("morning",):
                    target_action = "turn_on" if dev_type in ("light", "den", "lamp") else None
                else:
                    target_action = "turn_off"
                if target_action is None:
                    continue

                seq = self.registry.next_seq(nid)
                targets.append((nid, cid, target_action, seq))

        if targets:
            tasks = [
                self.verifier.verify_command(nid, cid, target_action, seq=seq)
                for nid, cid, target_action, seq in targets
            ]
            gathered_results = await asyncio.gather(*tasks, return_exceptions=True)
            for (nid, cid, target_action, seq), cmd_res in zip(targets, gathered_results):
                if isinstance(cmd_res, Exception):
                    res_dict = {
                        "command_id": str(seq),
                        "node_id": nid,
                        "channel": cid,
                        "verification": "failed",
                        "is_success": False,
                        "error": str(cmd_res),
                    }
                else:
                    res_dict = cmd_res.to_dict() if hasattr(cmd_res, "to_dict") else {
                        "command_id": str(seq), "node_id": nid, "channel": cid,
                        "verification": cmd_res[0].value if hasattr(cmd_res[0], "value") else str(cmd_res[0]),
                        "is_success": cmd_res[0] in (VerifyResult.SUCCESS, VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD, VerifyResult.ALREADY_IN_STATE),
                    }
                device_results.append(res_dict)
                if res_dict.get("is_success"):
                    affected_count += 1
                else:
                    failed_count += 1

        is_success = (affected_count > 0 and failed_count == 0)
        verify_status = "success" if is_success else "partial" if affected_count else "timeout"
        scene_vn_map = {
            "sleep": "đi ngủ", "night": "đi ngủ",
            "leave_home": "rời nhà", "away": "rời nhà",
            "morning": "chào buổi sáng", "movie": "xem phim"
        }
        scene_display = scene_vn_map.get(scene_name, str(scene_name))
        if not affected_count and not failed_count:
            reply = "Chưa có thiết bị nào phù hợp để thực hiện cảnh."
        elif not affected_count:
            reply = "Chưa có thiết bị nào xác nhận lệnh."
        elif failed_count:
            reply = f"Có {affected_count} thiết bị xác nhận, {failed_count} thiết bị chưa xác nhận."
        else:
            reply = f"Đã kích hoạt cảnh {scene_display}."

        result = {
            "scene": scene_name,
            "success": is_success,
            "verify": verify_status,
            "affected_count": affected_count,
            "failed_count": failed_count,
            "device_results": device_results,
            "voice_reply": reply,
        }
        self.broadcast_event("scene_executed", result)
        return result

    def broadcast_event(self, event_name: str, data: dict):
        """Send SSE event to WebUI and subscribers."""
        if hasattr(self, "web_server") and self.web_server:
            if hasattr(self.web_server, "broadcast_event"):
                self.web_server.broadcast_event(event_name, data)
            elif hasattr(self.web_server, "broadcast"):
                self.web_server.broadcast(event_name, data)

    async def _on_subbox_state(self, topic, payload):
        if not isinstance(payload, dict) or payload.get("status") != "ONLINE":
            return
        parts = topic.split("/")
        if len(parts) != 4 or parts[:2] != ["home", "subbox"] or parts[3] != "state":
            return
        node_id = parts[2]
        if not node_id or payload.get("subbox_id") != node_id:
            return
        node = self.registry.get_all_nodes().get(node_id)
        if node is None or node.get("status") == "NEEDS_REPROVISION":
            return
        self.registry.update_heartbeat(node_id)
        if getattr(self, "lifecycle", None):
            self.lifecycle.resume_claims(node_id)
        self.broadcast_event("node_status", {
            "node_id": node_id, "device_id": node_id,
            "online": True, "status": "online",
        })

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
        # Enrollment events arrive through the authenticated SubBox MQTT topic.
        if isinstance(payload, dict) and payload.get("type") in ("SETUP", "CLAIM_APPLIED", "CLAIM_FAILED"):
            import re
            parts = topic.split("/")
            uid = payload.get("hardware_uid", "")
            node_id = payload.get("node_id", "")
            if (len(parts) != 5 or parts[:2] != ["home", "subbox"] or parts[3:] != ["event", "actionbox"]
                    or not isinstance(uid, str) or not re.fullmatch(r"[0-9A-F]{12}", uid)
                    or node_id != "AB" + uid or payload.get("protocol_version") != 3):
                return
            subbox_id = parts[2]
            if payload["type"] == "SETUP":
                remaining = payload.get("setup_remaining_ms")
                session = payload.get("setup_session")
                if (type(remaining) is not int or not 0 < remaining <= 180000
                        or type(session) is not int or not 0 < session <= 0xffffffff
                        or payload.get("channel_count") != 3):
                    return
                candidate = {**payload, "device_uid": node_id, "id": node_id,
                    "board_model": "actionbox_v2", "subbox_id": subbox_id,
                    "hardware": "ActionBox", "state": "FACTORY_NEW", "serial": uid,
                    "mac": ":".join(uid[i:i+2] for i in range(0, 12, 2)), "rl": [0, 0, 0]}
                self.lifecycle.add_candidate(candidate)
                # Physical discovery permits a new claim, never automatic ownership.
                self.registry.data.setdefault("pending", {})[node_id] = {
                    **candidate, "device_id": node_id, "last_seen": datetime.now(timezone.utc).isoformat()
                }
                self.registry.save()
                self.broadcast_event("pending_device", {"device_uid": node_id})
                return
            op = self.lifecycle.get_operation(payload.get("operation_id", ""))
            if (not op or op.device_uid != node_id or op.target_subbox != subbox_id
                    or op.kind.value != "claim" or op.state.value not in ("accepted", "running")
                    or op.is_expired(time.time())):
                return
            if payload["type"] == "CLAIM_FAILED":
                from device_lifecycle import OperationState
                self.lifecycle.ledger.update_operation_state(op.operation_id, OperationState.FAILED,
                    error_code=str(payload.get("error_code", "DEVICE_REJECTED")),
                    error_message="Thiết bị chưa lưu được đăng ký. Mở lại CONFIG và BUT1 rồi thử lại.")
                return
            if (type(payload.get("config_version")) is not int or payload["config_version"] != op.desired_revision
                    or type(payload.get("owner_epoch")) is not int or payload["owner_epoch"] < 1):
                return
            await self.lifecycle.on_device_applied(node_id, payload["owner_epoch"],
                op.operation_id, payload["config_version"], confirmed_subbox=subbox_id)
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("channels"), list):
            return
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            return
        channels = payload["channels"]

        target_node_id = node_id
        if target_node_id not in self.registry.get_all_nodes():
            uid = payload.get("hardware_uid") or (self.mqtt.node_identities.get(node_id) or {}).get("hardware_uid")
            if uid:
                mac_norm = ":".join(uid[i:i+2] for i in range(0, 12, 2)).upper()
                for nid, ninfo in self.registry.get_all_nodes().items():
                    n_mac = (ninfo.get("mac") or ninfo.get("address", {}).get("mac") or "").upper()
                    if n_mac == mac_norm:
                        target_node_id = nid
                        if node_id in self.mqtt.node_identities:
                            self.mqtt.node_identities[target_node_id] = {**self.mqtt.node_identities[node_id], "hw_node_id": node_id}
                        if node_id in self.mqtt.node_routes:
                            self.mqtt.node_routes[target_node_id] = self.mqtt.node_routes[node_id]
                        break

        if target_node_id not in self.registry.get_all_nodes():

            if node_id not in self.registry.data.get("pending", {}):
                identity = self.mqtt.node_identities.get(node_id)
                if not identity or node_id in self.mqtt.conflicting_nodes:
                    return
                uid = identity["hardware_uid"]
                self.registry.on_hello({"id": node_id, "hardware": "ActionBox", "state": "FACTORY_NEW",
                    "serial": uid, "mac": ":".join(uid[i:i+2] for i in range(0, 12, 2)),
                    "rl": [0] * max(len(channels), 3)})
            return
        states = {c.get("channel"): c.get("state") == "ON" for c in channels if isinstance(c, dict)}
        sorted_channels = sorted([k for k in states.keys() if isinstance(k, int)])
        if sorted_channels:
            self.registry.update_relay_state(target_node_id, [int(states[k]) for k in sorted_channels])

        node = self.registry.get_all_nodes().get(target_node_id)
        if node:
            for c in channels:
                if isinstance(c, dict):
                    ch_num = c.get("channel")
                    pw = c.get("power_w", c.get("power", c.get("p")))
                    if ch_num is not None and pw is not None:
                        ch_key = f"ch{ch_num}"
                        if "channels" in node and ch_key in node["channels"]:
                            try:
                                node["channels"][ch_key]["power"] = float(pw)
                            except (ValueError, TypeError):
                                pass

            existing_channels = node.setdefault("channels", {})
            if len(existing_channels) < len(sorted_channels):
                updated = False
                for ch_num in sorted_channels:
                    ch_key = f"ch{ch_num}"
                    if ch_key not in existing_channels:
                        dt = "switch"
                        existing_channels[ch_key] = {
                            "device_type": dt,
                            "fullname": f"{node_id}-{dt}",
                            "name": f"Kênh {ch_num}",
                            "aliases": [dt],
                            "gpio": 5 if ch_num == 3 else (4 if ch_num == 1 else (5 if ch_num == 2 else 5)),
                            "rated_watts": 100 if ch_num == 3 else (40 if ch_num == 1 else 55),
                            "description": dt
                        }
                        if "configuration" in node and "relays" in node["configuration"]:
                            node["configuration"]["relays"][ch_key] = {
                                "device_type": dt,
                                "fullname": f"{node_id}-{dt}",
                                "name": f"Kênh {ch_num}",
                                "gpio": 5 if ch_num == 3 else (4 if ch_num == 1 else 5)
                            }
                        updated = True
                caps = node.get("capabilities", [])
                if len(sorted_channels) >= 3:
                    if "relay_2ch" in caps:
                        node["capabilities"] = [c if c != "relay_2ch" else "relay_3ch" for c in caps]
                        updated = True
                    elif "relay_3ch" not in caps:
                        caps.append("relay_3ch")
                        node["capabilities"] = caps
                        updated = True
                if updated:
                    self.registry.save(changed_node=target_node_id)
                    if hasattr(self, "discovery") and self.discovery:
                        await self.discovery.publish_ha_discovery_for_node(target_node_id)
        self.registry.update_heartbeat(target_node_id)

    async def _on_hello(self, topic: str, payload: dict):
        """Node mới hoặc đã provision gửi hello qua MQTT (compact)."""
        if not isinstance(payload, dict):
            return
        hello = payload if payload.get("t") == "hello" else {"t": "hello", **payload}
        res = self.registry.on_hello(hello, ws_available=False)
        self.broadcast_event("node_hello", hello)

        if res.get("action") == "pending":
            self.broadcast_event("pending_node", {"mac": res["mac"], "hello": hello})
            logger.info(f"📥 Pending node (MQTT): {res['mac']}")
        elif res.get("action") == "cfg_mismatch":
            cfg = self.registry.get_provision_payload(res["node_id"])
            if cfg:
                await self.mqtt.send_cfg(res["node_id"], cfg)
        elif res.get("action") == "known":
            self.broadcast_event("node_status", {"node_id": res["node_id"], "online": True})
            if hasattr(self, "lifecycle") and self.lifecycle:
                self.lifecycle.on_device_reconnected(res["node_id"])

    async def _on_node_register(self, topic: str, payload: dict):
        """Legacy register (giữ tương thích)."""
        if not isinstance(payload, dict):
            return

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

            norm = dict(payload)
            if "p" in norm and "power" not in norm: norm["power"] = norm["p"]
            if "v" in norm and "voltage" not in norm: norm["voltage"] = norm["v"]
            if "i" in norm and "current" not in norm: norm["current"] = norm["i"]
            self.broadcast_event("node_telemetry", {"node_id": node_id, **norm})

            # Update per-channel power in registry if present in telemetry
            node = self.registry.data.get("nodes", {}).get(node_id)
            if node:
                node_channels = node.setdefault("channels", {})
                ch_list = payload.get("channels")
                if isinstance(ch_list, list):
                    for idx, ch_item in enumerate(ch_list):
                        if isinstance(ch_item, dict):
                            pw = ch_item.get("power_w", ch_item.get("power", ch_item.get("p")))
                            if pw is not None:
                                try:
                                    ch_key = f"ch{idx+1}"
                                    node_channels.setdefault(ch_key, {})["power"] = float(pw)
                                except (ValueError, TypeError):
                                    pass
                elif isinstance(ch_list, dict):
                    for ch_k, ch_item in ch_list.items():
                        if isinstance(ch_item, dict):
                            pw = ch_item.get("power_w", ch_item.get("power", ch_item.get("p")))
                            if pw is not None:
                                try:
                                    node_channels.setdefault(ch_k, {})["power"] = float(pw)
                                except (ValueError, TypeError):
                                    pass
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

            if payload.get("t") == "ack":
                self.mqtt.record_compact_ack(node_id, payload)
                rl = payload.get("rl", [])
                if rl and hasattr(self.registry, "update_relay_state"):
                    self.registry.update_relay_state(node_id, rl)
                self.broadcast_event("node_status", {
                    "node_id": node_id, "rl_state": rl, "seq": payload.get("seq"),
                    "ch1": rl[0] if len(rl)>0 else None, "ch2": rl[1] if len(rl)>1 else None,
                    "ch3": rl[2] if len(rl)>2 else None
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

    async def provision_pending(self, mac_or_id: str = None, room: str = "livingroom",
                                rl1: str = "light", rl2: str = "fan", rl3: Optional[str] = None,
                                node_short: str = None, name: str = None,
                                location: str = None, description: str = None,
                                mac: str = None) -> dict:
        target = mac_or_id or mac
        node = self.registry.provision_node(
            target, room, rl1, rl2, rl3=rl3,
            node_short=node_short, name=name, location=location, description=description
        )
        if not node:
            return {"success": False, "error": "Target node not in pending or invalid"}
        node_id = node.get("device_id") or node.get("node_id")
        mac = node.get("mac", "")
        cfg = self.registry.get_provision_payload(node_id)

        ok = True
        if mac:
            if not await self.mqtt.send_cfg(mac, cfg):
                ok = False
        if not await self.mqtt.send_cfg(node_id, cfg):
            ok = False

        if not ok:
            self.registry.data["nodes"].pop(node_id, None)
            self.registry.save()
            return {"success": False, "error": "Failed to transmit configuration to device"}

        await self.discovery.publish_ha_discovery_for_node(node_id)
        self.broadcast_event("node_provisioned", {"node_id": node_id, "device_id": node_id, "cfg": cfg})
        if mac:
            self.broadcast_event("pending_remove", {"mac": mac.upper(), "device_id": node_id})
        return {"success": True, "device_id": node_id, "node_id": node_id, "cfg": cfg}

    async def _on_unclaimed_device(self, topic: str, payload: Any):
        """Thiết bị xuất xưởng / unprovisioned phát hiện qua home/discovery/unclaimed"""
        if not isinstance(payload, dict):
            try:
                payload = json.loads(payload)
            except Exception:
                return
        logger.info(f"🆕 [Discovery] Unclaimed Device: {payload.get('device_id')} ({payload.get('serial')})")
        if hasattr(self, "lifecycle") and self.lifecycle:
            self.lifecycle.add_candidate(payload)
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
            if hasattr(self, "lifecycle") and self.lifecycle:
                self.lifecycle.on_device_reconnected(device_id)

    async def _on_device_operation_ack(self, topic: str, payload: Any):
        """Nhận operation feedback / ACK từ thiết bị: home/devices/{device_id}/operation/ack"""
        parts = topic.split("/")
        device_id = parts[2] if len(parts) >= 3 else None
        if not isinstance(payload, dict):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        dev_id = payload.get("device_uid") or payload.get("node_id") or device_id
        op_id = payload.get("operation_id") or payload.get("op_id")
        status = payload.get("status", "succeeded")
        err_code = payload.get("error_code")
        err_msg = payload.get("error_message")
        if dev_id and hasattr(self, "lifecycle") and self.lifecycle:
            self.lifecycle.on_operation_ack(
                device_uid=dev_id,
                operation_id=op_id,
                status=status,
                error_code=err_code,
                error_message=err_msg,
            )

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

        op_id = payload.get("operation_id")
        try:
            epoch = int(payload.get("owner_epoch", 1)) if payload.get("owner_epoch") is not None else 1
        except (ValueError, TypeError):
            epoch = 1
        try:
            rev = int(payload.get("version") or payload.get("config_revision", 1))
        except (ValueError, TypeError):
            rev = 1
        if op_id or payload.get("status") in ("applied", "APPLIED", "READY") or payload.get("state") in ("applied", "APPLIED"):
            await self.on_device_applied(device_id, owner_epoch=epoch, operation_id=op_id, config_revision=rev)

    async def on_device_applied(self, device_uid: str, owner_epoch: int = 1, operation_id: str | None = None, config_revision: int = 1):
        if hasattr(self, "lifecycle") and self.lifecycle:
            await self.lifecycle.on_device_applied(
                device_uid=device_uid,
                owner_epoch=owner_epoch,
                operation_id=operation_id,
                config_revision=config_revision,
            )

    async def _on_device_applied_msg(self, topic: str, payload: Any):
        parts = topic.split("/")
        if len(parts) >= 3:
            device_id = parts[2]
            if not isinstance(payload, dict):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            op_id = payload.get("operation_id")
            try:
                epoch = int(payload.get("owner_epoch", 1)) if payload.get("owner_epoch") is not None else 1
            except (ValueError, TypeError):
                epoch = 1
            try:
                rev = int(payload.get("config_revision") or payload.get("version", 1))
            except (ValueError, TypeError):
                rev = 1
            await self.on_device_applied(device_id, owner_epoch=epoch, operation_id=op_id, config_revision=rev)

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
            ch_idx = {"ch1": 0, "ch2": 1, "ch3": 2, "1": 0, "2": 1, "3": 2, 1: 0, 2: 1, 3: 2}.get(channel, 0)
            caps = n.get("capabilities", [])
            min_len = 3 if ("relay_3ch" in caps or len(n.get("channels", {})) >= 3) else 2
            while len(cur_rl) < max(ch_idx + 1, min_len):
                cur_rl.append(0)
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

        await self.mqtt.send_desired_config(device_id, desired_payload)

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

    def get_voice_vocabulary_diagnostics(self, user: Optional[dict] = None) -> dict:
        """Thu thập thông tin chẩn đoán từ vựng và nhận diện giọng nói có phân quyền."""
        asr_diag = self.asr.dump_active_vocabulary(self.registry) if hasattr(self, "asr") and self.asr else {"initialized": False, "hotwords_count": 0, "hotwords": []}
        stored = []

        if hasattr(self.registry, "get_user_accessible_nodes"):
            accessible_nodes = self.registry.get_user_accessible_nodes(user)
        elif user and user.get("role") != "admin" and hasattr(self, "auth") and self.auth:
            accessible_nodes = self.auth.filter_nodes(user, self.registry.get_all_nodes())
        else:
            accessible_nodes = self.registry.get_all_nodes()

        for nid, n in accessible_nodes.items():
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

        if user and user.get("role") != "admin" and isinstance(asr_diag, dict):
            allowed_alias_phrases = set()
            for s in stored:
                for a in s.get("aliases", []):
                    allowed_alias_phrases.add(a.lower())
                if s.get("name"):
                    allowed_alias_phrases.add(s["name"].lower())
            filtered_hotwords = [
                hw for hw in asr_diag.get("hotwords", [])
                if any(phrase in hw.lower() for phrase in allowed_alias_phrases)
            ]
            asr_diag = {
                **asr_diag,
                "hotwords": filtered_hotwords,
                "hotwords_count": len(filtered_hotwords),
            }

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
        if hasattr(self, "lifecycle") and self.lifecycle:
            try:
                from device_lifecycle import OperationKind
                if self.registry and "nodes" in getattr(self.registry, "data", {}) and device_id in self.registry.data["nodes"]:
                    self.lifecycle.start_operation(
                        user={"id": 1, "username": "admin", "role": "admin"},
                        device_uid=device_id,
                        kind=OperationKind.REMOVE_FROM_HOME,
                        confirmation=True,
                    )
                    if hasattr(self, "audio_server") and hasattr(self.audio_server, "_ws_nodes"):
                        ws = self.audio_server._ws_nodes.pop(device_id, None)
                        if ws and hasattr(self.audio_server, "_active_speakers"):
                            self.audio_server._active_speakers.discard(ws)
                    return True
            except Exception as e:
                logger.warning(f"Lifecycle remove_from_home failed for {device_id}: {e}")

        if hasattr(self, "auth") and self.auth:
            self.auth.revoke_device_grants(device_id)
        ok = self.registry.delete_node(device_id)
        if hasattr(self, "audio_server") and hasattr(self.audio_server, "_ws_nodes"):
            ws = self.audio_server._ws_nodes.pop(device_id, None)
            if ws and hasattr(self.audio_server, "_active_speakers"):
                self.audio_server._active_speakers.discard(ws)
        if hasattr(self, "discovery") and hasattr(self.discovery, "remove_ha_discovery_for_node"):
            try:
                res = self.discovery.remove_ha_discovery_for_node(device_id)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass
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
    if hasattr(gateway, "mqtt") and gateway.mqtt:
        await gateway.mqtt.disconnect()
    for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
        t.cancel()

if __name__ == "__main__":
    asyncio.run(main())
