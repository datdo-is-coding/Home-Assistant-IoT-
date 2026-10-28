"""
Audio Server — WebSocket server for ESP32 voice streaming.
Receives PCM audio from ESP32-S3, runs Sherpa-ONNX ASR,
dispatches commands via Gateway, and streams TTS PCM response
back to ESP32 speaker.

Protocol (ESP32 → Pi):
  TEXT:   {"type":"start","codec":"pcm","sample_rate":16000}
  BINARY: [PCM 16kHz/16bit/mono; SubBox batches 960 bytes / 30ms, final chunk may be shorter]
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
import collections
import contextlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Optional, Tuple, Any
try:
    import websockets
except ImportError:
    websockets = None

try:
    import numpy as np
except ImportError:
    import array
    import math

    class _DummyArray(list):
        def astype(self, dtype):
            return self

        def __truediv__(self, other):
            return _DummyArray([x / other for x in self])

        def __rtruediv__(self, other):
            return _DummyArray([other / x for x in self])

    class _DummyNP:
        ndarray = Any
        int16 = "h"
        float32 = "f"

        def frombuffer(self, b, dtype=None):
            arr = array.array("h")
            arr.frombytes(b)
            return _DummyArray(arr)

        def square(self, arr):
            return [x * x for x in arr]

        def mean(self, arr):
            return sum(arr) / len(arr) if arr else 0.0

        def sqrt(self, val):
            return math.sqrt(val)

        def concatenate(self, chunks):
            res = _DummyArray()
            for c in chunks:
                res.extend(c)
            return res

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

    NEAR_FIELD_RMS_THRESHOLD = 600.0

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.active_streams: dict = {}

    def register_start(self, node_id: str):
        now = time.monotonic()
        prune_window = max(getattr(config, "VAD_MAX_DURATION_S", 10.0) + 2.0, 12.0)
        self.active_streams = {nid: d for nid, d in self.active_streams.items() if (now - d["start_time"]) < prune_window}
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

        now = time.monotonic()
        prune_window = max(getattr(config, "VAD_MAX_DURATION_S", 10.0) + 2.0, 12.0)
        self.active_streams = {nid: d for nid, d in self.active_streams.items() if (now - d["start_time"]) < prune_window}
        active_window = getattr(config, "VAD_MAX_DURATION_S", 10.0)
        candidates = {}
        for nid, data in self.active_streams.items():
            if (now - data["start_time"]) <= active_window and data["rms_values"]:
                top_rms = sorted(data["rms_values"], reverse=True)[:10]
                avg_top = sum(top_rms) / len(top_rms) if top_rms else 0
                candidates[nid] = avg_top

        if not candidates or current_node_id not in candidates:
            return current_node_id, self._get_room(current_node_id)

        current_room = self._get_room(current_node_id)
        curr_rms = candidates.get(current_node_id, 0.0)

        # Intra-room suppression: Check if other candidates in the SAME room have higher RMS
        same_room_cands = {
            nid: rms for nid, rms in candidates.items()
            if current_room is not None and self._get_room(nid) == current_room and nid != current_node_id
        }
        if same_room_cands and max(same_room_cands.values()) > curr_rms:
            dominant_same = max(same_room_cands, key=same_room_cands.get)
            logger.info(
                f"🔇 Spatial Arbiter: Suppressed weaker intra-room node '{current_node_id}' "
                f"in favor of '{dominant_same}' ({current_room})"
            )
            return dominant_same, current_room

        # Cross-room sound leakage suppression
        other_room_cands = {
            nid: rms for nid, rms in candidates.items()
            if self._get_room(nid) != current_room
        }
        if curr_rms < self.NEAR_FIELD_RMS_THRESHOLD and other_room_cands and max(other_room_cands.values()) > curr_rms * 2.5:
            loudest_nid = max(candidates, key=candidates.get)
            loudest_room = self._get_room(loudest_nid)
            logger.info(
                f"🔇 Spatial Arbiter: Suppressed acoustic room leak '{current_node_id}' ({curr_rms:.0f}) "
                f"in favor of louder room '{loudest_nid}' ({loudest_room})"
            )
            return loudest_nid, loudest_room

        return current_node_id, current_room

    def _get_room(self, node_id: str) -> Optional[str]:
        if self.gateway and hasattr(self.gateway, "registry") and self.gateway.registry:
            nodes = self.gateway.registry.get_all_nodes()
            if isinstance(nodes, dict):
                node_info = nodes.get(node_id)
                if isinstance(node_info, dict):
                    room = node_info.get("room")
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

        self._ws_nodes: dict = {}

        self._active_speakers: set = set()
        self._playback_receipts = {}
        self._playback_locks: dict = collections.defaultdict(asyncio.Lock)
        self._default_playback_lock = asyncio.Lock()

        self._asr_lock = asyncio.Lock()
        self._followup_pending = {}
        self._active_voice_sessions: dict = {}
        self.arbiter = StreamArbiter(gateway=self.gateway)

    @property
    def _active_voice_session(self) -> Optional[dict]:
        if not self._active_voice_sessions:
            return None
        latest = max(self._active_voice_sessions.values(), key=lambda s: s.get("timestamp", 0), default=None)
        if latest and (time.monotonic() - latest.get("timestamp", 0)) < 3.5:
            return latest
        return None

    @_active_voice_session.setter
    def _active_voice_session(self, val: Optional[dict]):
        if not val:
            self._active_voice_sessions.clear()
        elif isinstance(val, dict):
            room = val.get("room") or val.get("detected_room")
            if not room and "node_id" in val:
                room = self.arbiter._get_room(val["node_id"]) or val["node_id"]
            room = room or "default"
            self._active_voice_sessions[room] = val

    @property
    def _playback_lock(self) -> asyncio.Lock:
        return self._default_playback_lock

    def _is_ws_alive(self, ws) -> bool:
        """Kiểm tra websocket còn sống không (tương thích mọi version websockets)."""
        if ws is None:
            return False
        try:

            if hasattr(ws, 'open'):
                return bool(ws.open)
            if hasattr(ws, 'closed'):
                return not bool(ws.closed)
            return True
        except Exception:
            return False

    def _extract_token(self, websocket, path=None) -> Optional[str]:
        """Extract Bearer token from headers or query parameters."""
        headers = None
        if hasattr(websocket, "request_headers"):
            headers = websocket.request_headers
        elif hasattr(websocket, "request") and hasattr(websocket.request, "headers"):
            headers = websocket.request.headers
        elif hasattr(websocket, "headers"):
            headers = websocket.headers

        if headers:
            auth_header = headers.get("Authorization") or headers.get("authorization")
            if auth_header:
                parts = auth_header.strip().split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]
                elif len(parts) == 1:
                    return parts[0]
            token_h = headers.get("X-API-Token") or headers.get("token") or headers.get("Token")
            if token_h:
                return token_h.strip()

        q_path = path or getattr(websocket, "path", "")
        if not q_path and hasattr(websocket, "request"):
            q_path = getattr(websocket.request, "path", "")
        if q_path and "?" in q_path:
            import urllib.parse
            qs = urllib.parse.parse_qs(q_path.split("?", 1)[1])
            token_val = qs.get("token") or qs.get("access_token")
            if token_val:
                return token_val[0]

        return None

    def _core_speaker(self, node_id):
        if not isinstance(node_id, str) or not re.fullmatch(r'SB[0-9A-F]{12}', node_id):
            return None
        core = getattr(getattr(self.gateway, 'firebase_commissioning', None), 'core', None)
        if core is None:
            return None
        try:
            row = core.r.one("SELECT n.* FROM registered_nodes n JOIN factory_devices f USING(factory_id) "
                             "WHERE n.factory_id=? AND f.product_type='SUB_BOX'", ('HC-'+node_id[2:],))
        except Exception as exc:
            if getattr(exc, 'code', None) == 'not_found':
                return None
            logger.error('Core speaker registry unavailable')
            return {'token':None}
        row['token'] = None
        if row['registration'] == 'REGISTERED' and row['home_id'] == core.home:
            try:
                row['token'] = hmac.digest(core.r.node_key(row['node_id']), b'HC-SPEAKER-V1\0', 'sha256').hex()
            except Exception:
                pass
        return row

    def _is_token_valid(self, token: Optional[str], node_id: Optional[str] = None) -> bool:
        """Kiểm tra token có khớp với WS_AUDIO_TOKEN hoặc WS_AUDIO_TOKENS."""
        if not token:
            return False
        core = self._core_speaker(node_id)
        if core is not None:
            return bool(core['token'] and hmac.compare_digest(core['token'], token))

        global_tok = getattr(config, "WS_AUDIO_TOKEN", "")
        if global_tok and token == global_tok:
            return True

        tokens = getattr(config, "WS_AUDIO_TOKENS", {})
        if isinstance(tokens, dict):
            if node_id and tokens.get(node_id) == token:
                return True
            if token in tokens:
                bound_id = tokens[token]
                if not node_id or bound_id == node_id:
                    return True
            if not node_id and token in tokens.values():
                return True
            if node_id and token in tokens.values():
                for nid, tok in tokens.items():
                    if tok == token and nid == node_id:
                        return True
        elif isinstance(tokens, (list, set, tuple)):
            if token in tokens:
                return True

        return False

    def _check_owner_epoch(self, node_id: str, payload_epoch: Any, bound_epoch: Optional[int] = None) -> bool:
        """Kiểm tra owner_epoch chống replay/stale/stripped epoch.
        Trả về False và ghi log cảnh báo nếu epoch nhận được nhỏ hơn epoch hiện tại của node trong registry,
        hoặc nếu node đã có epoch > 0 mà payload không chứa epoch."""
        reg_epoch = 0
        if self.gateway and hasattr(self.gateway, "registry") and self.gateway.registry:
            actual_nid = node_id
            if hasattr(self.gateway.registry, "find_node_by_mac") and (":" in str(node_id) or len(str(node_id)) == 12):
                mapped_id = self.gateway.registry.find_node_by_mac(str(node_id))
                if mapped_id:
                    actual_nid = mapped_id
            if hasattr(self.gateway.registry, "get_node_owner_epoch"):
                reg_epoch = self.gateway.registry.get_node_owner_epoch(actual_nid)
            elif hasattr(self.gateway.registry, "get_all_nodes"):
                node_info = self.gateway.registry.get_all_nodes().get(actual_nid, {})
                reg_epoch = int(node_info.get("owner_epoch", node_info.get("epoch", 0)))

        min_valid_epoch = max(reg_epoch, bound_epoch or 0)
        if payload_epoch is None:
            if min_valid_epoch > 0:
                logger.warning(
                    f"Rejected packet missing owner_epoch (epoch stripped) for node '{node_id}' "
                    f"(expected epoch >= {min_valid_epoch})"
                )
                return False
            return True

        try:
            p_epoch = int(payload_epoch)
        except (ValueError, TypeError):
            logger.warning(f"Invalid owner_epoch format '{payload_epoch}' from node '{node_id}'")
            return False

        if min_valid_epoch > 0 and p_epoch < min_valid_epoch:
            logger.warning(
                f"Rejected packet with stale/replay owner_epoch {p_epoch} < {min_valid_epoch} "
                f"for node '{node_id}'"
            )
            return False
        return True

    async def start(self):
        """Start the WebSocket server."""
        self._running = True
        logger.info(f"Starting Audio WebSocket server on {self.host}:{self.port}")

        ssl_context = None
        cert_file = getattr(config, "WS_AUDIO_TLS_CERT", "")
        key_file = getattr(config, "WS_AUDIO_TLS_KEY", "")
        if cert_file or key_file:
            import os, ssl
            if not cert_file or not key_file or not os.path.isfile(cert_file) or not os.path.isfile(key_file):
                raise ValueError('Audio TLS certificate/key missing')
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
            logger.info("Enabled TLS for Audio WebSocket server")

        serve_kwargs = {
            "ping_interval": 20,
            "ping_timeout": 30,
            "max_size": 10 * 1024 * 1024
        }
        if ssl_context:
            serve_kwargs["ssl"] = ssl_context

        self.server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            **serve_kwargs
        )
        logger.info("Audio WebSocket server running and ready for ESP32 connections")

    def _relay_source_epoch(self, parent_id: str, source_id: str) -> Optional[int]:
        registry = getattr(self.gateway, "registry", None)
        if not registry or not isinstance(source_id, str):
            return None
        nodes = registry.get_all_nodes()
        source = nodes.get(source_id, {})
        pending = registry.get_pending() if hasattr(registry, "get_pending") else {}
        if (parent_id not in nodes or source.get("subbox_id") != parent_id
                or source.get("status") != "online" or source_id in pending):
            return None
        return int(source.get("owner_epoch", source.get("epoch", 0)))

    async def stop(self):
        """Stop the server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Audio WebSocket server stopped")

    async def _handle_client(self, websocket, path=None):
        """Handle an active ESP32 WebSocket connection."""
        client_addr = getattr(websocket, "remote_address", "unknown")
        logger.info(f"🔗 ESP32 client connected from {client_addr}")

        auth_required = bool(
            getattr(config, "WS_AUDIO_TOKEN", "")
            or getattr(config, "WS_AUDIO_TOKENS", {})
            or getattr(config, "WS_AUDIO_AUTH_REQUIRED", False)
        )
        extracted_token = self._extract_token(websocket, path)
        request_headers = getattr(websocket, 'request_headers', None)
        if request_headers is None:
            request_headers = getattr(getattr(websocket, 'request', None), 'headers', {})
        header_node = request_headers.get('X-Device-ID') if request_headers else None
        core_speaker = self._core_speaker(header_node)
        is_authenticated = False
        authenticated_token = None

        if core_speaker is not None:
            transport = getattr(websocket, 'transport', None)
            if (not transport or not transport.get_extra_info('ssl_object') or
                    not self._is_token_valid(extracted_token, header_node)):
                await websocket.close(1008, 'Core speaker authentication required')
                return
            is_authenticated = True
            authenticated_token = extracted_token
            auth_required = True
        elif not auth_required:
            is_authenticated = True
        elif extracted_token and self._is_token_valid(extracted_token):
            is_authenticated = True
            authenticated_token = extracted_token

        client_node_id = None
        client_owner_epoch = None
        stream_source_id = None
        relay_source_epoch = None
        websocket.has_speaker = True
        websocket.authenticated = is_authenticated
        websocket.client_node_id = None
        websocket.owner_epoch = None
        websocket.playback_only = core_speaker is not None
        websocket.requires_playback_ack = core_speaker is not None

        codec = "pcm"
        sample_rate = config.AUDIO_SAMPLE_RATE
        pcm_chunks = []
        decoder = None
        recording = False
        record_start_time = 0.0
        total_frames = 0
        client_mac = None
        installed = {}

        async def _bind_client_node(target_node_id: str, owner_epoch: Optional[int] = None) -> bool:
            nonlocal client_node_id, client_owner_epoch
            if not target_node_id:
                return False
            if core_speaker is None and self._core_speaker(target_node_id) is not None:
                await websocket.close(1008, 'Core speaker identity cannot use legacy registration')
                return False
            if client_node_id and client_node_id != target_node_id:
                logger.warning(f"Socket already bound to '{client_node_id}', cannot re-bind to '{target_node_id}' from {client_addr}")
                return False

            old_ws = self._ws_nodes.get(target_node_id)
            if old_ws and old_ws is not websocket and self._is_ws_alive(old_ws):
                logger.warning(f"Closing existing active connection for node '{target_node_id}' due to new connection from {client_addr}")
                self._active_speakers.discard(old_ws)
                try:
                    if hasattr(old_ws, "close"):
                        await old_ws.close(1000, "Superseded by new connection")
                except Exception:
                    pass

            client_node_id = target_node_id
            if owner_epoch is not None:
                client_owner_epoch = owner_epoch
            self._ws_nodes[target_node_id] = websocket
            websocket.node_id = target_node_id
            websocket.client_node_id = target_node_id
            websocket.owner_epoch = client_owner_epoch
            return True

        try:
            async for message in websocket:
                if isinstance(message, str):

                    try:
                        cmd = json.loads(message)
                        msg_type = cmd.get("type", "")

                        compact_type = cmd.get("t")

                        if core_speaker is None:
                            claimed = cmd.get('id') or cmd.get('node_id') or cmd.get('device_id')
                            mac = str(cmd.get('mac', '')).replace(':', '').upper()
                            if self._core_speaker(claimed) is not None or (re.fullmatch(r'[0-9A-F]{12}', mac) and self._core_speaker('SB'+mac) is not None):
                                await websocket.close(1008, 'Core speaker must use authenticated WSS identity')
                                return

                        if core_speaker is not None:
                            if not self._is_token_valid(authenticated_token, header_node):
                                await websocket.close(1008, 'Core speaker revoked')
                                return
                            if compact_type == 'hello':
                                if cmd.get('id') != header_node or cmd.get('speaker') is not True or cmd.get('playback_only') is not True:
                                    await websocket.close(1008, 'Core speaker identity mismatch')
                                    return
                                if not await _bind_client_node(header_node):
                                    return
                                self._active_speakers.add(websocket)
                                logger.info('Core playback speaker registered: %s', header_node)
                                await websocket.send(json.dumps({'t':'hello_ok','id':header_node}))
                            elif msg_type == 'playback_complete' and client_node_id:
                                pending = self._playback_receipts.get(cmd.get('playback_id'))
                                if pending and pending[0] is websocket and not pending[1].done():
                                    complete = (cmd.get('success') is True and
                                                type(cmd.get('received_bytes')) is int and
                                                cmd['received_bytes'] == pending[2])
                                    if not complete:
                                        logger.warning('Speaker playback incomplete: %s, received=%r expected=%d, output_ok=%r',
                                                       header_node, cmd.get('received_bytes'), pending[2], cmd.get('success'))
                                    pending[1].set_result(complete)
                            else:
                                logger.debug('Ignoring non-playback message from Core speaker')
                            continue

                        if compact_type == "hello":
                            hello_token = cmd.get("token") or cmd.get("auth_token")
                            hello_id = cmd.get("id")

                            if auth_required and not is_authenticated:
                                if hello_token and self._is_token_valid(hello_token, node_id=hello_id):
                                    is_authenticated = True
                                    authenticated_token = hello_token
                                    websocket.authenticated = True
                                else:
                                    logger.warning(f"Unauthorized hello from {client_addr}: token missing or invalid")
                                    await websocket.send(json.dumps({"t": "error", "error": "unauthorized"}))
                                    if hasattr(websocket, "close"):
                                        await websocket.close(1008, "Unauthorized")
                                    return

                            if auth_required and is_authenticated and hello_id and authenticated_token:
                                if not self._is_token_valid(authenticated_token, node_id=hello_id):
                                    logger.warning(f"Token forbidden for node '{hello_id}' from {client_addr}")
                                    await websocket.send(json.dumps({"t": "error", "error": "forbidden"}))
                                    if hasattr(websocket, "close"):
                                        await websocket.close(1008, "Forbidden")
                                    return

                            hello_epoch = cmd.get("owner_epoch", cmd.get("epoch"))
                            target_id_for_check = hello_id or (cmd.get("mac") or "").upper()
                            if target_id_for_check:
                                if not self._check_owner_epoch(target_id_for_check, hello_epoch):
                                    logger.warning(f"Rejected hello with stale/replay/missing owner_epoch {hello_epoch} from {client_addr}")
                                    await websocket.send(json.dumps({"t": "error", "error": "stale_epoch"}))
                                    if hasattr(websocket, "close"):
                                        await websocket.close(1008, "Stale epoch")
                                    return

                            client_mac = (cmd.get("mac") or "").upper()
                            handled = None
                            if self.gateway and hasattr(self.gateway, "registry"):
                                handled = self.gateway.registry.on_hello(cmd, ws_available=True)
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("node_hello", cmd)
                            node_id = handled.get("node_id") if handled else None
                            if not node_id and hello_id:
                                node_id = hello_id

                            if node_id:
                                bound_ok = await _bind_client_node(
                                    node_id,
                                    owner_epoch=int(hello_epoch) if hello_epoch is not None else None
                                )
                                if not bound_ok:
                                    logger.warning(f"Failed to bind node identity '{node_id}' from {client_addr}")
                                    await websocket.send(json.dumps({"t": "error", "error": "conflict"}))
                                    if hasattr(websocket, "close"):
                                        await websocket.close(1008, "Identity conflict")
                                    return
                                is_subbox = "subbox" in str(node_id).lower() or str(node_id).upper().startswith("SB") or (cmd.get("audio_relay") is True and cmd.get("speaker") is not False)
                                if is_subbox:
                                    websocket.is_subbox = True
                                    websocket.has_speaker = True
                                is_spk = getattr(websocket, "has_speaker", False) or cmd.get("speaker") is True or ("actionbox" not in str(node_id).lower() and not str(node_id).upper().startswith("AB") and cmd.get("speaker") is not False)
                                websocket.has_speaker = is_spk
                                websocket.node_id = node_id
                                websocket.asr_only = cmd.get("asr_only") is True
                                websocket.audio_relay = cmd.get("audio_relay") is True
                                websocket.local_kws = cmd.get("local_kws") is True
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

                                if self.gateway and hasattr(self.gateway, "mqtt"):
                                    cfg = self.gateway.registry.get_provision_payload(node_id)
                                    if cfg and hasattr(self.gateway.mqtt, "send_cfg"):
                                        res = self.gateway.mqtt.send_cfg(node_id, cfg)
                                        if asyncio.iscoroutine(res):
                                            await res
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("pending_node", {"mac": client_mac, "hello": cmd})
                                await websocket.send(json.dumps({"t": "cfg_sent", "id": node_id}))
                            elif handled and handled.get("action") == "pending":
                                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                    self.gateway.broadcast_event("pending_node", {"mac": client_mac, "hello": cmd})
                                await websocket.send(json.dumps({"t": "pending", "mac": client_mac}))
                            else:
                                logger.warning(f"hello_ignored: {cmd}")
                            continue

                        elif compact_type == "ack":
                            if not is_authenticated:
                                logger.warning(f"Rejected ACK from unauthenticated socket {client_addr}")
                                continue
                            nid = cmd.get("id")
                            if not client_node_id or nid != client_node_id:
                                logger.warning(f"Rejected spoofed ACK: socket node_id='{client_node_id}', payload id='{nid}' from {client_addr}")
                                continue
                            ep = cmd.get("owner_epoch", cmd.get("epoch"))
                            if not self._check_owner_epoch(client_node_id, ep, client_owner_epoch):
                                logger.warning(f"Rejected ACK with stale/replay/missing owner_epoch {ep} for node '{client_node_id}' from {client_addr}")
                                continue
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
                                         "ch2": rl[1] if len(rl)>1 else None,
                                         "ch3": rl[2] if len(rl)>2 else None})
                                logger.info(f"ACK {nid} rl={rl} seq={cmd.get('seq')}")
                            continue

                        elif compact_type == "need_cfg":
                            if not is_authenticated:
                                logger.warning(f"Rejected need_cfg from unauthenticated socket {client_addr}")
                                continue
                            req_nid = cmd.get("id")
                            if req_nid and client_node_id and req_nid != client_node_id:
                                logger.warning(f"Rejected need_cfg with mismatched node_id '{req_nid}' (socket bound to '{client_node_id}') from {client_addr}")
                                continue
                            ep = cmd.get("owner_epoch", cmd.get("epoch"))
                            target_check = client_node_id or req_nid
                            if target_check and not self._check_owner_epoch(target_check, ep, client_owner_epoch):
                                logger.warning(f"Rejected need_cfg with stale/replay/missing owner_epoch {ep} from {client_addr}")
                                continue
                            mac = (cmd.get("mac") or "").upper()

                            found = None
                            if self.gateway:
                                nid = self.gateway.registry.find_node_by_mac(mac) if hasattr(self.gateway.registry, "find_node_by_mac") else None
                                if nid:
                                    cfg = self.gateway.registry.get_provision_payload(nid)
                                    if self.gateway.mqtt and hasattr(self.gateway.mqtt, "send_cfg"):
                                        res = self.gateway.mqtt.send_cfg(nid, cfg)
                                        if asyncio.iscoroutine(res):
                                            await res
                                        found = True
                            if not found:
                                await websocket.send(json.dumps({"t": "pending", "mac": mac}))
                            continue

                        if msg_type == "start":
                            if getattr(self.gateway, "local_kws_enabled", False) or getattr(websocket, "local_kws", False):
                                await websocket.send(json.dumps({"type": "error", "error": "local_kws_only"}))
                                continue
                            if not is_authenticated:
                                logger.warning(f"Rejected start from unauthenticated socket {client_addr}")
                                await websocket.send(json.dumps({"type": "error", "error": "unauthorized"}))
                                continue

                            start_nid = cmd.get("node_id")
                            source_epoch = None
                            if client_node_id and start_nid and start_nid != client_node_id:
                                if getattr(websocket, "is_subbox", False) and cmd.get("audio_relay") is True:
                                    source_epoch = self._relay_source_epoch(client_node_id, start_nid)
                                if source_epoch is None:
                                    logger.warning(f"Rejected unregistered relay source '{start_nid}' from '{client_node_id}'")
                                    await websocket.send(json.dumps({"type": "error", "error": "forbidden"}))
                                    continue
                            if not client_node_id and start_nid:
                                bound_ok = await _bind_client_node(start_nid)
                                if not bound_ok:
                                    await websocket.send(json.dumps({"type": "error", "error": "conflict"}))
                                    continue
                            if not client_node_id:
                                logger.warning(f"Rejected start from unbound socket {client_addr}")
                                await websocket.send(json.dumps({"type": "error", "error": "identity_required"}))
                                continue

                            ep = cmd.get("owner_epoch", cmd.get("epoch"))
                            if not self._check_owner_epoch(client_node_id, ep, client_owner_epoch):
                                logger.warning(f"Rejected start with stale/replay/missing owner_epoch {ep} for node '{client_node_id}' from {client_addr}")
                                await websocket.send(json.dumps({"type": "error", "error": "stale_epoch"}))
                                continue

                            websocket.asr_only = cmd.get("asr_only") is True
                            websocket.audio_relay = cmd.get("audio_relay") is True
                            client_room = self.arbiter._get_room(client_node_id) if client_node_id else None
                            room_playback_lock = self._playback_locks[client_room] if client_room else self._default_playback_lock
                            if room_playback_lock.locked() or (client_room and self._default_playback_lock.locked()):
                                curr_node = client_node_id or "node_voice"
                                logger.info(f"🔇 Rejecting mic stream from '{curr_node}': speaker is actively playing TTS audio")
                                await websocket.send(json.dumps({
                                    "type": "suppressed", "reason": "speaker_busy"
                                }))
                                continue

                            codec = cmd.get("codec", "pcm")
                            sample_rate = cmd.get("sample_rate", config.AUDIO_SAMPLE_RATE)
                            stream_source_id = start_nid or client_node_id
                            relay_source_epoch = source_epoch
                            pcm_chunks.clear()
                            recording = True
                            record_start_time = time.monotonic()
                            total_frames = 0
                            curr_node = stream_source_id or client_node_id or "node_voice"
                            self._ws_nodes[curr_node] = websocket
                            if not getattr(websocket, "is_subbox", False):
                                websocket.node_id = curr_node
                            is_dedicated_mic = (
                                "actionbox" in str(curr_node).lower()
                                or str(curr_node).upper().startswith("AB")
                            )
                            if is_dedicated_mic:
                                websocket.current_source = curr_node
                                if not getattr(websocket, "is_subbox", False):
                                    websocket.has_speaker = False
                                    self._active_speakers.discard(websocket)
                                else:
                                    websocket.has_speaker = True
                                    self._active_speakers.add(websocket)
                            elif cmd.get("speaker") is True or getattr(websocket, "has_speaker", False):
                                websocket.has_speaker = True
                                self._active_speakers.add(websocket)
                            elif cmd.get("speaker") is False:
                                websocket.has_speaker = False
                                self._active_speakers.discard(websocket)
                            elif getattr(websocket, "has_speaker", True):
                                self._active_speakers.add(websocket)
                            self.arbiter.register_start(curr_node)

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
                            self.arbiter.active_streams.pop(stream_source_id or client_node_id, None)
                            await websocket.send(json.dumps({"type": "status", "state": "cancelled"}))

                        elif msg_type == "stop":
                            if not recording:
                                continue
                            recording = False
                            now_ts = time.monotonic()
                            elapsed = now_ts - record_start_time
                            curr_node = stream_source_id or client_node_id or "node_voice"
                            if relay_source_epoch is not None and self._relay_source_epoch(client_node_id, curr_node) != relay_source_epoch:
                                pcm_chunks.clear()
                                await websocket.send(json.dumps({"type": "error", "error": "forbidden"}))
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

                            curr_room = detected_room or self.arbiter._get_room(curr_node) or curr_node
                            active_session = self._active_voice_sessions.get(curr_room)
                            if active_session and (now_ts - active_session.get("timestamp", 0)) < 3.5:
                                active_nid = active_session.get("node_id")
                                if active_nid and active_nid != curr_node:
                                    logger.info(f"🔇 Spatial Arbiter: Suppressed concurrent stream from '{curr_node}' (active session already on '{active_nid}' in {curr_room})")
                                    await websocket.send(json.dumps({
                                        "type": "suppressed",
                                        "dominant_node": active_nid,
                                        "detected_room": curr_room
                                    }))
                                    pcm_chunks.clear()
                                    continue

                            self._active_voice_sessions[curr_room] = {"node_id": curr_node, "timestamp": now_ts}

                            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                self.gateway.broadcast_event("audio_state", {"state": "PROCESSING"})
                            await websocket.send(json.dumps({
                                "type": "status", "state": "processing"
                            }))

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

                elif isinstance(message, bytes):
                    if not is_authenticated or not client_node_id or not recording:
                        logger.warning(
                            f"Rejected binary audio frame from unauthenticated/unbound/non-recording socket {client_addr} "
                            f"(auth={is_authenticated}, bound={client_node_id}, rec={recording})"
                        )
                        continue

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

                        raw_i16 = np.frombuffer(message, dtype=np.int16)
                        pcm_float = raw_i16.astype(np.float32) / 32768.0
                        pcm_chunks.append(pcm_float)

                        if len(raw_i16) > 0:
                            rms = int(np.sqrt(np.mean(np.square(raw_i16.astype(np.float32)))))
                            curr_node = stream_source_id or client_node_id or "node_voice"
                            self.arbiter.add_rms(curr_node, rms)
                            if self.gateway and hasattr(self.gateway, "broadcast_event") and total_frames % 2 == 0:
                                self.gateway.broadcast_event("audio_meter", {"rms": rms, "frames": total_frames})

                    elapsed = time.monotonic() - record_start_time
                    if elapsed > config.VAD_MAX_DURATION_S:
                        logger.info(
                            f"Max recording duration ({config.VAD_MAX_DURATION_S}s) "
                            f"reached — auto-stopping"
                        )
                        recording = False
                        if pcm_chunks:
                            full_pcm = np.concatenate(pcm_chunks)
                            curr_node = stream_source_id or client_node_id or "node_voice"
                            if relay_source_epoch is not None and self._relay_source_epoch(client_node_id, curr_node) != relay_source_epoch:
                                pcm_chunks.clear()
                                await websocket.send(json.dumps({"type": "error", "error": "forbidden"}))
                                continue

                            dominant_nid, detected_room = self.arbiter.determine_dominant_room(curr_node)
                            if dominant_nid and dominant_nid != curr_node:
                                logger.info(f"🔇 Spatial Arbiter: Suppressed weaker stream '{curr_node}' in favor of dominant '{dominant_nid}' ({detected_room})")
                                await websocket.send(json.dumps({
                                    "type": "suppressed",
                                    "dominant_node": dominant_nid,
                                    "detected_room": detected_room
                                }))
                                pcm_chunks.clear()
                                continue

                            now_ts = time.monotonic()
                            curr_room = detected_room or self.arbiter._get_room(curr_node) or curr_node
                            active_session = self._active_voice_sessions.get(curr_room)
                            if active_session and (now_ts - active_session.get("timestamp", 0)) < 3.5:
                                active_nid = active_session.get("node_id")
                                if active_nid and active_nid != curr_node:
                                    logger.info(f"🔇 Spatial Arbiter: Suppressed concurrent stream from '{curr_node}' (active session already on '{active_nid}' in {curr_room})")
                                    await websocket.send(json.dumps({
                                        "type": "suppressed",
                                        "dominant_node": active_nid,
                                        "detected_room": curr_room
                                    }))
                                    pcm_chunks.clear()
                                    continue

                            self._active_voice_sessions[curr_room] = {"node_id": curr_node, "timestamp": now_ts}

                            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                                self.gateway.broadcast_event("audio_state", {"state": "PROCESSING"})
                            await websocket.send(json.dumps({
                                "type": "status", "state": "processing"
                            }))
                            await self._process_audio(
                                websocket, full_pcm, sample_rate,
                                client_node_id=curr_node,
                                detected_room=detected_room
                            )
                        pcm_chunks.clear()

        except Exception as e:
            if websockets and hasattr(websockets, "exceptions") and isinstance(e, getattr(websockets.exceptions, "ConnectionClosed", ())):
                logger.info(f"ESP32 client disconnected: {client_addr} (code={getattr(e, 'code', None)}, reason='{getattr(e, 'reason', '')}')")
            else:
                logger.error(f"Error handling WebSocket client {client_addr}: {e}")
            self._active_speakers.discard(websocket)
            for nid, ws in list(self._ws_nodes.items()):
                if ws is websocket:
                    del self._ws_nodes[nid]
            self._active_speakers = {ws for ws in self._active_speakers if self._is_ws_alive(ws)}
            logger.info(f"WS node still connected: {list(self._ws_nodes.keys())}, active speakers: {len(self._active_speakers)}")

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
        is_bcast = not node_id or str(node_id).lower() in ("all", "broadcast", "*", "broadcast_mac", "ff:ff:ff:ff:ff:ff")
        if is_bcast and not getattr(config, "ALLOW_BROADCAST_COMMANDS", False):
            logger.warning(f"Refusing to send relay control command to broadcast/all ({node_id}) via WebSocket")
            return False
        ws = self._ws_nodes.get(node_id)
        if getattr(ws, 'playback_only', False):
            return False
        if not self.has_ws(node_id):
            return False
        ch = {"ch1": 1, "ch2": 2, "ch3": 3, 1: 1, 2: 2, 3: 3}.get(channel, 0)
        if ch not in (1, 2, 3):
            return False
        s = 1 if action in ("turn_on", "open", "on") else 0
        payload = json.dumps({"t": "rl", "ch": ch, "s": s, "seq": seq})
        try:
            await ws.send(payload)
            logger.info(f"⚡ WS relay {node_id} ch{ch}={s} seq={seq} (~{len(payload)}B)")
            return True
        except Exception as e:
            logger.warning(f"WS relay to {node_id} failed: {e}")

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
        if getattr(self.gateway, "local_kws_enabled", False) or not getattr(self.gateway, "asr", None):
            logger.warning("Rejected obsolete microphone/ASR uplink; SubBox owns local KWS")
            await websocket.send(json.dumps({
                "type": "transcript", "text": "", "accepted": False, "reason": "local_kws"
            }))
            return

        followup_deadline = self._followup_pending.pop(client_node_id, 0)
        was_followup = followup_deadline > time.monotonic()
        duration_s = len(pcm_samples) / sample_rate
        logger.info(
            f"📊 Processing speech: {len(pcm_samples)} samples ({duration_s:.2f}s) "
            f"from {client_node_id} (detected_room={detected_room})"
        )

        try:
            async with asyncio.timeout(5.0):
                async with self._asr_lock:
                    inference = asyncio.create_task(asyncio.to_thread(
                        self.gateway.asr.transcribe_with_confidence, pcm_samples, sample_rate))
                    try:
                        text, confidence = await asyncio.shield(inference)
                    except asyncio.CancelledError:
                        await inference
                        raise
        except (TimeoutError, asyncio.TimeoutError):
            await websocket.send(json.dumps({"type": "transcript", "text": "", "accepted": False,
                                             "reason": "asr_busy"}))
            return

        if was_followup and not text:
            dialog = getattr(self.gateway, "dialog", None)
            if dialog:
                dialog.clear_session(client_node_id)
            await websocket.send(json.dumps({"type": "transcript", "text": "", "accepted": False}))
            return

        if not text:
            logger.warning("ASR returned empty transcript")
            reply = "Em không nghe rõ. Bạn nói lại được không?"
            await websocket.send(json.dumps({
                "type": "transcript", "text": "", "accepted": False
            }))
            await self._send_voice_reply(websocket, reply, follow_up=not was_followup, broadcast=False, follow_up_node_id=client_node_id)
            return

        from asr_engine import ASREngine
        if confidence < ASREngine.CONFIDENCE_LOW:
            logger.warning(f"ASR confidence too low ({confidence:.2f}): '{text}' — asking user to repeat")
            reply = "Chưa rõ khẩu lệnh."
            await websocket.send(json.dumps({
                "type": "transcript", "text": "", "confidence": round(confidence, 2), "accepted": False
            }))
            if self.gateway and hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("transcript", {"text": text, "confidence": round(confidence, 2), "status": "low_confidence"})
            await self._send_voice_reply(websocket, reply, follow_up=not was_followup, broadcast=False, follow_up_node_id=client_node_id)
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

        result = await self.gateway.process_voice_command(
            text, client_node_id=client_node_id, detected_room=detected_room
        )
        follow_up = result.get("follow_up", False)
        tts_audio = result.get("tts_audio")
        tts_format = result.get("tts_format", "pcm")
        voice_reply = result.get("voice_reply")
        has_tts = bool(tts_audio or voice_reply)
        await websocket.send(json.dumps({
            "type": "command_result",
            "verify": result.get("verify"),
            "voice_reply": voice_reply,
            "has_tts": has_tts,
            "follow_up": follow_up,
        }))

        if tts_audio and tts_format == "pcm":
            await self._send_pcm_stream(websocket, tts_audio, follow_up=follow_up, follow_up_node_id=client_node_id)
        elif tts_audio and tts_format == "mp3":
            await self._send_audio_stream_mp3(websocket, tts_audio, follow_up=follow_up)
        elif voice_reply:
            await self._send_voice_reply(websocket, voice_reply, follow_up=follow_up, broadcast=False, follow_up_node_id=client_node_id)

    async def speak_kws(self, subbox_id, text, result, synthesis_slots):
        """Reply only to the identified speaker; local firmware owns follow-up."""
        ws = self._ws_nodes.get(subbox_id)
        if not ws or not self._is_ws_alive(ws) or not getattr(ws, "has_speaker", False):
            return False
        async with synthesis_slots:
            pcm = await self.gateway.tts.synthesize_pcm(text, sample_rate=config.AUDIO_SAMPLE_RATE)
        if not pcm or self._ws_nodes.get(subbox_id) is not ws or not self._is_ws_alive(ws):
            return False
        return await self._broadcast_pcm_stream([ws], pcm, kws_result=result)

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
        else:

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
                is_bcast = not node_id or str(node_id).lower() in ("all", "broadcast", "*")
                return bool(await self._broadcast_pcm_stream(targets, pcm_audio, follow_up=False, broadcast=is_bcast))
            else:
                if any(getattr(ws, 'playback_only', False) for ws in targets):
                    return False
                mp3_audio = await self.gateway.tts.synthesize(text)
                if mp3_audio:
                    for ws in targets:
                        await self._send_audio_stream_mp3(ws, mp3_audio, follow_up=False)
                    return True
        except Exception as e:
            logger.error(f"Failed to speak proactive audio: {e}")
        return False

    async def _send_voice_reply(self, websocket, text: str, follow_up: bool = False, broadcast: bool = False, follow_up_node_id=None):
        """Synthesize text to PCM and stream to ESP32 speaker(s) — unicast by default."""
        if not self.gateway or not hasattr(self.gateway, "tts"):
            logger.warning("TTS engine not available")
            return

        is_subbox = "subbox" in str(getattr(websocket, "node_id", "")).lower() or str(getattr(websocket, "node_id", "")).upper().startswith("SB")
        has_spk = getattr(websocket, "has_speaker", False) or is_subbox

        targets = []
        if broadcast and self._active_speakers:
            targets = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
        elif has_spk and websocket and self._is_ws_alive(websocket):

            targets = [websocket]
        else:

            subbox_spks = [
                ws for ws in self._active_speakers
                if self._is_ws_alive(ws) and ("subbox" in str(getattr(ws, "node_id", "")).lower() or str(getattr(ws, "node_id", "")).upper().startswith("SB"))
            ]
            if subbox_spks:
                targets = [subbox_spks[0]]
            elif self._active_speakers:
                alive = [ws for ws in self._active_speakers if self._is_ws_alive(ws)]
                if alive:
                    targets = [alive[0]]

        if not targets:
            logger.info("No speaker target found for voice reply — skipping TTS audio stream")
            return

        pcm_audio = await self.gateway.tts.synthesize_pcm(
            text, sample_rate=config.AUDIO_SAMPLE_RATE
        )

        if pcm_audio:
            await self._broadcast_pcm_stream(targets, pcm_audio, follow_up=follow_up, initiator_ws=websocket, follow_up_node_id=follow_up_node_id, broadcast=broadcast)
        else:

            logger.warning("PCM synthesis failed, trying raw MP3 fallback")
            mp3_audio = await self.gateway.tts.synthesize(text)
            if mp3_audio:
                for ws in targets:
                    await self._send_audio_stream_mp3(ws, mp3_audio, follow_up=follow_up)

    async def _send_pcm_stream(self, websocket, pcm_bytes: bytes, follow_up: bool = False, follow_up_node_id=None):
        """Single speaker wrapper for _broadcast_pcm_stream."""
        is_subbox = "subbox" in str(getattr(websocket, "node_id", "")).lower() or str(getattr(websocket, "node_id", "")).upper().startswith("SB")
        has_spk = getattr(websocket, "has_speaker", False) or is_subbox
        if has_spk and websocket and self._is_ws_alive(websocket):
            await self._broadcast_pcm_stream([websocket], pcm_bytes, follow_up=follow_up, initiator_ws=websocket, follow_up_node_id=follow_up_node_id)
        else:
            subbox_spks = [
                ws for ws in self._active_speakers
                if self._is_ws_alive(ws) and ("subbox" in str(getattr(ws, "node_id", "")).lower() or str(getattr(ws, "node_id", "")).upper().startswith("SB"))
            ]
            target = subbox_spks[0] if subbox_spks else next((ws for ws in self._active_speakers if self._is_ws_alive(ws)), None)
            if target:
                await self._broadcast_pcm_stream([target], pcm_bytes, follow_up=follow_up, initiator_ws=websocket, follow_up_node_id=follow_up_node_id)

    async def _broadcast_pcm_stream(self, targets: list, pcm_bytes: bytes, follow_up: bool = False, initiator_ws=None, follow_up_node_id=None, broadcast: bool = False, kws_result=None):
        """
        Stream raw PCM audio data to ESP32 speaker(s).
        Protected by self._playback_lock so multiple streams can never interleave or corrupt audio.
        Pacing is calibrated: 8 pre-buffer chunks (~512ms) then 70% real-time pacing (~45ms)
        so ESP32 512KB PSRAM DMA buffer never underflows.
        """
        targets = [ws for ws in targets if (getattr(ws, "has_speaker", False) or (getattr(ws, "has_speaker", True) and not getattr(ws, "audio_relay", False))) and self._is_ws_alive(ws)]
        targets = [ws for ws in targets if not getattr(ws, 'playback_only', False) or
                   self._is_token_valid(self._extract_token(ws), getattr(ws, 'node_id', None))]
        if any(getattr(ws, 'requires_playback_ack', False) for ws in targets) and len(pcm_bytes) > 256000:
            return False
        if not targets:
            return

        valid_targets = [ws for ws in targets if self._is_ws_alive(ws)]
        if not valid_targets:
            return

        active_spk_count = len([w for w in self._active_speakers if self._is_ws_alive(w)])
        is_broadcast = broadcast or (len(valid_targets) > 1 and len(valid_targets) == active_spk_count)

        target_rooms = set()
        lock_keys = set()
        for ws in valid_targets:
            nid = getattr(ws, "node_id", None) or getattr(ws, "client_node_id", None)
            rm = self.arbiter._get_room(nid) if nid else None
            # All playback paths share the physical speaker lock.
            lock_keys.add(f"speaker_{nid or id(ws)}")
            if kws_result is None and rm:
                target_rooms.add(rm)
                lock_keys.add(rm)

        locks_to_acquire = []
        if is_broadcast:
            locks_to_acquire.append(self._default_playback_lock)
        for k in sorted(lock_keys):
            locks_to_acquire.append(self._playback_locks[k])

        async with contextlib.AsyncExitStack() as stack:
            for lock in locks_to_acquire:
                await stack.enter_async_context(lock)

            valid_targets = [ws for ws in targets if self._is_ws_alive(ws)]
            valid_targets = [ws for ws in valid_targets if not getattr(ws, 'playback_only', False) or
                             self._is_token_valid(self._extract_token(ws), getattr(ws, 'node_id', None))]
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

            if kws_result is not None:
                notify_nodes = list(valid_targets)
            elif is_broadcast:
                notify_nodes = list({ws for ws in self._ws_nodes.values() if self._is_ws_alive(ws)})
            else:
                notify_nodes = list({
                    ws for ws in self._ws_nodes.values()
                    if self._is_ws_alive(ws) and (
                        (self.arbiter._get_room(getattr(ws, "node_id", None) or getattr(ws, "client_node_id", None)) in target_rooms)
                        or ws in valid_targets
                    )
                })

            busy_msg = json.dumps({"type": "speaker_busy", "busy": True})
            if notify_nodes:
                await asyncio.gather(*[ws.send(busy_msg) for ws in notify_nodes], return_exceptions=True)

            receipts = {}
            for ws in valid_targets:
                if getattr(ws, 'requires_playback_ack', False):
                    playback_id = secrets.token_hex(16)
                    future = asyncio.get_running_loop().create_future()
                    receipts[ws] = (playback_id, future)
                    self._playback_receipts[playback_id] = (ws, future, total_len)
            try:
                start_msg = json.dumps({
                    "type": "audio_start",
                    "format": "pcm",
                    "sample_rate": config.AUDIO_SAMPLE_RATE,
                    "channels": config.AUDIO_CHANNELS,
                    "sample_width": config.AUDIO_SAMPLE_WIDTH,
                    "size": total_len,
                })
                results = await asyncio.gather(*[ws.send(json.dumps({**json.loads(start_msg), 'playback_id':receipts[ws][0]})
                                                        if ws in receipts else start_msg) for ws in valid_targets], return_exceptions=True)
                dead = [ws for ws, res in zip(valid_targets, results) if isinstance(res, Exception)]
                if dead:
                    for d in dead:
                        self._active_speakers.discard(d)
                    valid_targets = [ws for ws in valid_targets if ws not in dead]
                    if not valid_targets:
                        return

                await asyncio.sleep(0.030)

                chunks_sent = 0
                bytes_per_sec = config.AUDIO_SAMPLE_RATE * config.AUDIO_SAMPLE_WIDTH
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

                    if chunks_sent <= 16:
                        await asyncio.sleep(0.002)
                    else:
                        chunk_duration = len(chunk) / bytes_per_sec
                        await asyncio.sleep(chunk_duration * 0.80)

                tasks = []
                for ws in valid_targets:
                    ws_follow_up = follow_up if (ws == initiator_ws or initiator_ws is None) else False
                    end_payload = {
                        "type": "audio_end", "follow_up": ws_follow_up,
                        "timeout_ms": 6000 if ws_follow_up else 0
                    }
                    if ws in receipts:
                        end_payload['playback_id'] = receipts[ws][0]
                    parent = getattr(ws, "node_id", "")
                    mqtt = getattr(self.gateway, "mqtt", None)
                    identity = getattr(mqtt, "node_identities", {}).get(follow_up_node_id)
                    if (ws_follow_up and identity and getattr(mqtt, "session_id", 0)
                            and self._relay_source_epoch(parent, follow_up_node_id) is not None):
                        command = {"protocol_version": 3, "node_id": follow_up_node_id,
                                   "hardware_uid": identity["hardware_uid"],
                                   "config_version": identity["config_version"],
                                   "request_id": secrets.randbelow(0x7ffffffe) + 1,
                                   "session_id": mqtt.session_id, "cmd": "LISTEN_FOLLOWUP"}
                        end_payload["follow_up_command"] = json.dumps(command, separators=(",", ":"))
                        self._followup_pending = {node: deadline for node, deadline in self._followup_pending.items()
                                                  if deadline > time.monotonic()}
                        self._followup_pending[follow_up_node_id] = time.monotonic() + 30
                        dialog = getattr(self.gateway, "dialog", None)
                        if dialog and follow_up_node_id in dialog._sessions:
                            dialog._sessions[follow_up_node_id].created_at = time.time()
                    end_msg = json.dumps(end_payload)
                    tasks.append(ws.send(end_msg))
                if tasks:
                    end_results = await asyncio.gather(*tasks, return_exceptions=True)
                    valid_targets = [ws for ws, res in zip(valid_targets, end_results) if not isinstance(res, Exception)]

                confirmed = []
                for ws in valid_targets:
                    if ws in receipts:
                        try:
                            ok = await asyncio.wait_for(asyncio.shield(receipts[ws][1]), 3)
                        except asyncio.TimeoutError:
                            ok = False
                        if not ok:
                            logger.warning('Speaker did not confirm complete playback: %s', getattr(ws, 'node_id', '?'))
                            continue
                        logger.info('Speaker confirmed playback: %s (%d bytes)', getattr(ws, 'node_id', '?'), total_len)
                    confirmed.append(ws)
                valid_targets = confirmed

                logger.info(
                    f"✅ Streamed {total_len} bytes in {chunks_sent} chunks to {len(valid_targets)} ESP32(s)"
                )
            finally:
                for playback_id, future in receipts.values():
                    self._playback_receipts.pop(playback_id, None)
                    if not future.done():
                        future.cancel()
                if self.gateway and hasattr(self.gateway, "broadcast_event"):
                    self.gateway.broadcast_event("audio_state", {"state": "IDLE"})

                free_msg = json.dumps({"type": "speaker_busy", "busy": False})
                if notify_nodes:
                    await asyncio.gather(*[ws.send(free_msg) for ws in notify_nodes], return_exceptions=True)
            if kws_result is not None and valid_targets:
                done = {"type": "kws_playback_done", **{key:kws_result[key] for key in ("session_id", "request_id", "origin_node")}}
                await valid_targets[0].send(json.dumps(done))
                return True
            return bool(valid_targets)

    async def _send_audio_stream_mp3(self, websocket, audio_bytes: bytes, follow_up: bool = False):
        """
        Fallback: Stream MP3 audio data back to ESP32.
        ESP32 would need an MP3 decoder for this path.
        """
        if getattr(websocket, 'playback_only', False):
            return False
        if not getattr(websocket, "has_speaker", False) and (not getattr(websocket, "has_speaker", True) or getattr(websocket, "audio_relay", False)):
            return
        total_len = len(audio_bytes)
        chunk_size = config.WS_SEND_CHUNK_SIZE

        await websocket.send(json.dumps({
            "type": "audio_start",
            "format": "mp3",
            "size": total_len,
        }))

        for i in range(0, total_len, chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            await websocket.send(chunk)
            await asyncio.sleep(0.005)

        await websocket.send(json.dumps({
            "type": "audio_end",
            "follow_up": follow_up,
            "timeout_ms": 6000 if follow_up else 0
        }))
        logger.info(f"Streamed {total_len} bytes MP3 to ESP32 (fallback)")
