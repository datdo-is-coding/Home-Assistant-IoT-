"""
TTS Engine — EdgeTTS Vietnamese text-to-speech.
Converts text responses to audio for playback on ESP32 speaker.
"""

import io
import os
import re
import time
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


class VieNeuEngine:
    """
    On-device Vietnamese Text-to-Speech using VieNeu-TTS (Phạm Nguyễn Ngọc Bảo).
    CPU-optimized flow matching architecture running via ONNX Runtime without torch.
    """

    def __init__(self):
        self._vieneu = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            mode = getattr(config, "VIENEU_MODE", "v3nano")
            voice = getattr(config, "VIENEU_VOICE", "Ái Hân")
            logger.info(f"⏳ Loading on-device VieNeu-TTS (mode={mode}, voice={voice})...")
            try:
                def _load():
                    from vieneu import Vieneu
                    return Vieneu(mode=mode)
                self._vieneu = await asyncio.to_thread(_load)
                self._initialized = True
                logger.info(f"✅ VieNeu-TTS ({mode}) loaded into RAM successfully!")
            except Exception as e:
                logger.error(f"Failed to load VieNeu-TTS: {e}")
                self._initialized = False

    async def synthesize(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        if not self._initialized:
            await self.initialize()
        if not self._vieneu:
            return None

        voice = voice or getattr(config, "VIENEU_VOICE", "Ái Hân")
        try:
            def _infer():
                try:
                    # steps=8 and sway=-1 gives ~2x speedup on CPU
                    audio_arr = self._vieneu.infer(text, voice=voice, steps=8, sway=-1)
                except TypeError:
                    audio_arr = self._vieneu.infer(text, voice=voice)
                
                import io
                import soundfile as sf
                buf = io.BytesIO()
                sr = getattr(self._vieneu, "sample_rate", 24000)
                sf.write(buf, audio_arr, sr, format='WAV', subtype='PCM_16')
                return buf.getvalue()

            wav_bytes = await asyncio.to_thread(_infer)
            return wav_bytes
        except Exception as e:
            logger.error(f"VieNeu inference error: {e}")
            return None


class TTSEngine:
    """Vietnamese text-to-speech with dual engine support (VieNeu-TTS local + EdgeTTS cloud)."""
    
    def __init__(self):
        self.voice = getattr(config, "TTS_VOICE", "vi-VN-HoaiMyNeural")
        self.fallback_voice = getattr(config, "TTS_FALLBACK_VOICE", "vi-VN-HoaiMyNeural")
        self.rate = getattr(config, "TTS_RATE", "-4%")
        self.pitch = getattr(config, "TTS_PITCH", "+2Hz")
        self.vieneu = VieNeuEngine()
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
        provider = getattr(config, "TTS_PROVIDER", "vieneu")
        rate = getattr(config, "TTS_RATE", self.rate)
        pitch = getattr(config, "TTS_PITCH", self.pitch)
        vieneu_voice = getattr(config, "VIENEU_VOICE", "Ái Hân")
        vieneu_mode = getattr(config, "VIENEU_MODE", "v3nano")
        norm = " ".join(text.strip().lower().split())
        return hashlib.md5(f"{norm}_{provider}_{self.voice}_{rate}_{pitch}_{vieneu_voice}_{vieneu_mode}_{suffix}".encode("utf-8")).hexdigest()

    async def synthesize_edgetts(self, text: str, rate: str = "-4%", pitch: str = "+2Hz") -> Optional[bytes]:
        """EdgeTTS synthesis with fallback voice."""
        try:
            # Ensure sign prefix for edge-tts
            rate_str = str(rate or "-4%").strip()
            if not rate_str.startswith(("+", "-")):
                rate_str = f"+{rate_str}"
            pitch_str = str(pitch or "+2Hz").strip()
            if not pitch_str.startswith(("+", "-")):
                pitch_str = f"+{pitch_str}"

            communicate = edge_tts.Communicate(text, self.voice, rate=rate_str, pitch=pitch_str)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if audio_data:
                logger.info(f"EdgeTTS synthesized: \"{text[:45]}...\" [rate={rate}, pitch={pitch}] → {len(audio_data)} bytes")
                return audio_data
        except Exception as e:
            logger.error(f"EdgeTTS primary error: {e}")
            try:
                communicate = edge_tts.Communicate(text, self.fallback_voice, rate=rate, pitch=pitch)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data if audio_data else None
            except Exception as e2:
                logger.error(f"EdgeTTS fallback failed: {e2}")
        return None

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert Vietnamese text to audio bytes (WAV/MP3) with cache.
        Supports switching between VieNeu-TTS (local) and EdgeTTS (cloud).
        """
        if not text or not text.strip():
            return None

        text = self.beautify_prosody(text)
        provider = getattr(config, "TTS_PROVIDER", "vieneu").lower().strip()
        rate = getattr(config, "TTS_RATE", self.rate)
        pitch = getattr(config, "TTS_PITCH", self.pitch)

        h = self._get_hash(text, "audio")
        if h in self._mem_cache:
            return self._mem_cache[h]

        disk_path = os.path.join(self.cache_dir, f"{h}.audio")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "rb") as f:
                    data = f.read()
                if data:
                    self._mem_cache[h] = data
                    return data
            except Exception:
                pass

        audio_data = None
        # 1. Thử VieNeu-TTS local on-device nếu provider được chọn là vieneu
        if provider == "vieneu":
            try:
                t0 = time.time()
                audio_data = await self.vieneu.synthesize(text)
                if audio_data:
                    dt = time.time() - t0
                    logger.info(f"✨ VieNeu-TTS synthesized local in {dt:.2f}s: \"{text[:45]}...\" ({len(audio_data)} bytes)")
            except Exception as e:
                logger.warning(f"⚠️ VieNeu-TTS failed: {e}")
                audio_data = None

        # 2. Nếu provider là edgetts hoặc vieneu tạm thời lỗi/chưa tải xong: Dùng EdgeTTS mượt mà
        if not audio_data:
            if provider == "vieneu":
                logger.info("⚡ VieNeu-TTS unavailable, falling back seamlessly to EdgeTTS Cloud")
            audio_data = await self.synthesize_edgetts(text, rate=rate, pitch=pitch)

        if audio_data:
            self._mem_cache[h] = audio_data
            try:
                with open(disk_path, "wb") as f:
                    f.write(audio_data)
            except Exception:
                pass
            return audio_data

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

        audio_bytes = await self.synthesize(text)
        if not audio_bytes:
            return None

        pcm_data = None
        # Method 1: If audio_bytes is already a WAV file, we can use soundfile or pydub
        if HAS_PYDUB:
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
                audio = audio.set_frame_rate(sample_rate)
                audio = audio.set_channels(1)      # Mono
                audio = audio.set_sample_width(2)  # 16-bit
                pcm_data = audio.raw_data
            except Exception as e:
                logger.warning(f"pydub from_file failed: {e}, trying fallback")

        # Method 2: If WAV and soundfile available
        if not pcm_data and audio_bytes.startswith(b"RIFF"):
            try:
                import soundfile as sf
                import numpy as np
                import scipy.signal
                data, sr = sf.read(io.BytesIO(audio_bytes), dtype='int16')
                if len(data.shape) > 1:
                    data = data.mean(axis=1).astype(np.int16)
                if sr != sample_rate:
                    num_target = int(len(data) * sample_rate / sr)
                    data = scipy.signal.resample(data, num_target).astype(np.int16)
                pcm_data = data.tobytes()
            except Exception as e:
                logger.debug(f"soundfile direct conversion failed: {e}")

        # Method 3: ffmpeg subprocess (universal for WAV, MP3, AAC)
        if not pcm_data:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", "pipe:0", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "pipe:1",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                pcm_data, _ = await proc.communicate(input=audio_bytes)
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

        logger.error("Failed to convert synthesized audio to PCM.")
        return None
