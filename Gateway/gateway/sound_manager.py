"""
Sound Manager — AETHERIA OS Acoustic System
============================================
Manages system acoustic soundscapes and audio effects:
  - morning_sound: Báo thức / Chào buổi sáng (Morning alarm & awakening melody)
  - bootup_sound: Âm thanh khởi động hệ thống ổn định (System boot & ready chime)
  - listen_success: Nhận diện giọng nói thành công (Speech recognition acknowledge)
  - new_noti: Thông báo mới / Cảnh báo an toàn (Proactive notification alert)
  - wrong_sound: Lệnh sai / Không nhận dạng được (Unrecognized command / error blip)

Pre-caches 16kHz 16-bit mono PCM for zero-latency direct streaming to ESP32 I2S speaker,
and provides MP3 streams for Web UI & Mobile App preview.
"""

import os
import io
import time
import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger("sound_manager")


class SoundManager:
    """Manages acoustic sound effects for the entire Smart Home Gateway ecosystem."""

    SOUND_BOOTUP = "bootup_sound"
    SOUND_LISTEN_SUCCESS = "listen_success"
    SOUND_MORNING = "morning_sound"
    SOUND_NOTIFICATION = "new_noti"
    SOUND_WRONG = "wrong_sound"

    DESCRIPTIONS = {
        "bootup_sound": {
            "title": "Khởi Động Hệ Thống",
            "usage": "Phát khi Gateway và ESP32 khởi động thành công và hệ thống đã ổn định.",
            "duration": 1.92,
            "filename": "bootup_sound.mp3"
        },
        "listen_success": {
            "title": "Nhận Diện Thành Công",
            "usage": "Phát ngay sau khi ASR nhận diện chính xác khẩu lệnh của người dùng.",
            "duration": 1.15,
            "filename": "listen_success.mp3"
        },
        "morning_sound": {
            "title": "Báo Thức & Buổi Sáng",
            "usage": "Phát vào buổi sáng sớm (06:30 - 08:30) hoặc làm chuông báo thức khi người dùng yêu cầu.",
            "duration": 34.87,
            "filename": "morning_sound.mp3"
        },
        "new_noti": {
            "title": "Thông Báo / Cảnh Báo",
            "usage": "Phát trước khi Lumi đọc cảnh báo an toàn (bình nóng lạnh bật lâu, thiết bị pending mới, TinyML).",
            "duration": 2.40,
            "filename": "new_noti.mp3"
        },
        "wrong_sound": {
            "title": "Lệnh Lỗi / Chưa Hiểu",
            "usage": "Phát khi câu lệnh không rõ, không tìm thấy thiết bị hoặc nhận diện thất bại.",
            "duration": 1.27,
            "filename": "wrong_sound.mp3"
        }
    }

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.sound_dir = self._find_sound_dir()
        # In-memory caches: sound_name -> bytes
        self._pcm_cache: Dict[str, bytes] = {}
        self._mp3_cache: Dict[str, bytes] = {}
        self._load_all_sounds()

    def _find_sound_dir(self) -> str:
        """Find the folder containing sound files."""
        candidates = [
            "/home/pi4/smarthome/sound",
            "/home/pi4/Home-Assistant-IoT-/sound",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sound"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sound"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "sound"),
            r"d:\Home-Assistant-IoT-\sound"
        ]
        for c in candidates:
            if os.path.isdir(c) and os.path.exists(os.path.join(c, "morning_sound.mp3")):
                logger.info(f"🎵 Sound directory located at: {c}")
                return os.path.abspath(c)
        # Default fallback
        logger.warning("Sound directory not explicitly found, defaulting to relative ../../sound")
        return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sound"))

    def _load_all_sounds(self):
        """Pre-load PCM and MP3 bytes into memory for instant playback."""
        if not os.path.isdir(self.sound_dir):
            return

        for key in self.DESCRIPTIONS.keys():
            # 1. Load MP3
            mp3_path = os.path.join(self.sound_dir, f"{key}.mp3")
            if os.path.exists(mp3_path):
                try:
                    with open(mp3_path, "rb") as f:
                        self._mp3_cache[key] = f.read()
                except Exception as e:
                    logger.warning(f"Failed to read {mp3_path}: {e}")

            # 2. Load pre-converted 16kHz PCM
            pcm_path = os.path.join(self.sound_dir, f"{key}.pcm")
            if os.path.exists(pcm_path):
                try:
                    with open(pcm_path, "rb") as f:
                        self._pcm_cache[key] = f.read()
                    logger.info(f"  ⚡ Preloaded PCM '{key}': {len(self._pcm_cache[key])} bytes")
                except Exception as e:
                    logger.warning(f"Failed to read {pcm_path}: {e}")

    def get_mp3_data(self, sound_name: str) -> Optional[bytes]:
        """Get MP3 bytes for HTTP streaming or mobile app preview."""
        name = sound_name.replace(".mp3", "").strip().lower()
        if name in self._mp3_cache:
            return self._mp3_cache[name]
        mp3_path = os.path.join(self.sound_dir, f"{name}.mp3")
        if os.path.exists(mp3_path):
            try:
                with open(mp3_path, "rb") as f:
                    data = f.read()
                    self._mp3_cache[name] = data
                    return data
            except Exception:
                pass
        return None

    def get_pcm_data(self, sound_name: str) -> Optional[bytes]:
        """Get 16kHz 16-bit mono PCM bytes for direct I2S playback on ESP32."""
        name = sound_name.replace(".mp3", "").replace(".pcm", "").strip().lower()
        if name in self._pcm_cache:
            return self._pcm_cache[name]

        pcm_path = os.path.join(self.sound_dir, f"{name}.pcm")
        if os.path.exists(pcm_path):
            try:
                with open(pcm_path, "rb") as f:
                    data = f.read()
                    self._pcm_cache[name] = data
                    return data
            except Exception:
                pass
        return None

    def list_sounds(self) -> Dict[str, Any]:
        """Return catalog of available sounds with metadata."""
        items = []
        for k, meta in self.DESCRIPTIONS.items():
            has_pcm = k in self._pcm_cache or os.path.exists(os.path.join(self.sound_dir, f"{k}.pcm"))
            has_mp3 = k in self._mp3_cache or os.path.exists(os.path.join(self.sound_dir, f"{k}.mp3"))
            items.append({
                "id": k,
                "title": meta["title"],
                "usage": meta["usage"],
                "duration_seconds": meta["duration"],
                "filename": meta["filename"],
                "available": has_mp3 or has_pcm,
            })
        return {"status": "success", "sounds": items}

    async def play_sound(self, sound_name: str, target_node: str = "esp32s3_master", websocket=None) -> bool:
        """
        Play a sound effect through the ESP32 physical speaker.
        If websocket is provided, sends to it. Otherwise sends to target_node or all connected speakers.
        """
        pcm = self.get_pcm_data(sound_name)
        if not pcm:
            logger.warning(f"PCM audio not found for sound '{sound_name}'")
            return False

        if not self.gateway or not hasattr(self.gateway, "audio_server"):
            logger.warning("Audio server not available for playing sound")
            return False

        audio_server = self.gateway.audio_server
        target_ws = websocket

        if not target_ws:
            if target_node and target_node in audio_server._ws_nodes:
                target_ws = audio_server._ws_nodes[target_node]
            elif "esp32s3_master" in audio_server._ws_nodes:
                target_ws = audio_server._ws_nodes["esp32s3_master"]
            elif audio_server._ws_nodes:
                target_ws = next(iter(audio_server._ws_nodes.values()))

        if not target_ws:
            logger.debug(f"No active speaker WebSocket found to play sound '{sound_name}'")
            return False

        try:
            logger.info(f"🔊 Playing sound '{sound_name}' ({len(pcm)} bytes PCM) to speaker...")
            await audio_server._send_pcm_stream(target_ws, pcm, follow_up=False)
            return True
        except Exception as e:
            logger.error(f"Error streaming sound '{sound_name}': {e}")
            return False

    async def play_sound_and_speak(
        self,
        sound_name: str,
        speech_text: str,
        target_node: str = "esp32s3_master",
        websocket=None,
        follow_up: bool = False
    ) -> bool:
        """
        Play a sound effect first (e.g. new_noti, morning_sound, wrong_sound),
        then immediately speak Lumi's voice reply!
        """
        # 1. Play sound
        await self.play_sound(sound_name, target_node=target_node, websocket=websocket)

        # Brief pause between sound effect and speech
        await asyncio.sleep(0.2)

        # 2. Synthesize & speak voice
        if self.gateway and hasattr(self.gateway, "audio_server"):
            audio_server = self.gateway.audio_server
            if websocket:
                await audio_server._send_voice_reply(websocket, speech_text, follow_up=follow_up)
                return True
            else:
                return await audio_server.speak_proactive(speech_text, node_id=target_node)
        return False
