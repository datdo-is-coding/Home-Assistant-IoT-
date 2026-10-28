"""
SIC Home — Smart Home Operating System & Energy Ecosystem
=====================================================
Multi-page luxury dashboard, Three.js 3D Digital Twin, OTA Firmware Center,
Device Commissioning & Multi-tenant Device Scoping.
Self-contained async HTTP + SSE server.
"""

import asyncio
import json
import logging
import os
import time
import urllib.parse
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional

import config
from device_lifecycle import ClaimError, OperationError, OperationKind

logger = logging.getLogger("web_server")

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")

def get_html_page() -> str:
    try:
        if os.path.exists(TEMPLATE_PATH):
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logger.error(f"Error reading template: {e}")
    return "<h1>SIC Home</h1>"

HTML_PAGE = get_html_page()

async def _run_nmcli(*args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        return proc
    except Exception as e:
        logger.debug(f"nmcli {' '.join(args)} error: {e}")
        return None

class WebServer:
    """Async HTTP + SSE dashboard & Aetheria OS manager."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.host = getattr(config, "WEB_HOST", "0.0.0.0")
        self.port = getattr(config, "WEB_PORT", 8000)
        self.server = None
        self.sse_queues = {}
        self._running = False
        self._event_revision = 0

    @property
    def ota_manager(self):
        if hasattr(self, "_ota_manager") and self._ota_manager is not None:
            return self._ota_manager
        return getattr(self.gateway, "ota", None)

    @ota_manager.setter
    def ota_manager(self, value):
        self._ota_manager = value

    async def start(self):
        self._running = True
        try:
            self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
            logger.info(f"🌐 SIC Home Web Dashboard: http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Web server failed on {self.port}: {e}")

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Web server stopped")

    def broadcast_event(self, event_name: str, data: Dict[str, Any]):
        self._event_revision += 1
        data["revision"] = self._event_revision
        if not self.sse_queues:
            return
        payload = f"id: {self._event_revision}\nevent: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        allowed_non_admin_events = {
            "node_status",
            "node_telemetry",
            "relay_state",
            "device_deleted",
            "device_rebooted",
            "operation_updated",
        }
        for q, user in list(self.sse_queues.items()):
            if user.get("role") != "admin":
                node_id = data.get("node_id") or data.get("device_id")
                if (
                    event_name not in allowed_non_admin_events
                    or not node_id
                    or not (
                        hasattr(self.gateway, "auth")
                        and self.gateway.auth
                        and node_id in self.gateway.auth.get_user_devices(user["id"])
                    )
                ):
                    continue
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def broadcast(self, event_name: str, data: Dict[str, Any]):
        self.broadcast_event(event_name, data)

    def _nodes_snapshot(self, user: Optional[Dict[str, Any]] = None) -> dict:
        r = self.gateway.registry
        all_nodes = r.get_all_nodes()
        if hasattr(self.gateway, "auth") and self.gateway.auth:
            all_nodes = self.gateway.auth.filter_nodes(user, all_nodes)

        all_nodes = {key: dict(value) for key, value in all_nodes.items()}
        now = datetime.now(timezone.utc)
        for node in all_nodes.values():
            if node.get("status") != "online":
                continue
            try:
                seen = datetime.fromisoformat(node.get("last_seen", ""))
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                age = (now - seen).total_seconds()
                fresh = 0 <= age < 90
            except (ValueError, TypeError):
                fresh = False
            if not fresh:
                node["status"] = "offline"

        disc = self.gateway.discovery.get_discovered_devices() if hasattr(self.gateway, "discovery") else {}
        mqtt_obj = getattr(self.gateway, "mqtt", None)
        mqtt_ch_powers = getattr(mqtt_obj, "channel_powers", {}) if mqtt_obj else {}
        for node_id, node in all_nodes.items():
            if str(node_id).upper().startswith("SB"):
                node.setdefault("board_model", "subbox")
                node.setdefault("device_type", "subbox")
            ch_powers = mqtt_ch_powers.get(node_id, {})
            channels = node.get("channels", {})
            if isinstance(channels, dict):
                for ch_k, ch_info in channels.items():
                    if isinstance(ch_info, dict) and ch_k in ch_powers and "power" not in ch_info:
                        ch_info["power"] = ch_powers[ch_k]

        return {
            "nodes": all_nodes,
            "rooms": r.get_rooms() if user and user.get("role") == "admin" else sorted({n.get("room", "") for n in all_nodes.values()}),
            "pending": r.get_pending() if user and user.get("role") == "admin" else {},
            "discovered": disc if user and user.get("role") == "admin" else {},
        }

    async def _respond(self, writer, status, data, extra=""):
        reasons = {
            200: "OK",
            202: "Accepted",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
            413: "Payload Too Large",
            429: "Too Many Requests",
            500: "Internal Server Error",
        }
        body = json.dumps(data, ensure_ascii=False).encode()
        writer.write((f"HTTP/1.1 {status} {reasons.get(status, 'OK')}\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n").encode() + body)
        await writer.drain()
        writer.close()

    async def _handle_client(self, reader, writer):
        try:
            request_line = await asyncio.wait_for(reader.readline(), 10)
            parts = request_line.decode("ascii").split()
            if len(parts) != 3 or len(request_line) > 8192:
                await self._respond(writer, 400, {"error": "Malformed request"}); return
            method, full_path = parts[0].upper(), parts[1]
            parsed_url = urllib.parse.urlparse(full_path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            headers = {}
            header_bytes = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), 10)
                header_bytes += len(line)
                if header_bytes > 16384:
                    await self._respond(writer, 400, {"error": "Headers too large"}); return
                if line == b"\r\n": break
                if not line or b":" not in line:
                    await self._respond(writer, 400, {"error": "Malformed headers"}); return
                k, v = line.decode("latin-1").strip().split(":", 1)
                k = k.lower().strip()
                if k in headers:
                    await self._respond(writer, 400, {"error": "Duplicate header"}); return
                headers[k] = v.strip()
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = -1
            if content_length < 0 or "transfer-encoding" in headers:
                await self._respond(writer, 400, {"error": "Invalid body framing"}); return
            maximum = 10 * 1024 * 1024 if path == "/api/ota/upload" else 65536
            if content_length > maximum:
                await self._respond(writer, 413, {"error": "Request too large"}); return
            origin = headers.get("origin")
            host_header = headers.get("host", "").strip()
            allowed_origins = {config.WEB_PUBLIC_ORIGIN.rstrip("/")}
            if host_header:
                allowed_origins.add(f"http://{host_header.rstrip('/')}")
                allowed_origins.add(f"https://{host_header.rstrip('/')}")
            if origin and origin.rstrip("/") not in allowed_origins:
                await self._respond(writer, 403, {"error": "Cross-origin request denied"}); return
            cookies = SimpleCookie()
            cookies.load(headers.get("cookie", ""))
            auth_header = headers.get("authorization", "")
            token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else headers.get("x-api-key", "")
            cookie_auth = not token and "aetheria_session" in cookies
            if cookie_auth:
                token = cookies["aetheria_session"].value
                if method not in ("GET", "HEAD") and origin and origin.rstrip("/") not in allowed_origins:
                    await self._respond(writer, 403, {"error": "Origin required for cookie authentication"}); return
            auth = getattr(self.gateway, "auth", None)
            current_user = auth.authenticate_token(token) if auth and token else None
            extra_info = getattr(writer, "get_extra_info", None)
            is_ssl = bool(extra_info("sslcontext")) if callable(extra_info) else False
            is_https = headers.get("x-forwarded-proto", "").lower() == "https" or is_ssl
            secure_attr = " Secure;" if is_https else ""

            is_commissioning_wifi = (
                method == "POST" and path == "/api/wifi/connect" and (
                    (auth and hasattr(auth, "has_any_admin") and not auth.has_any_admin())
                    or getattr(self.gateway, "is_commissioning", False)
                )
            )
            is_ota_download_with_ticket = False
            if method in ("GET", "HEAD") and path.startswith("/api/ota/download/"):
                req_ticket = query.get("ticket", [None])[0]
                req_device = query.get("device", [None])[0]
                fn = os.path.basename(path)
                ota_mgr = getattr(self.gateway, "ota", None)
                if ota_mgr and req_ticket and hasattr(ota_mgr, "validate_download_ticket"):
                    if ota_mgr.validate_download_ticket(req_ticket, req_device, fn):
                        is_ota_download_with_ticket = True

            public = (
                (method == "GET" and path in {"/", "/index.html", "/api/health", "/api/wifi/status", "/api/wifi/scan"})
                or (method == "POST" and path == "/api/auth/login")
                or is_commissioning_wifi
                or is_ota_download_with_ticket
                or (method in ("GET", "HEAD") and path in ("/downloads/app-release.apk", "/api/app/download", "/downloads/aetheria_home_assistant.apk"))
            )
            if not current_user and not public:
                await self._respond(writer, 401, {"error": "Authentication required"}); return
            raw_body = await asyncio.wait_for(reader.readexactly(content_length), 10) if content_length else b""
            async def _read_body():
                return raw_body
            if current_user and current_user.get("role") != "admin":
                allowed = (method == "GET" and path in {"/", "/index.html", "/api/nodes", "/api/events", "/api/auth/me", "/api/health", "/api/voice/vocabulary"}) or (method == "POST" and path == "/api/auth/logout") or (is_commissioning_wifi and path == "/api/wifi/connect")
                target = None
                if method == "POST" and path == "/api/relay":
                    try: target = json.loads(raw_body).get("node_id")
                    except (ValueError, AttributeError): pass
                elif method == "POST" and path in {"/api/device/alias", "/api/device/alias/delete"}:
                    try:
                        b = json.loads(raw_body)
                        target = (b.get("device_id") or b.get("node_id") or "").split("::")[0]
                    except (ValueError, AttributeError): pass
                elif method == "GET" and path.startswith("/api/device/") and path.rsplit("/", 1)[-1] in {"twin", "telemetry"}:
                    target = query.get("id", query.get("device_id", [None]))[0]
                    if len(path.split("/")) == 5: target = path.split("/")[3]
                if target:
                    allowed = target in auth.get_user_devices(current_user["id"])
                if not allowed:
                    await self._respond(writer, 403, {"error": "Insufficient permissions"}); return

            if path == "/api/kws/config" and method in ("GET", "PUT"):
                try:
                    data = self.gateway.kws.get_config() if method == "GET" else await self.gateway.kws.set_config(json.loads(raw_body))
                    await self._respond(writer, 200, data)
                except (ValueError, TypeError) as exc:
                    await self._respond(writer, 409 if str(exc) == "revision_conflict" else 400, {"error": str(exc)})
                return

            # Route guard for device lifecycle & commissioning: admin only
            is_lifecycle_endpoint = (
                path.startswith("/api/commissioning")
                or path.startswith("/api/operations")
                or (path.startswith("/api/devices/") and ("/operations" in path or path.endswith("/remove")))
            )
            if is_lifecycle_endpoint:
                if not current_user:
                    await self._respond(writer, 401, {"error": "Authentication required"}); return
                if current_user.get("role") != "admin":
                    await self._respond(writer, 403, {"error": "Admin privileges required"}); return

                if path == "/api/commissioning/candidates" and method == "GET":
                    now = time.time()
                    candidates = []
                    if hasattr(self.gateway, "lifecycle") and self.gateway.lifecycle:
                        active_candidates = self.gateway.lifecycle.get_candidates(now)
                        candidates = [c.to_api_dict() for c in active_candidates]
                    await self._respond(writer, 200, {"success": True, "candidates": candidates}); return

                if path == "/api/commissioning/claims" and method == "POST":
                    body_json = {}
                    if raw_body:
                        try:
                            body_json = json.loads(raw_body.decode())
                        except Exception:
                            await self._respond(writer, 400, {"error": "Invalid JSON"}); return
                    if not hasattr(self.gateway, "lifecycle") or not self.gateway.lifecycle:
                        await self._respond(writer, 500, {"error": "Lifecycle manager not initialized"}); return

                    try:
                        now = time.time()
                        op = self.gateway.lifecycle.start_claim(current_user, body_json, now)
                        await self._respond(writer, 202, {
                            "success": True,
                            "operation": op.to_dict(),
                            **op.to_dict()
                        }); return
                    except ClaimError as e:
                        await self._respond(writer, e.status_code, {
                            "success": False,
                            "error": e.error_code,
                            "error_code": e.error_code,
                            "message": e.message
                        }); return
                    except Exception as e:
                        await self._respond(writer, 400, {
                            "success": False,
                            "error": str(e)
                        }); return

                parts = [p for p in path.split("/") if p]

                if len(parts) == 4 and parts[0] == "api" and parts[1] == "devices" and parts[3] == "operations" and method == "POST":
                    uid = parts[2]
                    body_json = {}
                    if raw_body:
                        try:
                            body_json = json.loads(raw_body.decode())
                        except Exception:
                            await self._respond(writer, 400, {"error": "Invalid JSON"}); return
                    if not hasattr(self.gateway, "lifecycle") or not self.gateway.lifecycle:
                        await self._respond(writer, 500, {"error": "Lifecycle manager not initialized"}); return

                    kind = body_json.get("kind")
                    if not kind:
                        await self._respond(writer, 400, {
                            "success": False,
                            "error": "MISSING_KIND",
                            "error_code": "MISSING_KIND",
                            "message": "kind is required",
                        }); return
                    confirmation = bool(body_json.get("confirmation", False))
                    idempotency_key = body_json.get("idempotency_key")
                    now = time.time()
                    try:
                        op = self.gateway.lifecycle.start_operation(
                            user=current_user,
                            device_uid=uid,
                            kind=kind,
                            idempotency_key=idempotency_key,
                            confirmation=confirmation,
                            now_sec=now,
                        )
                        await self._respond(writer, 202, {
                            "success": True,
                            "operation": op.to_dict(),
                            **op.to_dict(),
                        }); return
                    except OperationError as e:
                        await self._respond(writer, e.status_code, {
                            "success": False,
                            "error": e.error_code,
                            "error_code": e.error_code,
                            "message": e.message,
                        }); return
                    except Exception as e:
                        await self._respond(writer, 400, {
                            "success": False,
                            "error": str(e),
                        }); return

                if len(parts) == 4 and parts[0] == "api" and parts[1] == "devices" and parts[3] == "remove" and method == "POST":
                    uid = parts[2]
                    body_json = {}
                    if raw_body:
                        try:
                            body_json = json.loads(raw_body.decode())
                        except Exception:
                            pass
                    if not hasattr(self.gateway, "lifecycle") or not self.gateway.lifecycle:
                        await self._respond(writer, 500, {"error": "Lifecycle manager not initialized"}); return

                    idempotency_key = body_json.get("idempotency_key")
                    now = time.time()
                    try:
                        op = self.gateway.lifecycle.start_operation(
                            user=current_user,
                            device_uid=uid,
                            kind=OperationKind.REMOVE_FROM_HOME,
                            idempotency_key=idempotency_key,
                            confirmation=True,
                            now_sec=now,
                        )
                        await self._respond(writer, 200, {
                            "success": True,
                            "device_id": uid,
                            "operation": op.to_dict(),
                            **op.to_dict(),
                        }); return
                    except OperationError as e:
                        await self._respond(writer, e.status_code, {
                            "success": False,
                            "error": e.error_code,
                            "error_code": e.error_code,
                            "message": e.message,
                        }); return
                    except Exception as e:
                        await self._respond(writer, 400, {
                            "success": False,
                            "error": str(e),
                        }); return

                if path.startswith("/api/operations/") and method == "GET":
                    op_id = parts[2] if len(parts) >= 3 else ""
                    if not hasattr(self.gateway, "lifecycle") or not self.gateway.lifecycle:
                        await self._respond(writer, 500, {"error": "Lifecycle manager not initialized"}); return
                    now = time.time()
                    op = self.gateway.lifecycle.get_operation(op_id, now_sec=now)
                    if not op:
                        await self._respond(writer, 404, {"error": "Operation not found"}); return
                    await self._respond(writer, 200, {
                        "success": True,
                        "operation": op.to_dict(),
                        **op.to_dict()
                    }); return

                elif hasattr(self.gateway, "handle_lifecycle_request"):
                    body_json = {}
                    if raw_body:
                        try: body_json = json.loads(raw_body.decode())
                        except Exception: pass
                    res = await self.gateway.handle_lifecycle_request(method, path, body_json, user=current_user)
                    await self._respond(writer, 200, res); return
                else:
                    await self._respond(writer, 200, {"success": True, "endpoint": path, "status": "ready"}); return

            if method == "GET" and path == "/api/health":
                await self._respond(writer, 200, {"status": "ok"}); return

            if method == "GET" and path in ("/", "/index.html"):
                body = get_html_page().encode("utf-8")
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: text/html; charset=utf-8\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/nodes":
                data = self._nodes_snapshot(current_user)
                body = json.dumps(data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/events":
                writer.write(("HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: text/event-stream\r\n"
                              "Cache-Control: no-cache\r\nConnection: keep-alive\r\n"
                              "\r\n").encode())
                await writer.drain()
                q = asyncio.Queue(maxsize=64)
                self.sse_queues[q] = current_user
                try:
                    init_d = json.dumps(self._nodes_snapshot(current_user), ensure_ascii=False)
                    writer.write(f"id: {self._event_revision}\nevent: init\ndata: {init_d}\n\n".encode())
                    await writer.drain()
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(q.get(), timeout=15.0)
                        except asyncio.TimeoutError:
                            msg = ": keepalive\n\n"
                        if not auth.authenticate_token(token):
                            break
                        writer.write(msg.encode())
                        await writer.drain()
                except (asyncio.TimeoutError, Exception):
                    pass
                finally:
                    self.sse_queues.pop(q, None)
                    try: writer.close()
                    except Exception: pass
                return

            if method == "POST" and path == "/api/relay":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    node_id = d.get("node_id")
                    channel = d.get("channel", d.get("ch"))
                    action = d.get("action", d.get("s"))

                    if action not in ("turn_on", "turn_off", "TURN_ON", "TURN_OFF", "on", "off", 0, 1, "0", "1") or channel not in ("ch1", "ch2", "ch3", 1, 2, 3, "1", "2", "3"):
                        await self._respond(writer, 400, {"error": "Use an explicit relay state and valid channel"}); return
                    action = "turn_on" if action in ("turn_on", "TURN_ON", "on", 1, "1") else "turn_off"
                    channel = {"ch1": "ch1", "ch2": "ch2", "ch3": "ch3", 1: "ch1", 2: "ch2", 3: "ch3", "1": "ch1", "2": "ch2", "3": "ch3"}[channel]
                    result, *_ = await self.gateway.verifier.verify_command(node_id, channel, action)
                    outcome = result.value
                    is_ok = outcome in {"ack_only", "confirmed_load", "already_in_state"}

                    if is_ok and hasattr(self.gateway, "registry"):
                        node = self.gateway.registry.data.get("nodes", {}).get(node_id)
                        if node:
                            ch_idx = int(channel[2:]) - 1
                            new_val = 1 if action == "turn_on" else 0
                            cur_rl = list(node.get("relay_state", [0, 0]))
                            caps = node.get("capabilities", [])
                            min_len = 3 if ("relay_3ch" in caps or len(node.get("channels", {})) >= 3) else 2
                            while len(cur_rl) < max(ch_idx + 1, min_len):
                                cur_rl.append(0)
                            cur_rl[ch_idx] = new_val
                            self.gateway.registry.update_relay_state(node_id, cur_rl)
                            if hasattr(self.gateway, "broadcast_event"):
                                self.gateway.broadcast_event("relay_state", {"node_id": node_id, "relay_state": cur_rl})
                            else:
                                self.broadcast_event("relay_state", {"node_id": node_id, "relay_state": cur_rl})

                    resp_data = {"success": is_ok, "verify": outcome, "node_id": node_id, "channel": channel, "action": action}
                    if not is_ok:
                        resp_data["error"] = f"Relay command failed on gateway ({outcome})"
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and (path in ("/api/provision", "/api/device/claim", "/api/device/add")):
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    mac = d.get("mac", "").upper()
                    dev_id = d.get("device_id", "")
                    target_key = dev_id if (dev_id and dev_id in self.gateway.registry.get_pending()) else mac
                    if not target_key or target_key not in self.gateway.registry.get_pending():
                        for pk, pv in self.gateway.registry.get_pending().items():
                            if pk == dev_id or pk == mac or pv.get("mac") == mac or pv.get("device_id") == dev_id:
                                target_key = pk
                                break
                    if not target_key:
                        target_key = dev_id or mac

                    res = await self.gateway.provision_pending(
                        target_key,
                        room=d.get("room", "livingroom"),
                        rl1=d.get("rl1", "light"),
                        rl2=d.get("rl2", "fan"),
                        rl3=d.get("rl3"),
                        node_short=d.get("node_short"),
                        name=d.get("name"),
                        location=d.get("location"),
                        description=d.get("description")
                    )

                    if current_user and hasattr(self.gateway, "auth"):
                        nid = res.get("device_id") or res.get("node_id")
                        if nid:
                            self.gateway.auth.assign_device_to_user(current_user["id"], nid)
                    resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method in ("POST", "DELETE") and (path == "/api/device/delete" or (path.startswith("/api/device/") and path.endswith("/delete"))):
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}") if body else {}
                    dev_id = d.get("device_id") or d.get("node_id")
                    if not dev_id:
                        parts = [p for p in path.split("/") if p]
                        if len(parts) >= 3:
                            dev_id = parts[2]
                    if not dev_id:
                        resp_data = {"success": False, "error": "device_id is required"}
                    else:
                        if hasattr(self.gateway, "delete_device"):
                            ok = await self.gateway.delete_device(dev_id)
                        else:
                            ok = self.gateway.registry.delete_node(dev_id)
                            self.broadcast_event("device_deleted", {"device_id": dev_id})
                        resp_data = {"success": ok, "device_id": dev_id}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and (path == "/api/device/update" or path == "/api/device/edit"):
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    dev_id = d.get("device_id") or d.get("node_id")
                    if not dev_id:
                        resp_data = {"success": False, "error": "device_id is required"}
                    elif hasattr(self.gateway, "update_device"):
                        updated = await self.gateway.update_device(dev_id, d)
                        resp_data = {"success": True, "device": updated}
                    else:
                        resp_data = {"success": False, "error": "Gateway update_device not available"}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and (path == "/api/device/alias" or path == "/api/device/alias/delete"):
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    dev_id = d.get("device_id") or d.get("node_id")
                    channel = d.get("channel")
                    alias = d.get("alias")
                    action = d.get("action", "remove" if path.endswith("/delete") else "add")

                    logger.info(f"[VOCAB][RX] received vocabulary: deviceId={dev_id}, channel={channel}, alias={alias}, action={action}")

                    if not dev_id or not alias:
                        resp_data = {"success": False, "error": "device_id and alias are required"}
                    else:
                        if action == "remove":
                            resp_data = await self.gateway.remove_device_alias(dev_id, channel, alias)
                        else:
                            resp_data = await self.gateway.add_device_alias(dev_id, channel, alias)
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/voice/vocabulary":
                try:
                    if hasattr(self.gateway, "get_voice_vocabulary_diagnostics"):
                        resp_data = self.gateway.get_voice_vocabulary_diagnostics(user=current_user)
                    else:
                        resp_data = {"success": False, "error": "Voice vocabulary diagnostics not available"}

                    # Strict permission filtering: Member only sees devices permitted by auth.get_user_devices
                    if current_user and current_user.get("role") != "admin" and auth and hasattr(auth, "get_user_devices") and isinstance(resp_data, dict):
                        resp_data = dict(resp_data)
                        allowed_devs = set(auth.get_user_devices(current_user.get("id")))
                        if "devices" in resp_data and isinstance(resp_data["devices"], list):
                            resp_data["devices"] = [d for d in resp_data["devices"] if d in allowed_devs]
                        if "stored_vocabulary" in resp_data and isinstance(resp_data["stored_vocabulary"], list):
                            resp_data["stored_vocabulary"] = [
                                item for item in resp_data["stored_vocabulary"]
                                if item.get("node_id") in allowed_devs or (item.get("device_id") and item.get("device_id").split("::")[0] in allowed_devs)
                            ]
                            resp_data["total_stored_items"] = len(resp_data["stored_vocabulary"])
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and (path == "/api/device/config" or (path.startswith("/api/device/") and path.endswith("/config"))):
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    if path != "/api/device/config":
                        parts = [p for p in path.split("/") if p]
                        if len(parts) >= 3:
                            d["device_id"] = parts[2]
                    dev_id = d.get("device_id")
                    if not dev_id:
                        resp_data = {"success": False, "error": "device_id is required"}
                    else:
                        resp_data = await self.gateway.update_device_desired_config(dev_id, d)
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and (path == "/api/device/twin" or (path.startswith("/api/device/") and path.endswith("/twin"))):
                dev_id = query.get("id", [None])[0] or query.get("device_id", [None])[0]
                if not dev_id and path != "/api/device/twin":
                    parts = [p for p in path.split("/") if p]
                    if len(parts) >= 3:
                        dev_id = parts[2]
                twin = self.gateway.registry.get_device_twin(dev_id) if dev_id else None
                resp_data = {"success": bool(twin), "twin": twin} if twin else {"success": False, "error": f"Device {dev_id} not found"}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and (path == "/api/device/telemetry" or (path.startswith("/api/device/") and path.endswith("/telemetry"))):
                dev_id = query.get("id", [None])[0] or query.get("device_id", [None])[0]
                if not dev_id and path != "/api/device/telemetry":
                    parts = [p for p in path.split("/") if p]
                    if len(parts) >= 3:
                        dev_id = parts[2]
                try:
                    limit = max(1, min(int(query.get("limit", [50])[0]), 1000))
                except (TypeError, ValueError):
                    limit = 50
                channel = (query.get("channel", [None])[0] or "").strip() or None
                if channel:
                    records = self.gateway.registry.get_channel_telemetry_history(
                        dev_id, channel=channel, limit=limit) if dev_id else []
                    resp_data = {"device_id": dev_id, "channel": channel, "telemetry": records}
                else:
                    records = self.gateway.registry.get_telemetry_history(dev_id, limit=limit) if dev_id else []
                    channel_records = self.gateway.registry.get_channel_telemetry_history(
                        dev_id, limit=limit) if dev_id else []
                    resp_data = {"device_id": dev_id, "telemetry": records, "channels": channel_records}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/ota/history":
                dev_id = query.get("device_id", [None])[0]
                records = self.gateway.registry.get_ota_history(dev_id)
                resp_data = {"history": records}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/proactive/status":
                has_gemini = bool(getattr(self.gateway, "persona", None) and self.gateway.persona.has_api_key)
                proactive_en = bool(getattr(self.gateway, "proactive", None) and self.gateway.proactive.enabled)
                resp_data = {
                    "enabled": proactive_en,
                    "has_gemini_key": has_gemini,
                    "tts_provider": getattr(config, "TTS_PROVIDER", "edgetts"),
                    "vieneu_voice": getattr(config, "VIENEU_VOICE", "Ái Hân"),
                    "tts_rate": getattr(config, "TTS_RATE", "-4%"),
                    "tts_pitch": getattr(config, "TTS_PITCH", "+2Hz")
                }
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/settings/voice":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    provider = d.get("provider", "edgetts").lower().strip()
                    config.TTS_PROVIDER = provider
                    if "vieneu_voice" in d:
                        config.VIENEU_VOICE = str(d["vieneu_voice"]).strip()
                    if "rate" in d:
                        config.TTS_RATE = str(d["rate"]).strip()
                    if "pitch" in d:
                        config.TTS_PITCH = str(d["pitch"]).strip()

                    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_config.json")
                    cfg_data = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                cfg_data = json.load(f)
                        except Exception: pass
                    cfg_data["TTS_PROVIDER"] = config.TTS_PROVIDER
                    cfg_data["VIENEU_VOICE"] = config.VIENEU_VOICE
                    cfg_data["TTS_RATE"] = config.TTS_RATE
                    cfg_data["TTS_PITCH"] = config.TTS_PITCH
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, ensure_ascii=False, indent=2)

                    resp_data = {"success": True, "provider": provider}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/sounds":
                data = self.gateway.sound.list_sounds() if hasattr(self.gateway, "sound") else {"sounds": []}
                body = json.dumps(data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method in ("GET", "HEAD") and path.startswith("/api/sound/"):
                sound_name = path.replace("/api/sound/", "").strip()
                audio_bytes = self.gateway.sound.get_mp3_data(sound_name) if hasattr(self.gateway, "sound") else None
                if audio_bytes:
                    writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: audio/mpeg\r\n"
                                  f"Content-Length: {len(audio_bytes)}\r\n"
                                  f"Connection: close\r\n\r\n").encode() + audio_bytes)
                    await writer.drain(); writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/sound/play":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    s_name = d.get("sound", "bootup_sound")
                    node_id = d.get("node_id", "all")
                    ok = False
                    if hasattr(self.gateway, "sound") and self.gateway.sound:
                        ok = await self.gateway.sound.play_sound(s_name, target_node=node_id)
                    resp_data = {"success": ok, "sound": s_name, "node_id": node_id}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method in ("GET", "HEAD") and path.startswith("/api/tts/preview"):
                test_text = query.get("text", ["Đã bật đèn phòng khách."])[0]
                audio_bytes = None
                if hasattr(self.gateway, "tts") and self.gateway.tts:
                    audio_bytes = await self.gateway.tts.synthesize(test_text)
                if audio_bytes:
                    mime = "audio/wav" if audio_bytes.startswith(b"RIFF") else "audio/mpeg"
                    writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: {mime}\r\n"
                                  f"Content-Length: {len(audio_bytes)}\r\n"
                                  f"Connection: close\r\n\r\n").encode() + audio_bytes)
                    await writer.drain(); writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/proactive/test_speak":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    t = d.get("type", "chào")
                    if t == "an_toan":
                        text = "Cảnh báo: bình nóng lạnh đã bật liên tục hơn 35 phút. Vui lòng kiểm tra tắt để đảm bảo an toàn."
                    else:
                        text = "Hệ thống nhà thông minh đang hoạt động ổn định."

                    ok = False
                    if hasattr(self.gateway, "audio_server") and self.gateway.audio_server:
                        ok = await self.gateway.audio_server.speak_proactive(text)
                    resp_data = {"success": ok, "text": text, "type": t}
                    if not ok:
                        resp_data["error"] = "Không có loa sẵn sàng hoặc chưa xác nhận phát âm thanh."
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/settings/gemini_key":
                await self._respond(writer, 403, {"error": "Configure GEMINI_API_KEY in the service environment"}); return

            if method == "POST" and path == "/api/proactive/toggle":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    enabled = bool(d.get("enabled", True))
                    if hasattr(self.gateway, "proactive") and self.gateway.proactive:
                        self.gateway.proactive.enabled = enabled
                    config.PROACTIVE_ENABLED = enabled
                    resp_data = {"success": True, "enabled": enabled}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/ota/list":
                items = []
                if hasattr(self.gateway, "ota") and self.gateway.ota:
                    items = self.gateway.ota.list_firmwares()
                body = json.dumps({"firmwares": items}, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/upload":
                raw_bytes = await _read_body()
                filename = headers.get("x-filename", f"firmware_{int(time.time())}.bin")
                if hasattr(self.gateway, "ota") and self.gateway.ota:
                    res = self.gateway.ota.save_firmware(filename, raw_bytes)
                    if not res.get("valid_esp", False):
                        resp_data = {"success": False, "error": res.get("error", "Invalid ESP32 binary"), **res}
                    else:
                        resp_data = {"success": True, **res}
                else:
                    resp_data = {"success": False, "error": "OTA manager not available"}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/delete":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    fn = d.get("filename")
                    ok = self.gateway.ota.delete_firmware(fn) if hasattr(self.gateway, "ota") else False
                    resp_data = {"success": ok}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/ota/flash":
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    fn = d.get("filename")
                    node_id = d.get("node_id", "all")

                    if not fn:
                        resp_data = {"success": False, "error": "Thiếu tên file firmware (.bin)"}
                    elif not hasattr(self.gateway, "ota") or not self.gateway.ota:
                        resp_data = {"success": False, "error": "OTA manager không khả dụng trên Gateway"}
                    else:

                        gw_ip = ""
                        req_host = headers.get("host", "").split(":")[0]
                        if req_host and req_host not in ("localhost", "127.0.0.1", "0.0.0.0"):
                            gw_ip = req_host
                        elif hasattr(self.gateway.ota, "get_gateway_lan_ip"):
                            gw_ip = self.gateway.ota.get_gateway_lan_ip()
                        else:
                            gw_ip = self.host if self.host != "0.0.0.0" else "127.0.0.1"

                        res = await self.gateway.ota.trigger_via_mqtt(node_id, fn, gateway_ip=gw_ip)
                        resp_data = res
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method in ("GET", "HEAD") and path.startswith("/api/ota/download/"):
                fn = os.path.basename(path)
                req_ticket = query.get("ticket", [None])[0]
                req_device = query.get("device", [None])[0]
                ota_mgr = getattr(self.gateway, "ota", None)

                is_authorized = False
                if current_user and current_user.get("role") == "admin":
                    is_authorized = True
                elif ota_mgr and req_ticket and hasattr(ota_mgr, "validate_download_ticket"):
                    if ota_mgr.validate_download_ticket(req_ticket, req_device, fn):
                        is_authorized = True

                if not is_authorized:
                    await self._respond(writer, 401, {"error": "Authentication or valid download ticket required"}); return

                data = self.gateway.ota.get_firmware_bytes(fn) if hasattr(self.gateway, "ota") else None
                if data:
                    hdr = (f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\n"
                           f"Content-Type: application/octet-stream\r\n"
                           f"Content-Length: {len(data)}\r\n"
                           f"Content-Disposition: attachment; filename=\"{fn}\"\r\n"
                           f"Cache-Control: no-cache, no-store, must-revalidate\r\n"
                           f"Pragma: no-cache\r\n"
                           f"Expires: 0\r\n"
                           f"Connection: close\r\n\r\n").encode()
                    writer.write(hdr)
                    if method == "GET":
                        writer.write(data)
                    await writer.drain()
                    if method == "GET" and req_ticket and self.ota_manager and hasattr(self.ota_manager, "consume_download_ticket"):
                        self.ota_manager.consume_download_ticket(req_ticket)
                    writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/auth/login":
                try:
                    d = json.loads(raw_body)
                    res = await asyncio.to_thread(auth.login, d.get("username", ""), d.get("password", ""))
                except (ValueError, AttributeError, TypeError):
                    await self._respond(writer, 400, {"error": "Invalid login request"}); return
                cookie = ""
                if res.get("success"):
                    cookie = f"Set-Cookie: aetheria_session={res['token']}; Path=/;{secure_attr} HttpOnly; SameSite=Strict; Max-Age={config.SESSION_TTL_SECONDS}\r\n"
                    if origin:
                        res = {k: v for k, v in res.items() if k not in {"token", "api_key"}}
                status = 200 if res.get("success") else (429 if res.get("rate_limited") else 401)
                await self._respond(writer, status, res, cookie); return

            if method == "POST" and path == "/api/auth/register":
                await self._respond(writer, 403, {"error": "Public registration is disabled"}); return

            if method == "GET" and path == "/api/auth/me":
                if current_user:
                    resp_data = {"authenticated": True, "user": current_user}
                else:
                    resp_data = {"authenticated": False}
                body = json.dumps(resp_data).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/auth/logout":
                if token and hasattr(self.gateway, "auth"):
                    self.gateway.auth.logout(token)
                await self._respond(writer, 200, {"success": True}, f"Set-Cookie: aetheria_session=; Path=/;{secure_attr} HttpOnly; SameSite=Strict; Max-Age=0\r\n"); return

            if method in ("GET", "HEAD") and path in ("/downloads/app-release.apk", "/api/app/download", "/downloads/aetheria_home_assistant.apk"):
                apk_paths = [
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "releases", "android", "HomeCompetition.apk"),
                    "/home/pi4/smarthome/apk/app-release.apk",
                    "/home/pi4/apk/app-release.apk",
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apk", "app-release.apk"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apk", "app-release.apk"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "app-release.apk"),
                    "/home/tuan/Home-Assistant-IoT-/apk/app-release.apk",
                ]
                apk_path = next((p for p in apk_paths if os.path.exists(p)), None)
                if apk_path:
                    fsize = os.path.getsize(apk_path)
                    writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/vnd.android.package-archive\r\n"
                                  f"Content-Length: {fsize}\r\n"
                                  f"Content-Disposition: attachment; filename=\"HomeCompetition.apk\"\r\n"
                                  f"Connection: close\r\n\r\n").encode())
                    if method == "GET":
                        with open(apk_path, "rb") as af:
                            while chunk := af.read(65536):
                                writer.write(chunk)
                                await writer.drain()
                    writer.close(); return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/wifi/status":
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    out, _ = await proc.communicate()
                    devices = []
                    for line in out.decode().strip().split("\n"):
                        if line:
                            parts = line.split(":")
                            if len(parts) >= 4:
                                devices.append({"device": parts[0], "type": parts[1], "state": parts[2], "connection": parts[3]})
                    resp_data = {"success": True, "devices": devices}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "GET" and path == "/api/wifi/scan":
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,CHAN", "dev", "wifi", "list",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    out, _ = await proc.communicate()
                    seen = {}
                    for line in out.decode().strip().split("\n"):
                        if line:
                            parts = line.split(":")
                            if len(parts) >= 3:
                                ssid = parts[0].strip()
                                if ssid and ssid != "--" and ssid != "Aetheria-Gateway-Setup":
                                    sig = int(parts[1]) if parts[1].isdigit() else 0
                                    sec = parts[2].strip()
                                    chan = parts[3].strip() if len(parts) > 3 else ""
                                    if ssid not in seen or sig > seen[ssid]["signal"]:
                                        seen[ssid] = {"ssid": ssid, "signal": sig, "security": sec, "channel": chan}
                    wifi_list = sorted(list(seen.values()), key=lambda x: x["signal"], reverse=True)
                    resp_data = {"success": True, "networks": wifi_list}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            if method == "POST" and path == "/api/wifi/connect":
                if not is_commissioning_wifi and (not current_user or current_user.get("role") != "admin"):
                    await self._respond(writer, 403, {"error": "Admin privileges required"}); return
                body = await _read_body()
                try:
                    d = json.loads(body.decode() or "{}")
                    ssid = d.get("ssid", "").strip()
                    password = d.get("password", "").strip()
                    if not ssid:
                        resp_data = {"success": False, "error": "SSID is required"}
                    else:
                        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
                        if password:
                            cmd.extend(["password", password])
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        out, err = await proc.communicate()
                        if proc.returncode == 0:
                            for hs in ("Aetheria-Hotspot", "GW-Setup-Hotspot"):
                                asyncio.create_task(_run_nmcli("con", "down", hs))
                            resp_data = {"success": True, "message": f"Connected to {ssid}"}
                        else:

                            up_proc = await asyncio.create_subprocess_exec(
                                "nmcli", "con", "up", ssid,
                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
                            up_out, up_err = await up_proc.communicate()
                            if up_proc.returncode == 0:
                                for hs in ("Aetheria-Hotspot", "GW-Setup-Hotspot"):
                                    asyncio.create_task(_run_nmcli("con", "down", hs))
                                resp_data = {"success": True, "message": f"Connected to {ssid}"}
                            else:

                                for hs in ("Aetheria-Hotspot", "GW-Setup-Hotspot"):
                                    await _run_nmcli("con", "down", hs)
                                await asyncio.sleep(2)
                                retry_proc = await asyncio.create_subprocess_exec(
                                    *cmd,
                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                                )
                                retry_out, retry_err = await retry_proc.communicate()
                                if retry_proc.returncode == 0:
                                    resp_data = {"success": True, "message": f"Connected to {ssid}"}
                                else:
                                    for hs in ("Aetheria-Hotspot", "GW-Setup-Hotspot"):
                                        asyncio.create_task(_run_nmcli("con", "up", hs))
                                    err_msg = retry_err.decode().strip() or retry_out.decode().strip() or err.decode().strip() or out.decode().strip()
                                    resp_data = {"success": False, "error": err_msg}
                except Exception as e:
                    resp_data = {"success": False, "error": str(e)}
                body = json.dumps(resp_data, ensure_ascii=False).encode()
                writer.write((f"HTTP/1.1 200 OK\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\nReferrer-Policy: no-referrer\r\nContent-Type: application/json\r\n"
                              f"Content-Length: {len(body)}\r\n"
                              f"Connection: close\r\n\r\n").encode() + body)
                await writer.drain(); writer.close(); return

            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain(); writer.close()
        except Exception as e:
            logger.debug(f"HTTP handler exception: {e}")
            try: writer.close()
            except Exception: pass
