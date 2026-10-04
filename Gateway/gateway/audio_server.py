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
from typing import Optional, Tuple, Any
try:
    import websockets
except ImportError:
    websockets = None

try:
    import numpy as np
except ImportError:
    class _DummyNP:
        ndarray = Any
    np = _DummyNP()

try:
    import opuslib
    HAS_OPUS = True
except ImportError:
    HAS_OPUS = False

import config

logger = logging.getLogger("audio_server")


class StreamArbiter:
    """Đo lường năng lượng âm thanh (RMS) đa node để định vị phòng người dùng đang đứng."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        # node_id -> {"rms_values": [...], "start_time": float}
        self.active_streams: dict = {}

    def register_start(self, node_id: str):
        now = time.time()
        # Dọn các stream cũ hơn 5 giây
        self.active_streams = {nid: d for nid, d in self.active_streams.items() if (now - d["start_time"]) < 5.0}
        self.active_streams[node_id] = {"rms_values": [], "start_time": now}

    def add_rms(self, node_id: str, rms: float):
        if node_id in self.active_streams:
            self.active_streams[node_id]["rms_values"].append(rms)

    def determine_dominant_room(self, current_node_id: str) -> Tuple[str, Optional[str]]:
        """
        Xác định node và phòng chiếm ưu thế về âm lượng (nơi phát ra giọng nói lớn nhất).
        Returns: (dominant_node_id, dominant_room)
        """
        if not self.active_streams:
            return current_node_id, self._get_room(current_node_id)

        now = time.time()
        candidates = {}
        for nid, data in self.active_streams.items():
            if (now - data["start_time"]) <= 3.0 and data["rms_values"]:
                top_rms = sorted(data["rms_values"], reverse=True)[:10]
                avg_top = sum(top_rms) / len(top_rms) if top_rms else 0
                candidates[nid] = avg_top

        if not candidates or current_node_id not in candidates:
            return current_node_id, self._get_room(current_node_id)

        dominant_nid = max(candidates, key=candidates.get)
        dominant_room = self._get_room(dominant_nid)
        logger.info(f"📍 Spatial Audio Arbiter: {candidates} -> Dominant node '{dominant_nid}' in room '{dominant_room}'")
        return dominant_nid, dominant_room

    def _get_room(self, node_id: str) -> Optional[str]:
        if self.gateway and hasattr(self.gateway, "registry") and self.gateway.registry:
            node = self.gateway.registry.get_all_nodes().get(node_id, {})
            room = node.get("room")
            if room and room != "unknown":
                return room
        return None


class AudioServer:
    """WebSocket server handling ESP32 two-way audio streaming."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.host = config.WS_AUDIO_HOST
        self.port = config.WS_AUDIO_PORT
        self.server = None
        self._running = False
        # node_id -> websocket, cho phép gửi relay command trực tiếp trên socket audio
        self._ws_nodes: dict = {}
        # Tập hợp tất cả các websocket loa ESP32 vật lý đang hoạt động
        self._active_speakers: set = set()
        self._playback_lock = asyncio.Lock()
        # ponytail: one recognizer worker; add independent model workers only after profiling.
        self._asr_lock = asyncio.Lock()
        self._active_voice_session = None  # {"node_id": str, "timestamp": float}
        self.arbiter = StreamArbiter(gateway=self.gateway)

    def _is_ws_alive(self, ws) -> bool:
        """Kiểm tra websocket còn sống không (tương thích mọi version websockets)."""
        if ws is None:
            return False
        try:
            # websockets >= 10.x uses .open; older versions use not .closed
            if hasattr(ws, 'open'):
                return bool(ws.open)
            if hasattr(ws, 'closed'):
                return not bool(ws.closed)
            return True  # fallback: assume alive
        except Exception:
            return False

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

        client_node_id = None
        websocket.has_speaker = True

        codec = "pcm"
        sample_rate = config.AUDIO_SAMPLE_RATE
        pcm_chunks = []
        decoder = None
        recording = False
        record_start_time = 0.0
        total_frames = 0
        client_mac = None
        installed = {}  # channel -> device_fullname for WS-commandable node

        try:
            async for message in websocket:
                if isinstance(message, str):
                    # ─── Text Control Message ───
                    try:
                        cmd = json.loads(message)
                        msg_type = cmd.get("type", "")
                        # Compact protocol (protocol_spec.md): {"t":"..."} 
                        compact_type = cmd.get("t")

                        # ── COMPACT: HELLO / register / provision handshake ──
                        if compact_type == "hello":
                            client_mac = (cmd.get("mac") or "").upper()
                            handled = None
                            if self.gateway and hasattr(self.gateway, "registry"):
                                handled = self.gateway.registry.on_hello(cmd, ws_available=True)
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("node_hello", cmd)
                            node_id = handled.get("node_id") if handled else None
                            if not node_id and cmd.get("id"):
                                node_id = cmd.get("id")

                            if node_id:
                                client_node_id = node_id
                                self._ws_nodes[client_node_id] = websocket
                                is_spk = cmd.get("speaker") is not False and "subbox" not in str(node_id).lower()
                                websocket.has_speaker = is_spk
                                websocket.asr_only = cmd.get("asr_only") is True
                                websocket.audio_relay = cmd.get("audio_relay") is True
                                if is_spk:
                                    self._active_speakers.add(websocket)
                                    logger.info(f"📢 ESP32 speaker registered from {client_addr} (Active speaker pool: {len(self._active_speakers)})")
                                else:
                                    self._active_speakers.discard(websocket)
                                    logger.info(f"🎤 ESP32 ASR-only node '{node_id}' registered from {client_addr}")

                            if handled and handled.get("action") == "known":
                                logger.info(f"✅ Node '{node_id}' registered for WS relay + speaker broadcast (pool: {len(self._active_speakers)})")
                                await websocket.send(json.dumps({"t": "hello_ok", "id": node_id}))
                            elif handled and handled.get("action") == "cfg_mismatch":
                                # re-provision
                                if self.gateway and hasattr(self.gateway, "mqtt"):
                                    cfg = self.gateway.registry.get_provision_payload(node_id)
                                    if cfg:
                                        await self.gateway.mqtt.send_cfg(node_id, cfg)
                                await websocket.send(json.dumps({"t": "cfg_sent", "id": node_id}))
                            elif handled and handled.get("action") == "pending":
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("pending_node", {"mac": client_mac, "hello": cmd})
                                await websocket.send(json.dumps({"t": "pending", "mac": client_mac}))
                            else:
                                logger.warning(f"hello_ignored: {cmd}")
                            continue

                        # ── COMPACT: relay ACK ──
                        elif compact_type == "ack":
                            nid = cmd.get("id")
                            rl = cmd.get("rl")
                            if self.gateway and nid:
                                self.gateway.mqtt.record_compact_ack(nid, cmd)
                            if nid and isinstance(rl, list):
                                if self.gateway and hasattr(self.gateway, "registry"):
                                    self.gateway.registry.update_relay_state(nid, rl)
                                    self.gateway.registry.update_heartbeat(nid)
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("node_status",
                                        {"node_id": nid, "rl_state": rl, "seq": cmd.get("seq"),
                                         "ch1": rl[0] if len(rl)>0 else None,
                                         "ch2": rl[1] if len(rl)>1 else None})
                                logger.info(f"ACK {nid} rl={rl} seq={cmd.get('seq')}")
                            continue

                        # ── COMPACT: node requests config (mac-based) ──
                        elif compact_type == "need_cfg":
                            mac = (cmd.get("mac") or "").upper()
                            # find node by mac in registry
                            found = None
                            if self.gateway:
                                nid = self.gateway.registry.find_node_by_mac(mac) if hasattr(self.gateway.registry, "find_node_by_mac") else None
                                if nid:
                                    cfg = self.gateway.registry.get_provision_payload(nid)
                                    if self.gateway.mqtt:
                                        await self.gateway.mqtt.send_cfg(nid, cfg)
                                        found = True
                            if not found:
                                await websocket.send(json.dumps({"t": "pending", "mac": mac}))
                            continue

                        # ── LEGACY: start / stop / ping (giữ nguyên) ──
                        if msg_type == "start":
                            websocket.asr_only = cmd.get("asr_only") is True
                            websocket.audio_relay = cmd.get("audio_relay") is True
                            if self._playback_lock.locked():
                                curr_node = client_node_id or "node_voice"
                                logger.info(f"🔇 Rejecting mic stream from '{curr_node}': speaker is actively playing TTS audio")
                                await websocket.send(json.dumps({
                                    "type": "suppressed", "reason": "speaker_busy"
                                }))
                                continue

                            codec = cmd.get("codec", "pcm")
                            sample_rate = cmd.get("sample_rate", config.AUDIO_SAMPLE_RATE)
                            pcm_chunks.clear()
                            recording = True
                            record_start_time = time.monotonic()
                            total_frames = 0
                            if cmd.get("node_id"):
                                client_node_id = cmd.get("node_id")
                            curr_node = client_node_id or "node_voice"
                            self._ws_nodes[curr_node] = websocket
                            if cmd.get("speaker") is False or "subbox" in str(curr_node).lower():
                                websocket.has_speaker = False
                                self._active_speakers.discard(websocket)
                            elif getattr(websocket, "has_speaker", True):
                                self._active_speakers.add(websocket)
                            self.arbiter.register_start(curr_node)

                            # Setup Opus decoder if needed
                            if codec == "opus" and HAS_OPUS:
                                decoder = opuslib.Decoder(sample_rate, 1)

                            logger.info(
                                f"🎙️ Voice recording STARTED from {curr_node} "
                                f"(codec={codec}, sr={sample_rate}Hz)"
                            )
                            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                self.gateway.broadcast_event("audio_state", {"state": "RECORDING"})
                            await websocket.send(json.dumps({
                                "type": "status", "state": "recording"
                            }))

                        elif msg_type == "cancel":
                            recording = False
                            pcm_chunks.clear()
                            self.arbiter.active_streams.pop(client_node_id, None)
                            await websocket.send(json.dumps({"type": "status", "state": "cancelled"}))

                        elif msg_type == "stop":
                            if not recording:
                                continue
                            recording = False
                            now_ts = time.monotonic()
                            elapsed = now_ts - record_start_time
                            curr_node = client_node_id or "node_voice"

                            # 1. Nếu đã có phiên giọng nói đang xử lý từ node khác trong 3.5s qua, suppress ngay để tránh xung đột
                            if self._active_voice_session and (now_ts - self._active_voice_session.get("timestamp", 0)) < 3.5:
                                active_nid = self._active_voice_session.get("node_id")
                                if active_nid and active_nid != curr_node:
                                    logger.info(f"🔇 Spatial Arbiter: Suppressed concurrent stream from '{curr_node}' (active session already on '{active_nid}')")
                                    await websocket.send(json.dumps({
                                        "type": "suppressed",
                                        "dominant_node": active_nid,
                                        "detected_room": self.arbiter._get_room(active_nid)
                                    }))
                                    pcm_chunks.clear()
                                    continue

                            dominant_nid, detected_room = self.arbiter.determine_dominant_room(curr_node)
                            logger.info(
                                f"🛑 Voice recording ENDED — "
                                f"{total_frames} frames, "
                                f"{len(pcm_chunks)} chunks, "
                                f"{elapsed:.2f}s (detected_room={detected_room})"
                            )

                            if dominant_nid and dominant_nid != curr_node:
                                logger.info(f"🔇 Spatial Arbiter: Suppressed weaker stream '{curr_node}' in favor of dominant '{dominant_nid}' ({detected_room})")
                                await websocket.send(json.dumps({
                                    "type": "suppressed",
                                    "dominant_node": dominant_nid,
                                    "detected_room": detected_room
                                }))
                                pcm_chunks.clear()
                                continue

                            # Khóa phiên giọng nói cho node chiếm ưu thế
                            self._active_voice_session = {"node_id": curr_node, "timestamp": now_ts}

                            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                self.gateway.broadcast_event("audio_state", {"state": "PROCESSING"})
                            await websocket.send(json.dumps({
                                "type": "status", "state": "processing"
                            }))

                            # Process the collected audio
                            if pcm_chunks:
                                full_pcm = np.concatenate(pcm_chunks)
                                await self._process_audio(
                                    websocket, full_pcm, sample_rate,
                                    client_node_id=curr_node,
                                    detected_room=detected_room
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

                        elif msg_type and not compact_type:
                            logger.debug(f"Ignored text msg: {msg_type}")

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
                        raw_i16 = np.frombuffer(message, dtype=np.int16)
                        pcm_float = raw_i16.astype(np.float32) / 32768.0
                        pcm_chunks.append(pcm_float)

                        if len(raw_i16) > 0:
                            rms = int(np.sqrt(np.mean(np.square(raw_i16.astype(np.float32)))))
                            curr_node = client_node_id or "node_voice"
                            self.arbiter.add_rms(curr_node, rms)
                            if self.gateway and hasattr(self.gateway, "broadcast_event") and total_frames % 2 == 0:
                                self.gateway.broadcast_event("audio_meter", {"rms": rms, "frames": total_frames})

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
                            curr_node = client_node_id or "node_voice"
                            dominant_nid, detected_room = self.arbiter.determine_dominant_room(curr_node)
                            await self._process_audio(
                                websocket, full_pcm, sample_rate,
                                client_node_id=curr_node,
                                detected_room=detected_room
                            )
                        pcm_chunks.clear()

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"ESP32 client disconnected: {client_addr} (code={e.code}, reason='{e.reason}')")
            self._active_speakers.discard(websocket)
            # remove node from ws registry
            for nid, ws in list(self._ws_nodes.items()):
                if ws is websocket:
                    del self._ws_nodes[nid]
            # Dọn dead sockets khỏi _active_speakers
            self._active_speakers = {ws for ws in self._active_speakers if self._is_ws_alive(ws)}
            logger.info(f"WS node still connected: {list(self._ws_nodes.keys())}, active speakers: {len(self._active_speakers)}")
        except Exception as e:
            self._active_speakers.discard(websocket)
            self._active_speakers = {ws for ws in self._active_speakers if self._is_ws_alive(ws)}
            logger.error(f"Error handling WebSocket client {client_addr}: {e}")

    def has_ws(self, node_id: str) -> bool:
        """Check if node has a stable WS audio connection (relay over WS available)."""
        ws = self._ws_nodes.get(node_id)
        return (ws is not None and not getattr(ws, "asr_only", False)
                and not getattr(ws, "audio_relay", False) and self._is_ws_alive(ws))

    async def send_relay_ws(self, node_id: str, channel: str, action: str, seq: int) -> bool:
        """
        Gửi relay command TRỰC TIẾP trên socket audio (TEXT frame, opcode 0x1).
        Payload: {"t":"rl","ch":1,"s":1,"seq":n} (~27 byte, nhẹ hơn 1 PCM frame ~24 lần).
        TEXT frame xen kẽ vẫn giữ luồng PCM 2 chiều ổn định.
        """
        ws = self._ws_nodes.get(node_id)
        if not self.has_ws(node_id):
            return False
        ch = {"ch1": 1, "ch2": 2}.get(channel, 0)
        if ch not in (1, 2):
            return False
        s = 1 if action in ("turn_on", "open", "on") else 0
        payload = json.dumps({"t": "rl", "ch": ch, "s": s, "seq": seq})
        try:
            await ws.send(payload)
            logger.info(f"⚡ WS relay {node_id} ch{ch}={s} seq={seq} (~{len(payload)}B)")
            return True
        except Exception as e:
            logger.warning(f"WS relay to {node_id} failed: {e}")
            # dọn socket hỏng
            self._ws_nodes.pop(node_id, None)
            return False

    async def _process_audio(
        self,
        websocket,
        pcm_samples: np.ndarray,
        sample_rate: int,
        client_node_id: str = "node_voice",
        detected_room: Optional[str] = None
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
            f"📊 Processing speech: {len(pcm_samples)} samples ({duration_s:.2f}s) "
            f"from {client_node_id} (detected_room={detected_room})"
        )

        if not self.gateway or not hasattr(self.gateway, "asr"):
            logger.error("Gateway ASR engine not available")
            return

        # ─── Step 1: Speech-to-Text with confidence scoring ───
        # One model invocation at a time; reject overload instead of accumulating PCM.
        if self._asr_lock.locked():
            await websocket.send(json.dumps({"type": "transcript", "text": "", "accepted": False,
                                             "reason": "asr_busy"}))
            return
        async with self._asr_lock:
            inference = asyncio.create_task(asyncio.to_thread(
                self.gateway.asr.transcribe_with_confidence, pcm_samples, sample_rate))
            try:
                text, confidence = await asyncio.shield(inference)
            except asyncio.CancelledError:
                # A cancelled socket cannot release the model while its thread is running.
                await inference
                raise

        if not text:
            logger.warning("ASR returned empty transcript")
            reply = "Em không nghe rõ. Bạn nói lại được không?"
            await websocket.send(json.dumps({
                "type": "transcript", "text": "", "accepted": False
            }))
            await self._send_voice_reply(websocket, reply, follow_up=True, broadcast=False)
            return

        # If confidence is very low, ask user to repeat (don't blindly execute)
        from asr_engine import ASREngine
        if confidence < ASREngine.CONFIDENCE_LOW:
            logger.warning(f"ASR confidence too low ({confidence:.2f}): '{text}' — asking user to repeat")
            reply = "Chưa rõ khẩu lệnh."
            await websocket.send(json.dumps({
                "type": "transcript", "text": "", "confidence": round(confidence, 2), "accepted": False
            }))
            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("transcript", {"text": text, "confidence": round(confidence, 2), "status": "low_confidence"})
            await self._send_voice_reply(websocket, reply, follow_up=True, broadcast=False)
            return

        if confidence < ASREngine.CONFIDENCE_MEDIUM:
            logger.warning(f"ASR confidence medium ({confidence:.2f}): '{text}' — proceeding with caution")

        logger.info(f"📝 Recognized voice: '{text}' (confidence={confidence:.2f})")
        if self.gateway and hasattr(self.gateway, "broadcast_event"):
            self.gateway.broadcast_event("transcript", {"text": text, "confidence": round(confidence, 2)})
        await websocket.send(json.dumps({
            "type": "transcript", "text": text, "confidence": round(confidence, 2), "accepted": True
        }))

        if getattr(websocket, "asr_only", False):
            return

        # ─── Step 2-4: Process command through Gateway ───
        result = await self.gateway.process_voice_command(
            text, client_node_id=client_node_id, detected_room=detected_room
        )
        follow_up = result.get("follow_up", False)
        await websocket.send(json.dumps({
            "type": "command_result",
            "verify": result.get("verify"),
            "voice_reply": result.get("voice_reply"),
            "follow_up": follow_up,
        }))

        # ─── Step 5: Stream audio back to ESP32 speaker (Unicast to caller) ───
        tts_audio = result.get("tts_audio")
        tts_format = result.get("tts_format", "pcm")
        voice_reply = result.get("voice_reply")
        if tts_audio and tts_format == "pcm":
            await self._send_pcm_stream(websocket, tts_audio, follow_up=follow_up)
        elif tts_audio and tts_format == "mp3":
            await self._send_audio_stream_mp3(websocket, tts_audio, follow_up=follow_up)
        elif voice_reply:
            await self._send_voice_reply(websocket, voice_reply, follow_up=follow_up, broadcast=False)

    async def speak_proactive(self, text: str, node_id: str = None) -> bool:
        """
        Chủ động phát âm thanh ra loa ESP32 (không cần user gọi trước).
        - Nếu node_id cụ thể: phát ra node đó.
        - Nếu node_id là None hoặc 'all': phát đồng thời ra TẤT CẢ các loa ESP32 đang kết nối.
        """
        if not self.gateway or not hasattr(self.gateway, "tts"):
            logger.warning("TTS engine not available for proactive speech")
            return False

        targets = []
        if node_id and node_id != "all":
            ws = self._ws_nodes.get(node_id)
            if ws and self._is_ws_alive(ws):
                targets = [ws]
            elif self._ws_nodes:
                alive = [w for w in self._ws_nodes.values() if self._is_ws_alive(w)]
                if alive:
                    targets = [alive[0]]
        else:
            # Broadcast tới tất cả các loa đang hoạt động
            targets = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
            if not targets and self._ws_nodes:
                targets = [ws for ws in self._ws_nodes.values() if self._is_ws_alive(ws)]

        if not targets:
            logger.debug("No active WebSocket speaker connected to receive proactive audio")
            return False

        try:
            pcm_audio = await self.gateway.tts.synthesize_pcm(
                text, sample_rate=config.AUDIO_SAMPLE_RATE
            )
            if pcm_audio:
                await self._broadcast_pcm_stream(targets, pcm_audio, follow_up=False)
                return True
            else:
                mp3_audio = await self.gateway.tts.synthesize(text)
                if mp3_audio:
                    for ws in targets:
                        await self._send_audio_stream_mp3(ws, mp3_audio, follow_up=False)
                    return True
        except Exception as e:
            logger.error(f"Failed to speak proactive audio: {e}")
        return False

    async def _send_voice_reply(self, websocket, text: str, follow_up: bool = False, broadcast: bool = False):
        """Synthesize text to PCM and stream to ESP32 speaker(s) — unicast by default."""
        if not getattr(websocket, "has_speaker", True) and not broadcast:
            logger.info("Caller node has no speaker — skipping TTS audio stream")
            return

        if not self.gateway or not hasattr(self.gateway, "tts"):
            logger.warning("TTS engine not available")
            return

        # Synthesize to PCM (16kHz, 16-bit, mono) — directly playable by ESP32 I2S
        pcm_audio = await self.gateway.tts.synthesize_pcm(
            text, sample_rate=config.AUDIO_SAMPLE_RATE
        )

        if pcm_audio:
            targets = []
            if broadcast and self._active_speakers:
                targets = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
            elif websocket and self._is_ws_alive(websocket):
                targets = [websocket]
            elif self._active_speakers:
                alive = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
                if alive:
                    targets = [alive[0]]

            if targets:
                await self._broadcast_pcm_stream(targets, pcm_audio, follow_up=follow_up, initiator_ws=websocket)
        else:
            # Fallback: try sending MP3 if PCM conversion failed
            logger.warning("PCM synthesis failed, trying raw MP3 fallback")
            mp3_audio = await self.gateway.tts.synthesize(text)
            if mp3_audio and websocket and self._is_ws_alive(websocket):
                await self._send_audio_stream_mp3(websocket, mp3_audio, follow_up=follow_up)

    async def _send_pcm_stream(self, websocket, pcm_bytes: bytes, follow_up: bool = False):
        """Single speaker wrapper for _broadcast_pcm_stream."""
        await self._broadcast_pcm_stream([websocket], pcm_bytes, follow_up=follow_up)

    async def _broadcast_pcm_stream(self, targets: list, pcm_bytes: bytes, follow_up: bool = False, initiator_ws=None):
        """
        Stream raw PCM audio data to ESP32 speaker(s).
        Protected by self._playback_lock so multiple streams can never interleave or corrupt audio.
        Pacing is calibrated: 8 pre-buffer chunks (~512ms) then 70% real-time pacing (~45ms)
        so ESP32 512KB PSRAM DMA buffer never underflows.
        """
        targets = [ws for ws in targets if getattr(ws, "has_speaker", True)
                   and not getattr(ws, "audio_relay", False) and self._is_ws_alive(ws)]
        if not targets:
            return
        async with self._playback_lock:
            valid_targets = [ws for ws in targets if self._is_ws_alive(ws)]
            if not valid_targets:
                return

            total_len = len(pcm_bytes)
            chunk_size = config.WS_SEND_CHUNK_SIZE
            duration_s = total_len / (config.AUDIO_SAMPLE_RATE * config.AUDIO_SAMPLE_WIDTH)

            logger.info(
                f"🔊 Streaming {total_len} bytes PCM to {len(valid_targets)} ESP32 speaker(s) "
                f"({duration_s:.2f}s audio, follow_up={follow_up})"
            )
            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("audio_state", {"state": "PLAYING"})

            # Thông báo cho TẤT CẢ các ESP32 trong nhà tắt mic / mute wake word để chống tự kích hoạt (echo suppression)
            busy_msg = json.dumps({"type": "speaker_busy", "busy": True})
            all_ws = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
            if all_ws:
                await asyncio.gather(*[ws.send(busy_msg) for ws in all_ws], return_exceptions=True)

            # Send start marker to all targets simultaneously
            start_msg = json.dumps({
                "type": "audio_start",
                "format": "pcm",
                "sample_rate": config.AUDIO_SAMPLE_RATE,
                "channels": config.AUDIO_CHANNELS,
                "sample_width": config.AUDIO_SAMPLE_WIDTH,
                "size": total_len,
            })
            results = await asyncio.gather(*[ws.send(start_msg) for ws in valid_targets], return_exceptions=True)
            dead = [ws for ws, res in zip(valid_targets, results) if isinstance(res, Exception)]
            if dead:
                for d in dead:
                    self._active_speakers.discard(d)
                valid_targets = [ws for ws in valid_targets if ws not in dead]
                if not valid_targets:
                    return

            # Chờ ESP32 parse JSON audio_start và chuyển state sang PLAYING
            await asyncio.sleep(0.030)

            # Send binary PCM chunks with robust playback pacing
            chunks_sent = 0
            bytes_per_sec = config.AUDIO_SAMPLE_RATE * config.AUDIO_SAMPLE_WIDTH  # 32,000 bytes/sec
            for i in range(0, total_len, chunk_size):
                chunk = pcm_bytes[i:i + chunk_size]
                results = await asyncio.gather(*[ws.send(chunk) for ws in valid_targets], return_exceptions=True)
                dead = [ws for ws, res in zip(valid_targets, results) if isinstance(res, Exception)]
                if dead:
                    for d in dead:
                        self._active_speakers.discard(d)
                    valid_targets = [ws for ws in valid_targets if ws not in dead]
                    if not valid_targets:
                        logger.warning("All target speaker websockets disconnected during streaming")
                        break

                chunks_sent += 1
                # Pre-buffer first 16 chunks (~32KB = 1s audio) with 2ms spacing to let ESP32
                # accumulate enough data before amp enables (it waits for ≥4KB).
                # After pre-buffer, pace at 80% real-time (~51ms per 2KB chunk) to maintain
                # steady flow without underflow or overflow on ESP32's 512KB PSRAM buffer.
                if chunks_sent <= 16:
                    await asyncio.sleep(0.002)
                else:
                    chunk_duration = len(chunk) / bytes_per_sec
                    await asyncio.sleep(chunk_duration * 0.80)

            # Send end marker: only initiator_ws gets follow_up=True, others get follow_up=False
            tasks = []
            for ws in valid_targets:
                ws_follow_up = follow_up if (ws == initiator_ws or initiator_ws is None) else False
                end_msg = json.dumps({
                    "type": "audio_end",
                    "follow_up": ws_follow_up,
                    "timeout_ms": 6000 if ws_follow_up else 0
                })
                tasks.append(ws.send(end_msg))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            logger.info(
                f"✅ Streamed {total_len} bytes in {chunks_sent} chunks to {len(valid_targets)} ESP32(s)"
            )
            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("audio_state", {"state": "IDLE"})

            # Mở lại mic cho toàn bộ các node sau khi loa phát xong
            free_msg = json.dumps({"type": "speaker_busy", "busy": False})
            all_ws = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
            if all_ws:
                await asyncio.gather(*[ws.send(free_msg) for ws in all_ws], return_exceptions=True)

    async def _send_audio_stream_mp3(self, websocket, audio_bytes: bytes, follow_up: bool = False):
        """
        Fallback: Stream MP3 audio data back to ESP32.
        ESP32 would need an MP3 decoder for this path.
        """
        if not getattr(websocket, "has_speaker", True) or getattr(websocket, "audio_relay", False):
            return
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
        await websocket.send(json.dumps({
            "type": "audio_end",
            "follow_up": follow_up,
            "timeout_ms": 6000 if follow_up else 0
        }))
        logger.info(f"Streamed {total_len} bytes MP3 to ESP32 (fallback)")
