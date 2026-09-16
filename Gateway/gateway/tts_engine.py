"""
TTS Engine — EdgeTTS Vietnamese text-to-speech.
Converts text responses to audio for playback on ESP32 speaker.
"""

import io
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
    """Vietnamese text-to-speech using Microsoft EdgeTTS."""
    
    def __init__(self):
        self.voice = config.TTS_VOICE
        self.fallback_voice = config.TTS_FALLBACK_VOICE
    
    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert Vietnamese text to MP3 audio bytes.
        
        Input:  "Đã bật đèn ngủ phòng ngủ ạ"
        Output: MP3 audio bytes
        """
        if not text or not text.strip():
            return None
        
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            audio_data = b""
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if audio_data:
                logger.info(f"TTS synthesized: \"{text[:50]}...\" → {len(audio_data)} bytes")
                return audio_data
            else:
                logger.warning("TTS produced empty audio")
                return None
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
            # Try fallback voice
            try:
                communicate = edge_tts.Communicate(text, self.fallback_voice)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data if audio_data else None
            except Exception as e2:
                logger.error(f"TTS fallback also failed: {e2}")
                return None
    
    async def speak_alert(self, message: str) -> Optional[bytes]:
        """Synthesize an alert/notification message."""
        return await self.synthesize(message)

    async def synthesize_pcm(self, text: str, sample_rate: int = 16000) -> Optional[bytes]:
        """
        Convert Vietnamese text to raw PCM audio bytes (16kHz, 16-bit, mono).
        Suitable for direct playback on ESP32 I2S speaker.

        Flow: text → EdgeTTS → MP3 bytes → pydub → raw PCM
        """
        mp3_data = await self.synthesize(text)
        if not mp3_data:
            return None

        if not HAS_PYDUB:
            logger.error("pydub not installed — cannot convert MP3 to PCM")
            return None

        try:
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            audio = audio.set_frame_rate(sample_rate)
            audio = audio.set_channels(1)    # Mono
            audio = audio.set_sample_width(2) # 16-bit
            pcm_data = audio.raw_data
            logger.info(
                f"TTS MP3→PCM converted: {len(mp3_data)} bytes MP3 → "
                f"{len(pcm_data)} bytes PCM ({len(pcm_data) / (sample_rate * 2):.2f}s)"
            )
            return pcm_data
        except Exception as e:
            logger.error(f"MP3→PCM conversion error: {e}")
            return None
