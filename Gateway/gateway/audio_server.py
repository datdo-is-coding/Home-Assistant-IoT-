"""
Audio Server — WebSocket server for ESP32 voice streaming.
Receives PCM audio from ESP32-S3, runs Sherpa-ONNX ASR,
dispatches commands via Gateway, and streams TTS PCM response
back to ESP32 speaker.

Protocol (ESP32 → Pi):
  TEXT:   {"type":"start","codec":"pcm","sample_rate":16000}
  BINARY: [640 bytes PCM 16kHz/16bit/mono per 20ms frame]
  TEXT:   {"type":"stop"}

Protocol (Pi → ESP32):
  TEXT:   {"type":"status","state":"recording|processing"}
  TEXT:   {"type":"transcript","text":"..."}
  TEXT:   {"type":"command_result","verify":"...","voice_reply":"..."}
  TEXT:   {"type":"audio_start","format":"pcm","sample_rate":16000,"size":N}
  BINARY: [2048 bytes PCM chunks]
  TEXT:   {"type":"audio_end"}
"""

import asyncio
import json
import logging
import time
from typing import Optional
import websockets
import numpy as np

try:
    import opuslib
    HAS_OPUS = True
except ImportError:
    HAS_OPUS = False

import config

logger = logging.getLogger("audio_server")


