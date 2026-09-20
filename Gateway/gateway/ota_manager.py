"""
AETHERIA OS — OTA Firmware Manager
Manages ESP32 firmware binaries, versioning, HTTP push flashing, and MQTT OTA triggers.
"""

import os
import time
import hashlib
import logging
import asyncio
import struct
from typing import Dict, List, Any, Optional
import urllib.request

import config

logger = logging.getLogger("ota_manager")

# ESP-IDF Binary Image Header constants
ESP_IMAGE_MAGIC = 0xE9
CHIP_NAMES = {
    0x0000: "ESP32",
    0x0002: "ESP32-S2",
    0x0005: "ESP32-C3",
    0x0009: "ESP32-S3",
    0x000C: "ESP32-C2",
    0x000D: "ESP32-C6",
    0x0010: "ESP32-H2",
}

class OTAManager:
    """Manages firmware binaries and remote OTA updates for ESP32 nodes."""

    def __init__(self, gateway=None):
        self.gateway = gateway
        self.firmware_dir = getattr(config, "FIRMWARE_DIR", "/home/pi4/Home-Assistant-IoT-/Gateway/firmware")
        try:
            os.makedirs(self.firmware_dir, exist_ok=True)
        except Exception:
            pass
        self._active_tasks: Dict[str, Dict[str, Any]] = {}

    def parse_header(self, file_path: str) -> Dict[str, Any]:
        """Parse ESP-IDF image header from binary file."""
        info = {
            "valid_esp_bin": False,
            "chip": "Unknown",
            "segments": 0,
            "flash_mode": 0,
            "flash_size_freq": 0,
            "entry_point": "0x0"
        }
        try:
            with open(file_path, "rb") as f:
                header = f.read(24)
            if len(header) >= 8 and header[0] == ESP_IMAGE_MAGIC:
                info["valid_esp_bin"] = True
                info["segments"] = header[1]
                info["flash_mode"] = header[2]
                info["flash_size_freq"] = header[3]
                entry = struct.unpack("<I", header[4:8])[0]
                info["entry_point"] = f"0x{entry:08X}"
                if len(header) >= 14:
                    chip_id = struct.unpack("<H", header[12:14])[0]
                    info["chip"] = CHIP_NAMES.get(chip_id, f"Chip 0x{chip_id:04X}")
        except Exception as e:
            logger.debug(f"Failed to parse binary header for {file_path}: {e}")
        return info

    def list_firmwares(self) -> List[Dict[str, Any]]:
        """List all firmware files with metadata."""
        items = []
        if not os.path.exists(self.firmware_dir):
            return items

        for fname in os.listdir(self.firmware_dir):
            if not fname.endswith(".bin"):
                continue
            full_path = os.path.join(self.firmware_dir, fname)
            if not os.path.isfile(full_path):
                continue

            try:
                st = os.stat(full_path)
                with open(full_path, "rb") as f:
                    file_bytes = f.read()
                md5 = hashlib.md5(file_bytes).hexdigest()
                hdr = self.parse_header(full_path)

                items.append({
                    "filename": fname,
                    "size_bytes": st.st_size,
                    "size_kb": round(st.st_size / 1024, 1),
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "md5": md5,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                    "timestamp": st.st_mtime,
                    "valid_esp": hdr["valid_esp_bin"],
                    "chip": hdr["chip"],
                    "entry_point": hdr["entry_point"]
                })
            except Exception as e:
                logger.error(f"Error inspecting firmware {fname}: {e}")

        # Sort newest first
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items

    def save_firmware(self, filename: str, content: bytes) -> Dict[str, Any]:
        """Save an uploaded firmware binary."""
        # Sanitize filename
        safe_name = "".join([c for c in filename if c.isalnum() or c in (".", "_", "-")])
        if not safe_name.endswith(".bin"):
            safe_name += ".bin"

        dest = os.path.join(self.firmware_dir, safe_name)
        with open(dest, "wb") as f:
            f.write(content)

        hdr = self.parse_header(dest)
        md5 = hashlib.md5(content).hexdigest()
        logger.info(f"✅ Saved firmware: {safe_name} ({len(content)} bytes, MD5={md5}, Chip={hdr['chip']})")

        return {
            "filename": safe_name,
            "size_bytes": len(content),
            "md5": md5,
            "valid_esp": hdr["valid_esp_bin"],
            "chip": hdr["chip"]
        }

    def delete_firmware(self, filename: str) -> bool:
        """Delete a firmware file."""
        safe_name = os.path.basename(filename)
        path = os.path.join(self.firmware_dir, safe_name)
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"🗑️ Deleted firmware: {safe_name}")
            return True
        return False

    def get_firmware_bytes(self, filename: str) -> Optional[bytes]:
        """Read firmware file bytes for download."""
        safe_name = os.path.basename(filename)
        path = os.path.join(self.firmware_dir, safe_name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return None

    async def flash_via_http(self, target_ip: str, filename: str, node_id: str = "node") -> Dict[str, Any]:
        """
        Push firmware directly to ESP32 Web Server /ota endpoint via HTTP POST.
        ESP32-S3 Master runs an internal HTTP server with Web OTA handler on port 80.
        """
        fw_bytes = self.get_firmware_bytes(filename)
        if not fw_bytes:
            return {"success": False, "error": f"Firmware file not found: {filename}"}

        endpoints = [f"http://{target_ip}:80/update", f"http://{target_ip}:80/ota"]
        task_id = f"{node_id}_{int(time.time())}"
        self._active_tasks[task_id] = {
            "node_id": node_id,
            "target_ip": target_ip,
            "filename": filename,
            "status": "flashing",
            "progress": 0,
            "start_time": time.time()
        }

        def _do_post():
            last_err = ""
            for url in endpoints:
                try:
                    logger.info(f"🚀 [OTA HTTP Flash] Trying endpoint {url} (node: {node_id}, size: {len(fw_bytes)}B)...")
                    req = urllib.request.Request(
                        url,
                        data=fw_bytes,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(len(fw_bytes)),
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        code = resp.getcode()
                        resp_body = resp.read().decode("utf-8", errors="replace")
                        return code, resp_body
                except urllib.error.HTTPError as he:
                    if he.code == 404:
                        last_err = f"HTTP 404 on {url}"
                        continue
                    return he.code, str(he)
                except Exception as e:
                    last_err = str(e)
            return 0, last_err

        code, body = await asyncio.to_thread(_do_post)

        if code in (200, 201) or "Successful" in body:
            self._active_tasks[task_id]["status"] = "success"
            self._active_tasks[task_id]["progress"] = 100
            logger.info(f"✨ [OTA HTTP Flash] Completed successfully for {node_id} ({target_ip})!")
            if hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("ota_progress", {
                    "node_id": node_id,
                    "progress": 100,
                    "status": "success",
                    "message": "Cập nhật OTA thành công! Thiết bị đang khởi động lại..."
                })
            return {"success": True, "message": "OTA Flashed successfully! Node is rebooting."}
        else:
            self._active_tasks[task_id]["status"] = "failed"
            logger.error(f"❌ [OTA HTTP Flash] Failed for {node_id} ({target_ip}): {body}")
            if hasattr(self.gateway, "broadcast_event"):
                self.gateway.broadcast_event("ota_progress", {
                    "node_id": node_id,
                    "progress": 0,
                    "status": "failed",
                    "message": f"Lỗi nạp OTA: {body[:80]}"
                })
            return {"success": False, "error": body}

    def get_gateway_lan_ip(self) -> str:
        """Automatically detect the real LAN IP of this Gateway reachable by ESP32 devices."""
        # 1. Check if explicitly configured in config
        if hasattr(config, "GATEWAY_IP") and config.GATEWAY_IP and config.GATEWAY_IP != "0.0.0.0":
            return config.GATEWAY_IP
        # 2. Open a dummy UDP socket to query routing table for local interface IP
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass
        return "192.168.1.1"

    def update_task_progress(self, node_id: str, progress: int, status: str, message: str = ""):
        """Update live progress of an active OTA task."""
        task_id = f"ota_{node_id}"
        self._active_tasks[task_id] = {
            "node_id": node_id,
            "status": status,
            "progress": progress,
            "message": message,
            "updated_at": time.time()
        }
        if hasattr(self.gateway, "registry") and hasattr(self.gateway.registry, "record_ota_history"):
            try:
                self.gateway.registry.record_ota_history(node_id, "esp32s3_master_latest.bin", status, progress=progress, message=message)
            except Exception:
                pass

    async def trigger_via_mqtt(self, node_id: str, filename: str, gateway_ip: str = None) -> Dict[str, Any]:
        """
        Trigger pull OTA via MQTT and WebSocket dual-channel command.
        ESP32 node connects back to Gateway to stream firmware and flash.
        """
        import json
        fw_bytes = self.get_firmware_bytes(filename)
        if not fw_bytes:
            return {"success": False, "error": f"Firmware file not found: {filename}"}

        if not gateway_ip or gateway_ip in ("0.0.0.0", "127.0.0.1", "localhost"):
            gateway_ip = self.get_gateway_lan_ip()

        md5 = hashlib.md5(fw_bytes).hexdigest()
        download_url = f"http://{gateway_ip}:{config.WEB_PORT}/api/ota/download/{filename}"
        
        payload = {
            "cmd": "ota_start",
            "url": download_url,
            "version": filename.replace(".bin", ""),
            "size": len(fw_bytes),
            "md5": md5
        }

        # 1. Publish to MQTT topics (both compact and industrial)
        topic = f"smarthome/ota/{node_id}"
        mqtt_sent = False
        if hasattr(self.gateway, "mqtt") and self.gateway.mqtt:
            try:
                await self.gateway.mqtt.publish(topic, payload, qos=1)
                if node_id != "all":
                    ind_ota_top = f"home/devices/{node_id}/ota/trigger"
                    await self.gateway.mqtt.publish(ind_ota_top, payload, qos=1)
                logger.info(f"📢 [OTA MQTT Trigger] Published OTA command to {topic}: {download_url}")
                mqtt_sent = True
            except Exception as e:
                logger.error(f"Failed to publish OTA command via MQTT: {e}")

        # 2. Also send over active WebSocket if connected
        ws_sent = False
        if hasattr(self.gateway, "audio_server") and self.gateway.audio_server:
            ws_targets = []
            if node_id == "all":
                ws_targets = list(self.gateway.audio_server._active_speakers)
            else:
                ws = self.gateway.audio_server._ws_nodes.get(node_id)
                if ws:
                    ws_targets = [ws]
                elif len(self.gateway.audio_server._ws_nodes) == 1:
                    ws_targets = list(self.gateway.audio_server._ws_nodes.values())
                elif self.gateway.audio_server._active_speakers:
                    ws_targets = list(self.gateway.audio_server._active_speakers)

            ws_msg = json.dumps({
                "t": "ota",
                "url": download_url,
                "size": len(fw_bytes),
                "md5": md5
            })
            for ws in ws_targets:
                if self.gateway.audio_server._is_ws_alive(ws):
                    try:
                        asyncio.create_task(ws.send(ws_msg))
                        ws_sent = True
                        logger.info(f"📢 [OTA WS Trigger] Sent OTA command to node '{node_id}' over WebSocket")
                    except Exception as e:
                        logger.warning(f"Could not send OTA over WebSocket: {e}")

        # 3. Broadcast initial progress event to Web UI SSE
        if hasattr(self.gateway, "broadcast_event"):
            self.gateway.broadcast_event("ota_progress", {
                "node_id": node_id,
                "progress": 0,
                "status": "starting",
                "message": f"Đã phát lệnh nạp {filename} (từ {gateway_ip}). Đang chờ ESP32 kết nối..."
            })

        self.update_task_progress(node_id, 0, "starting", f"Đã gửi lệnh nạp {filename} tới {node_id}")
        if hasattr(self.gateway, "registry") and hasattr(self.gateway.registry, "record_ota_history"):
            try:
                self.gateway.registry.record_ota_history(node_id, filename, "starting", progress=0, message=f"Đã phát lệnh nạp {filename}")
            except Exception:
                pass

        if mqtt_sent or ws_sent:
            return {"success": True, "topic": topic, "url": download_url, "size": len(fw_bytes), "md5": md5}
        else:
            return {"success": False, "error": "Neither MQTT nor WebSocket client available to send OTA command"}
