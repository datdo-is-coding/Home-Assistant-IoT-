"""
Audio Server — WebSocket server for ESP32 voice streaming.
Receives Opus/PCM audio streams, decodes via opuslib, runs Sherpa-ONNX ASR,
and streams EdgeTTS speech response back to ESP32 speaker.
"""

import asyncio
import json
import logging
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
        logger.info(f"ESP32 client connected from {client_addr}")
        
        codec = "opus"
        sample_rate = config.ASR_SAMPLE_RATE
        pcm_chunks = []
        decoder = None
        
        if HAS_OPUS:
            try:
                decoder = opuslib.Decoder(sample_rate, 1)
            except Exception as e:
                logger.error(f"Failed to create Opus decoder: {e}")
                decoder = None
                
        try:
            async for message in websocket:
                if isinstance(message, str):
                    # Control message
                    try:
                        cmd = json.loads(message)
                        msg_type = cmd.get("type", "")
                        
                        if msg_type == "start":
                            codec = cmd.get("codec", "opus")
                            sample_rate = cmd.get("sample_rate", config.ASR_SAMPLE_RATE)
                            pcm_chunks.clear()
                            if codec == "opus" and HAS_OPUS:
                                decoder = opuslib.Decoder(sample_rate, 1)
                            logger.info(f"Voice recording started (codec={codec}, sr={sample_rate})")
                            await websocket.send(json.dumps({"type": "status", "state": "recording"}))
                            
                        elif msg_type == "stop":
                            logger.info(f"Voice recording ended. Received {len(pcm_chunks)} chunks.")
                            await websocket.send(json.dumps({"type": "status", "state": "processing"}))
                            
                            # Process the collected audio
                            if pcm_chunks:
                                full_pcm = np.concatenate(pcm_chunks)
                                await self._process_audio(websocket, full_pcm, sample_rate)
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
                        
                elif isinstance(message, bytes):
                    # Audio data frame
                    if codec == "opus" and decoder:
                        try:
                            # Standard frame sizes: 960 (60ms), 640 (40ms), 480 (30ms), 320 (20ms)
                            pcm_raw = decoder.decode(message, 960)
                            pcm_data = np.frombuffer(pcm_raw, dtype=np.int16).astype(np.float32) / 32768.0
                            pcm_chunks.append(pcm_data)
                        except Exception as e:
                            logger.debug(f"Opus decode error: {e}")
                    else:
                        # Raw PCM (16-bit mono 16kHz)
                        pcm_data = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768.0
                        pcm_chunks.append(pcm_data)
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"ESP32 client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling WebSocket client {client_addr}: {e}")
            
    async def _process_audio(self, websocket, pcm_samples: np.ndarray, sample_rate: int):
        """Transcribe audio with Sherpa-ONNX and execute gateway command."""
        duration_s = len(pcm_samples) / sample_rate
        logger.info(f"Processing speech: {len(pcm_samples)} samples ({duration_s:.2f}s)")
        
        if not self.gateway or not hasattr(self.gateway, "asr"):
            logger.error("Gateway ASR engine not available")
            return
            
        # 1. Speech-to-text
        text = self.gateway.asr.transcribe(pcm_samples, sample_rate)
        if not text:
            logger.warning("ASR returned empty transcript")
            reply = "Em không nghe rõ. Bạn nói lại được không?"
            await websocket.send(json.dumps({"type": "transcript", "text": ""}))
            await self._send_voice_reply(websocket, reply)
            return
            
        logger.info(f"Recognized voice: '{text}'")
        await websocket.send(json.dumps({"type": "transcript", "text": text}))
        
        # 2. Process command through Gateway
        result = await self.gateway.process_voice_command(text)
        await websocket.send(json.dumps({
            "type": "command_result",
            "verify": result.get("verify"),
            "voice_reply": result.get("voice_reply")
        }))
        
        # 3. Stream TTS audio back to ESP32 speaker
        audio_data = result.get("tts_audio")
        if audio_data:
            await self._send_audio_stream(websocket, audio_data)
            
    async def _send_voice_reply(self, websocket, text: str):
        """Synthesize text and send to client."""
        if not self.gateway or not hasattr(self.gateway, "tts"):
            return
        audio = await self.gateway.tts.synthesize(text)
        if audio:
            await self._send_audio_stream(websocket, audio)
            
    async def _send_audio_stream(self, websocket, audio_bytes: bytes):
        """Stream audio data back to ESP32 in chunks."""
        total_len = len(audio_bytes)
        chunk_size = 2048
        
        # Send start marker
        await websocket.send(json.dumps({
            "type": "audio_start",
            "format": "mp3",
            "size": total_len
        }))
        
        # Send binary chunks
        for i in range(0, total_len, chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            await websocket.send(chunk)
            await asyncio.sleep(0.005)  # slight throttle to prevent ESP32 buffer overrun
            
        # Send end marker
        await websocket.send(json.dumps({"type": "audio_end"}))
        logger.info(f"Streamed {total_len} bytes audio back to ESP32")