class AudioServer:
    """WebSocket server handling ESP32 two-way audio streaming."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.host = config.WS_AUDIO_HOST
        self.port = config.WS_AUDIO_PORT
        self.server = None
        self._running = False

    async def start(self):
        """Start the WebSocket server."""
        self._running = True
        logger.info(f"Starting Audio WebSocket server on {self.host}:{self.port}")
        self.server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=30,
            max_size=10 * 1024 * 1024  # 10MB max message size
        )
        logger.info("Audio WebSocket server running and ready for ESP32 connections")

    async def stop(self):
        """Stop the server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Audio WebSocket server stopped")

    async def _handle_client(self, websocket, path=None):
        """Handle an active ESP32 WebSocket connection."""
        client_addr = websocket.remote_address
        logger.info(f"🔗 ESP32 client connected from {client_addr}")

        codec = "pcm"
        sample_rate = config.AUDIO_SAMPLE_RATE
        pcm_chunks = []
        decoder = None
        recording = False
        record_start_time = 0.0
        total_frames = 0

        try:
            async for message in websocket:
                if isinstance(message, str):
                    # ─── Text Control Message ───
                    try:
                        cmd = json.loads(message)
                        msg_type = cmd.get("type", "")

                        if msg_type == "start":
                            codec = cmd.get("codec", "pcm")
                            sample_rate = cmd.get("sample_rate", config.AUDIO_SAMPLE_RATE)
                            pcm_chunks.clear()
                            recording = True
                            record_start_time = time.monotonic()
                            total_frames = 0

                            # Setup Opus decoder if needed
                            if codec == "opus" and HAS_OPUS:
                                decoder = opuslib.Decoder(sample_rate, 1)

                            logger.info(
                                f"🎙️ Voice recording STARTED "
                                f"(codec={codec}, sr={sample_rate}Hz)"
                            )
                            await websocket.send(json.dumps({
                                "type": "status", "state": "recording"
                            }))

                        elif msg_type == "stop":
                            recording = False
                            elapsed = time.monotonic() - record_start_time
                            logger.info(
                                f"🛑 Voice recording ENDED — "
                                f"{total_frames} frames, "
                                f"{len(pcm_chunks)} chunks, "
                                f"{elapsed:.2f}s"
                            )
                            await websocket.send(json.dumps({
                                "type": "status", "state": "processing"
                            }))

                            # Process the collected audio
                            if pcm_chunks:
                                full_pcm = np.concatenate(pcm_chunks)
                                await self._process_audio(
                                    websocket, full_pcm, sample_rate
                                )
                            else:
                                logger.warning("No audio data received")
                                await websocket.send(json.dumps({
                                    "type": "error",
                                    "message": "Không nhận được âm thanh"
                                }))

                            pcm_chunks.clear()

                        elif msg_type == "ping":
                            await websocket.send(json.dumps({"type": "pong"}))

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid text frame: {message[:100]}")

                elif isinstance(message, bytes) and recording:
                    # ─── Binary Audio Data ───
                    total_frames += 1

                    if codec == "opus" and decoder:
                        try:
                            pcm_raw = decoder.decode(message, 960)
                            pcm_float = (
                                np.frombuffer(pcm_raw, dtype=np.int16)
                                .astype(np.float32) / 32768.0
                            )
                            pcm_chunks.append(pcm_float)
                        except Exception as e:
                            logger.debug(f"Opus decode error: {e}")
                    else:
                        # Raw PCM: 16-bit signed little-endian mono
                        pcm_float = (
                            np.frombuffer(message, dtype=np.int16)
                            .astype(np.float32) / 32768.0
                        )
                        pcm_chunks.append(pcm_float)

                    # ─── Server-side max duration check ───
                    elapsed = time.monotonic() - record_start_time
                    if elapsed > config.VAD_MAX_DURATION_S:
                        logger.info(
                            f"Max recording duration ({config.VAD_MAX_DURATION_S}s) "
                            f"reached — auto-stopping"
                        )
                        recording = False
                        await websocket.send(json.dumps({
                            "type": "status", "state": "processing"
                        }))
                        if pcm_chunks:
                            full_pcm = np.concatenate(pcm_chunks)
                            await self._process_audio(
                                websocket, full_pcm, sample_rate
                            )
                        pcm_chunks.clear()

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"ESP32 client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling WebSocket client {client_addr}: {e}")

    async def _process_audio(
        self, websocket, pcm_samples: np.ndarray, sample_rate: int
    ):
        """
        Full voice pipeline:
          1. ASR (Speech-to-Text)
          2. Intent Extraction (LLM)
          3. Command Dispatch (MQTT)
          4. TTS Response → PCM → stream to ESP32 speaker
        """
        duration_s = len(pcm_samples) / sample_rate
        logger.info(
            f"📊 Processing speech: {len(pcm_samples)} samples ({duration_s:.2f}s)"
        )

        if not self.gateway or not hasattr(self.gateway, "asr"):
            logger.error("Gateway ASR engine not available")
            return

        # ─── Step 1: Speech-to-Text ───
        text = self.gateway.asr.transcribe(pcm_samples, sample_rate)
        if not text:
            logger.warning("ASR returned empty transcript")
            reply = "Em không nghe rõ. Bạn nói lại được không?"
            await websocket.send(json.dumps({
                "type": "transcript", "text": ""
            }))
            await self._send_voice_reply(websocket, reply)
            return

        logger.info(f"📝 Recognized voice: '{text}'")
        await websocket.send(json.dumps({
            "type": "transcript", "text": text
        }))

        # ─── Step 2-4: Process command through Gateway ───
        result = await self.gateway.process_voice_command(text)
        await websocket.send(json.dumps({
            "type": "command_result",
            "verify": result.get("verify"),
            "voice_reply": result.get("voice_reply"),
        }))

        # ─── Step 5: Stream TTS audio back to ESP32 speaker ───
        voice_reply = result.get("voice_reply")
        if voice_reply:
            await self._send_voice_reply(websocket, voice_reply)

    async def _send_voice_reply(self, websocket, text: str):
        """Synthesize text to PCM and stream to ESP32 speaker."""
        if not self.gateway or not hasattr(self.gateway, "tts"):
            logger.warning("TTS engine not available")
            return

        # Synthesize to PCM (16kHz, 16-bit, mono) — directly playable by ESP32 I2S
        pcm_audio = await self.gateway.tts.synthesize_pcm(
            text, sample_rate=config.AUDIO_SAMPLE_RATE
        )

        if pcm_audio:
            await self._send_pcm_stream(websocket, pcm_audio)
        else:
            # Fallback: try sending MP3 if PCM conversion failed
            logger.warning("PCM synthesis failed, trying raw MP3 fallback")
            mp3_audio = await self.gateway.tts.synthesize(text)
            if mp3_audio:
                await self._send_audio_stream_mp3(websocket, mp3_audio)

    async def _send_pcm_stream(self, websocket, pcm_bytes: bytes):
        """
        Stream raw PCM audio data back to ESP32 in chunks.
        Format: 16kHz, 16-bit signed, little-endian, mono.
        ESP32 writes directly to I2S speaker — no decoding needed.
        """
        total_len = len(pcm_bytes)
        chunk_size = config.WS_SEND_CHUNK_SIZE
        duration_s = total_len / (config.AUDIO_SAMPLE_RATE * config.AUDIO_SAMPLE_WIDTH)

        logger.info(
            f"🔊 Streaming {total_len} bytes PCM to ESP32 speaker "
            f"({duration_s:.2f}s audio)"
        )

        # Send start marker with PCM format info
        await websocket.send(json.dumps({
            "type": "audio_start",
            "format": "pcm",
            "sample_rate": config.AUDIO_SAMPLE_RATE,
            "channels": config.AUDIO_CHANNELS,
            "sample_width": config.AUDIO_SAMPLE_WIDTH,
            "size": total_len,
        }))

        # Send binary PCM chunks
        chunks_sent = 0
        for i in range(0, total_len, chunk_size):
            chunk = pcm_bytes[i:i + chunk_size]
            await websocket.send(chunk)
            chunks_sent += 1
            # Slight throttle to prevent ESP32 buffer overrun
            # 2048 bytes = 64ms of audio → send at ~2x real-time
            await asyncio.sleep(0.005)

        # Send end marker
        await websocket.send(json.dumps({"type": "audio_end"}))
        logger.info(
            f"✅ Streamed {total_len} bytes in {chunks_sent} chunks to ESP32"
        )

    async def _send_audio_stream_mp3(self, websocket, audio_bytes: bytes):
        """
        Fallback: Stream MP3 audio data back to ESP32.
        ESP32 would need an MP3 decoder for this path.
        """
        total_len = len(audio_bytes)
        chunk_size = config.WS_SEND_CHUNK_SIZE

        # Send start marker
        await websocket.send(json.dumps({
            "type": "audio_start",
            "format": "mp3",
            "size": total_len,
        }))

        # Send binary chunks
        for i in range(0, total_len, chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            await websocket.send(chunk)
            await asyncio.sleep(0.005)

        # Send end marker
        await websocket.send(json.dumps({"type": "audio_end"}))
        logger.info(f"Streamed {total_len} bytes MP3 to ESP32 (fallback)")
