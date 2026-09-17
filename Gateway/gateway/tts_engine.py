"""
TTS Engine — EdgeTTS Vietnamese text-to-speech.
Converts text responses to audio for playback on ESP32 speaker.
"""

import io
import os
import re
import hashlib
import logging
import asyncio
from typing import Optional

import edge_tts

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False

import config

logger = logging.getLogger("tts")


class TTSEngine:
    """Vietnamese text-to-speech using Microsoft EdgeTTS with sweet prosody & pitch tuning."""
    
    def __init__(self):
        self.voice = getattr(config, "TTS_VOICE", "vi-VN-HoaiMyNeural")
        self.fallback_voice = getattr(config, "TTS_FALLBACK_VOICE", "vi-VN-HoaiMyNeural")
        self.rate = getattr(config, "TTS_RATE", "-4%")
        self.pitch = getattr(config, "TTS_PITCH", "+2Hz")
        # Persistent audio cache setup
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "tts")
        if os.path.exists("/home/pi4/smarthome"):
            self.cache_dir = "/home/pi4/smarthome/tts_cache"
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        self._mem_cache = {}

    def beautify_prosody(self, text: str) -> str:
        """
        Nắn chỉnh ngữ điệu tiếng Việt:
        - Xưng 'em' - gọi 'anh' tự nhiên, ngọt ngào.
        - Thêm khoảng ngắt nhịp thở nhẹ nhàng sau từ mở đầu (Dạ, Vâng, Anh ơi).
        - Uốn lượn âm cuối (luyến láy) với dấu lượn sóng ~ hoặc trợ từ tình thái.
        """
        if not text:
            return ""
        t = text.strip()

        # 1. Chuẩn hóa xưng hô: Luôn gọi "anh", xưng "em"
        t = re.sub(r"\bBạn muốn\b", "Dạ anh muốn", t)
        t = re.sub(r"\bbạn muốn\b", "anh muốn", t)
        t = re.sub(r"\bBạn có\b", "Dạ anh có", t)
        t = re.sub(r"\bbạn có\b", "anh có", t)
        t = re.sub(r"\bBạn nói\b", "Anh nói", t)
        t = re.sub(r"\bbạn nói\b", "anh nói", t)
        t = re.sub(r"\bcho bạn\b", "cho anh", t)
        t = re.sub(r"\bcủa bạn\b", "của anh", t)
        t = re.sub(r"\bvới bạn\b", "với anh", t)
        t = re.sub(r"\bchào bạn\b", "chào anh", t)
        t = re.sub(r"\bChào bạn\b", "Chào anh", t)
        t = re.sub(r"\bbạn nhé\b", "anh nhé", t)
        t = re.sub(r"\bbạn nha\b", "anh nha", t)
        # Bắt triệt để mọi từ "bạn" / "người dùng" còn lại
        t = re.sub(r"\bBạn\b", "Anh", t)
        t = re.sub(r"\bbạn\b", "anh", t)
        t = re.sub(r"\bngười dùng\b", "anh", t)

        # 2. Ngắt nhịp thở tự nhiên (~180ms micro-pause) sau từ mở đầu
        if t.startswith("Dạ ") and not t.startswith("Dạ, "):
            t = "Dạ, " + t[3:]
        elif t.startswith("Vâng ") and not t.startswith("Vâng, "):
            t = "Vâng, " + t[5:]
        elif t.startswith("Anh ơi ") and not t.startswith("Anh ơi, "):
            t = "Anh ơi, " + t[7:]

        # 3. Luyến láy đuôi câu nhẹ nhàng
        if t.endswith("nè.") or t.endswith("nè"):
            t = t.rstrip(".").rstrip() + "~"
        elif t.endswith("nha.") or t.endswith("nha"):
            t = t.rstrip(".").rstrip()
            if not t.endswith("anh"):
                t += " anh~"
            else:
                t += "~"
        elif t.endswith("nhé.") or t.endswith("nhé"):
            t = t.rstrip(".").rstrip()
            if not t.endswith("anh"):
                t += " nha anh~"
            else:
                t += "~"
        elif t.endswith("ạ."):
            t = t.rstrip(".") + "~"

        return t

    def _get_hash(self, text: str, suffix: str = "") -> str:
        rate = getattr(config, "TTS_RATE", self.rate)
        pitch = getattr(config, "TTS_PITCH", self.pitch)
        norm = " ".join(text.strip().lower().split())
        return hashlib.md5(f"{norm}_{self.voice}_{rate}_{pitch}_{suffix}".encode("utf-8")).hexdigest()

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert Vietnamese text to MP3 audio bytes with cache.
        """
        if not text or not text.strip():
            return None

        text = self.beautify_prosody(text)
        rate = getattr(config, "TTS_RATE", self.rate)
        pitch = getattr(config, "TTS_PITCH", self.pitch)

        h = self._get_hash(text, "mp3")
        if h in self._mem_cache:
            return self._mem_cache[h]

        disk_path = os.path.join(self.cache_dir, f"{h}.mp3")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "rb") as f:
                    data = f.read()
                if data:
                    self._mem_cache[h] = data
                    return data
            except Exception:
                pass
        
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate=rate, pitch=pitch)
            audio_data = b""
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if audio_data:
                self._mem_cache[h] = audio_data
                try:
                    with open(disk_path, "wb") as f:
                        f.write(audio_data)
                except Exception:
                    pass
                logger.info(f"TTS synthesized & cached: \"{text[:50]}...\" [rate={rate}, pitch={pitch}] → {len(audio_data)} bytes")
                return audio_data
            else:
                logger.warning("TTS produced empty audio")
                return None
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
            # Try fallback voice
            try:
                communicate = edge_tts.Communicate(text, self.fallback_voice, rate=rate, pitch=pitch)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                if audio_data:
                    self._mem_cache[h] = audio_data
                    try:
                        with open(disk_path, "wb") as f:
                            f.write(audio_data)
                    except Exception:
                        pass
                return audio_data if audio_data else None
            except Exception as e2:
                logger.error(f"TTS fallback also failed: {e2}")
                return None
            except Exception as e2:
                logger.error(f"TTS fallback also failed: {e2}")
                return None
    
    async def speak_alert(self, message: str) -> Optional[bytes]:
        """Synthesize an alert/notification message."""
        return await self.synthesize(message)

    async def synthesize_pcm(self, text: str, sample_rate: int = 16000) -> Optional[bytes]:
        """
        Convert Vietnamese text to raw PCM audio bytes (16kHz, 16-bit, mono) with cache.
        Suitable for direct playback on ESP32 I2S speaker.
        """
        if not text or not text.strip():
            return None

        h = self._get_hash(text, f"pcm_{sample_rate}")
        if h in self._mem_cache:
            logger.info(f"⚡ TTS PCM hit memory cache: '{text[:40]}' ({len(self._mem_cache[h])} bytes)")
            return self._mem_cache[h]

        disk_path = os.path.join(self.cache_dir, f"{h}.pcm")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "rb") as f:
                    data = f.read()
                if data:
                    self._mem_cache[h] = data
                    logger.info(f"⚡ TTS PCM hit disk cache: '{text[:40]}' ({len(data)} bytes)")
                    return data
            except Exception:
                pass

        mp3_data = await self.synthesize(text)
        if not mp3_data:
            return None

        pcm_data = None
        # Method 1: pydub
        if HAS_PYDUB:
            try:
                audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
                audio = audio.set_frame_rate(sample_rate)
                audio = audio.set_channels(1)    # Mono
                audio = audio.set_sample_width(2) # 16-bit
                pcm_data = audio.raw_data
            except Exception as e:
                logger.warning(f"pydub conversion failed: {e}, trying ffmpeg fallback")

        # Method 2: ffmpeg subprocess
        if not pcm_data:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", "pipe:0", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "pipe:1",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                pcm_data, _ = await proc.communicate(input=mp3_data)
                if proc.returncode != 0 or not pcm_data:
                    pcm_data = None
            except Exception as e:
                logger.error(f"ffmpeg conversion failed: {e}")

        if pcm_data:
            self._mem_cache[h] = pcm_data
            try:
                with open(disk_path, "wb") as f:
                    f.write(pcm_data)
                logger.info(f"💾 Saved TTS PCM to cache: {disk_path}")
            except Exception:
                pass
            return pcm_data

        logger.error("Neither pydub nor ffmpeg is available to convert audio to PCM.")
        return None
