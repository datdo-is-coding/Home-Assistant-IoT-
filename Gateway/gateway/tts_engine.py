"""
TTS Engine — EdgeTTS Vietnamese text-to-speech.
Converts text responses to audio for playback on ESP32 speaker.
"""

import io
import logging
import asyncio
from typing import Optional

import edge_tts

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
