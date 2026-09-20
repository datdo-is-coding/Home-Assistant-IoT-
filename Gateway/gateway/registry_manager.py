"""
Device Registry Manager v2 — quản lý theo phòng + fullname + provision flow.

- Mỗi node: id = {room}-{short}  e.g. livingroom-node01, bedroom-node02
- Mỗi relay: fullname = {node_id}-{dev} e.g. livingroom-node01-light
- ESP32 lưu {node_id, room, rl1, rl2, cfg_version} vào NVS và echo lại mỗi hello.
- Node mới (cfg==null) vào hàng chờ pending → WebUI đăng ký → Gateway gửi cfg.

Tương thích ngược: tự migrate file cũ (area/channels) sang schema mới khi load.
"""
import json
import os
import re
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

import config

logger = logging.getLogger("registry")
TZ_VN = timezone(timedelta(hours=7))

# ── Chuẩn hoá ────────────────────────────────────────────────────────────────
_slug_re = re.compile(r"[^a-z0-9]+")
def slug(s: str) -> str:
    s = (s or "").lower().strip()
    # bỏ dấu tiếng Việt cơ bản
    tbl = str.maketrans("áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
                        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd")
    s = s.translate(tbl)
    s = _slug_re.sub("_", s).strip("_")
    return s or "unknown"

DEVICE_CANON = {
    "den": "light", "light": "light", "bong_den": "light",
    "quat": "fan", "fan": "fan",
    "bom": "pump", "may_bom": "pump", "pump": "pump",
    "rem": "curtain", "man": "curtain",
}
def canon_device(s: str) -> str:
    s = slug(s)
    return DEVICE_CANON.get(s, s)

ROOM_ALIASES = {
    "phong_khach": ["phong_khach", "livingroom", "living_room", "khach", "p_khach"],
    "phong_ngu":   ["phong_ngu", "bedroom", "ngu", "p_ngu"],
    "phong_bep":   ["phong_bep", "kitchen", "bep"],
    "phong_tam":   ["phong_tam", "bathroom", "tam", "wc"],
    "ban_cong":    ["ban_cong", "balcony"],
    "san_vuon":    ["san_vuon", "garden", "vuon"],
}

class RegistryManager:
    def __init__(self, registry_path: str = None):
        self.path = registry_path or config.REGISTRY_FILE
        self.db_path = getattr(config, "GATEWAY_DB", "/var/lib/smarthome/gateway.db")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        except Exception:
            pass
        self.data: Dict[str, Any] = {"nodes": {}, "pending": {}, "rooms": {}}
        self._seq: Dict[str, int] = {}  # node_id -> last seq
        self._init_sqlite()
        self.load()

    # ── SQLite Database Storage Engine (Spec Section 8) ──────────────────
    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_sqlite(self):
        try:
            with self._get_db() as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id VARCHAR(32) PRIMARY KEY,
                    display_name VARCHAR(64) NOT NULL,
                    floor_level INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS devices (
                    device_id VARCHAR(32) PRIMARY KEY,
                    hardware_id VARCHAR(32) NOT NULL,
                    serial_number VARCHAR(32) UNIQUE NOT NULL,
                    device_type VARCHAR(24) NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    room_id VARCHAR(32),
                    location VARCHAR(128),
                    description TEXT,
                    mac_address VARCHAR(18) NOT NULL,
                    ip_address VARCHAR(15),
                    rssi INTEGER,
                    status VARCHAR(16) DEFAULT 'UNPROVISIONED',
                    protocol_version INTEGER DEFAULT 1,
                    firmware_version VARCHAR(24) DEFAULT '1.0.0',
                    desired_config_version INTEGER DEFAULT 1,
                    reported_config_version INTEGER DEFAULT 0,
                    sync_status VARCHAR(16) DEFAULT 'SYNCING',
                    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS device_configs (
                    device_id VARCHAR(32) PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
                    desired_json TEXT NOT NULL,
                    reported_json TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS device_capabilities (
                    device_id VARCHAR(32) PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
                    has_voice BOOLEAN DEFAULT FALSE,
                    has_speaker BOOLEAN DEFAULT FALSE,
                    has_opus BOOLEAN DEFAULT FALSE,
                    has_wake_word BOOLEAN DEFAULT FALSE,
                    has_energy_meter BOOLEAN DEFAULT FALSE,
                    relay_channels INTEGER DEFAULT 0,
                    raw_capabilities_json TEXT
                );

                CREATE TABLE IF NOT EXISTS ota_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(32),
                    from_version VARCHAR(24),
                    to_version VARCHAR(24),
                    firmware_file VARCHAR(128),
                    file_sha256 VARCHAR(64),
                    status VARCHAR(16),
                    error_message TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                );

                CREATE TABLE IF NOT EXISTS telemetry_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(32),
                    voltage REAL,
                    current REAL,
                    power REAL,
                    energy REAL,
                    free_heap INTEGER,
                    wifi_rssi INTEGER,
                    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_dev_time ON telemetry_records(device_id, recorded_at);
                """)
            logger.info(f"✨ SQLite Gateway Registry initialized: {self.db_path} (WAL Mode)")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite Registry at {self.db_path}: {e}")

    def _sync_node_to_sqlite(self, nid: str, n: dict):
        """Đồng bộ một node vào bảng devices và capabilities của SQLite."""
        try:
            now = datetime.now(TZ_VN).isoformat()
            hw = n.get("firmware", {}).get("hardware", n.get("hardware", "esp32s3"))
            serial = n.get("firmware", {}).get("serial", n.get("serial", f"S3-2026-{nid[-6:]}"))
            caps = n.get("capabilities", [])
            dev_type = "voice_node" if "voice_wake" in caps or "microphone" in caps else "relay_node"
            name = n.get("name", nid)
            room = n.get("room", "unknown")
            location = n.get("location", "")
            description = n.get("description", "")
            mac = n.get("address", {}).get("mac", n.get("mac", ""))
            ip = n.get("address", {}).get("ip", n.get("ip", ""))
            rssi = n.get("address", {}).get("rssi", n.get("rssi"))
            status = n.get("status", "online")
            des_ver = n.get("desired_config_version", n.get("cfg_version", 1))
            rep_ver = n.get("reported_config_version", des_ver)
            sync_st = n.get("sync_status", "SYNCED")
            last_seen = n.get("last_seen", now)

            with self._get_db() as conn:
                if room and room != "unknown":
                    conn.execute("""
                        INSERT OR IGNORE INTO rooms (room_id, display_name)
                        VALUES (?, ?)
                    """, (room, room.replace("_", " ").title()))

                conn.execute("""
                    INSERT INTO devices (
                        device_id, hardware_id, serial_number, device_type,
                        name, room_id, location, description,
                        mac_address, ip_address, rssi, status,
                        desired_config_version, reported_config_version, sync_status,
                        last_seen, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        name = excluded.name,
                        room_id = excluded.room_id,
                        location = excluded.location,
                        description = excluded.description,
                        ip_address = excluded.ip_address,
                        rssi = excluded.rssi,
                        status = excluded.status,
                        desired_config_version = excluded.desired_config_version,
                        reported_config_version = excluded.reported_config_version,
                        sync_status = excluded.sync_status,
                        last_seen = excluded.last_seen,
                        updated_at = excluded.updated_at
                """, (
                    nid, hw, serial, dev_type,
                    name, room, location, description,
                    mac, ip, rssi, status,
                    des_ver, rep_ver, sync_st,
                    last_seen, now
                ))

                has_voice = "voice_wake" in caps or "microphone" in caps
                has_spk = "audio_speaker" in caps
                conn.execute("""
                    INSERT INTO device_capabilities (
                        device_id, has_voice, has_speaker, has_opus, has_wake_word,
                        has_energy_meter, relay_channels, raw_capabilities_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        has_voice = excluded.has_voice,
                        has_speaker = excluded.has_speaker,
                        relay_channels = excluded.relay_channels,
                        raw_capabilities_json = excluded.raw_capabilities_json
                """, (
                    nid, has_voice, has_spk, True, has_voice,
                    True, 2, json.dumps(caps, ensure_ascii=False)
                ))
        except Exception as e:
            logger.warning(f"_sync_node_to_sqlite error for {nid}: {e}")

    # ── Persistence ─────────────────────────────────────────────────────
    def load(self):
        # 1. Load JSON file first if available
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if "nodes" in raw:
                self.data["nodes"] = raw.get("nodes", {})
                self.data["pending"] = raw.get("pending", {})
                self.data["rooms"] = raw.get("rooms", {})
                for nid, n in list(self.data["nodes"].items()):
                    self._migrate_node(nid, n)
                self._rebuild_rooms()
                logger.info(f"Registry loaded: {len(self.data['nodes'])} nodes, {len(self.data['pending'])} pending")
            else:
                self.data = {"nodes": {}, "pending": {}, "rooms": {}}
        else:
            self.save()
            logger.info("Created empty registry v2")

        # 2. Check SQLite: Auto-migration or sync
        try:
            with self._get_db() as conn:
                cur = conn.execute("SELECT count(*) as cnt FROM devices")
                cnt = cur.fetchone()["cnt"]
                if cnt == 0 and self.data["nodes"]:
                    logger.info(f"Auto-migrating {len(self.data['nodes'])} nodes from JSON to SQLite...")
                    for nid, n in self.data["nodes"].items():
                        self._sync_node_to_sqlite(nid, n)
                elif cnt > 0:
                    cur = conn.execute("SELECT * FROM devices")
                    for row in cur.fetchall():
                        did = row["device_id"]
                        if did in self.data["nodes"]:
                            n = self.data["nodes"][did]
                            n["desired_config_version"] = row["desired_config_version"]
                            n["reported_config_version"] = row["reported_config_version"]
                            n["sync_status"] = row["sync_status"]
                            n["serial"] = row["serial_number"]
                            n["location"] = row["location"] or n.get("location", "")
                            n["description"] = row["description"] or n.get("description", "")
        except Exception as e:
            logger.warning(f"SQLite sync in load() failed: {e}")

    def _migrate_node(self, nid: str, n: dict):
        if "room" not in n and "area" in n:
            n["room"] = slug(n.pop("area"))
        n.setdefault("room", "unknown")
        n.setdefault("aliases", [])
        n.setdefault("cfg_version", 1)
        n.setdefault("desired_config_version", n.get("cfg_version", 1))
        n.setdefault("reported_config_version", n.get("cfg_version", 1))
        n.setdefault("sync_status", "SYNCED")
        n.setdefault("status", "online")
        n.setdefault("mac", n.get("mac", ""))
        for ch_id, ch in list(n.get("channels", {}).items()):
            if "device_type" in ch:
                dt = canon_device(ch["device_type"])
                ch["device_type"] = dt
                ch.setdefault("fullname", f"{nid}-{dt}")
                ch.setdefault("aliases", [])
        n.setdefault("last_seen", datetime.now(TZ_VN).isoformat())

    def _rebuild_rooms(self):
        rooms: Dict[str, List[str]] = {}
        for nid, n in self.data["nodes"].items():
            r = n.get("room", "unknown")
            rooms.setdefault(r, []).append(nid)
        self.data["rooms"] = rooms

    def save(self):
        self._rebuild_rooms()
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)
        # Sync all nodes to SQLite
        for nid, n in self.data["nodes"].items():
            self._sync_node_to_sqlite(nid, n)

    # ── HELLO / Pending flow ────────────────────────────────────────────
    def on_hello(self, payload: dict, ws_available: bool = False) -> dict:
        """
        Xử lý gói tin hello thương mại từ ESP32:
        {"t":"hello", "id":..., "mac":..., "hardware":..., "serial":..., "state":..., "rl":[...], "cfg":n, ...}
        """
        mac = (payload.get("mac") or "").upper()
        node_id = payload.get("id") or payload.get("device_id")
        hardware = payload.get("hardware", "esp32s3")
        serial = payload.get("serial", "S3-2026-000000")
        state = payload.get("state", "READY")
        cfg = payload.get("cfg")
        rl = payload.get("rl", [0, 0])
        rssi = payload.get("rssi")
        ip = payload.get("ip")
        now = datetime.now(TZ_VN).isoformat()

        # Check if node is unprovisioned or in FACTORY_NEW state:
        is_factory = (state == "FACTORY_NEW" or cfg is None or (node_id and node_id not in self.data["nodes"]))
        if is_factory:
            clean_mac = mac.replace(":", "").lower()
            pending_key = node_id or (f"node_{clean_mac[-8:]}" if clean_mac else "unknown")

            # Khử trùng lặp triệt để: Xóa bất kỳ entry pending cũ nào có cùng MAC hoặc cùng ID
            if mac:
                for k, v in list(self.data["pending"].items()):
                    if k == pending_key:
                        continue
                    if k.upper() == mac.upper() or (v.get("mac") and v.get("mac").upper() == mac.upper()):
                        del self.data["pending"][k]

            self.data["pending"][pending_key] = {
                "device_id": pending_key,
                "mac": mac,
                "hardware": hardware,
                "serial": serial,
                "state": state or "FACTORY_NEW",
                "ip": ip,
                "rssi": rssi,
                "rl": rl,
                "cfg": cfg,
                "last_seen": now,
                "ws_available": ws_available
            }
            self.save()
            logger.info(f"📦 [Registry] Pending device: ID={pending_key}, MAC={mac}, Serial={serial}, State={state}")
            return {"action": "pending", "node_id": pending_key, "mac": mac}

        # Đã provision và có trong registry → update heartbeat & address block
        if node_id and node_id in self.data["nodes"]:
            # Đảm bảo dọn sạch bất kỳ pending entry nào còn sót lại của node này
            if mac:
                for k, v in list(self.data["pending"].items()):
                    if k.upper() == mac.upper() or (v.get("mac") and v.get("mac").upper() == mac.upper()) or k == node_id:
                        del self.data["pending"][k]
            elif node_id in self.data["pending"]:
                del self.data["pending"][node_id]

            n = self.data["nodes"][node_id]
            n["last_seen"] = now
            n["status"] = "online"
            if rssi is not None: n["rssi"] = rssi
            if ip: n["ip"] = ip
            n["relay_state"] = rl

            # Đồng bộ cấu trúc Image 1
            if "address" not in n:
                n["address"] = {}
            n["address"]["ip"] = ip or n["address"].get("ip")
            n["address"]["mac"] = mac or n["address"].get("mac")
            n["address"]["rssi"] = rssi if rssi is not None else n["address"].get("rssi")
            n["address"]["last_seen"] = now

            if "firmware" not in n:
                n["firmware"] = {}
            n["firmware"]["hardware"] = hardware
            n["firmware"]["serial"] = serial

            expected = n.get("configuration", {}).get("cfg_version") or n.get("cfg_version", 1)
            if cfg is not None and cfg != expected:
                if cfg > expected:
                    # Node đã được cập nhật hoặc apply Desired Twin thành công -> Gateway đồng bộ theo node
                    if "configuration" not in n:
                        n["configuration"] = {}
                    n["configuration"]["cfg_version"] = cfg
                    n["cfg_version"] = cfg
                    n["reported_config_version"] = cfg
                    n["sync_status"] = "SYNCED"
                    logger.info(f"🔄 Auto-synced node {node_id} registry version to node's newer cfg={cfg}")
                    self.save()
                    return {"action": "known", "node_id": node_id}
                else:
                    logger.warning(f"cfg mismatch {node_id}: node cfg={cfg} expected={expected} → will re-provision")
                    self.save()
                    return {"action": "cfg_mismatch", "node_id": node_id, "expected": expected, "got": cfg}
            self.save()
            return {"action": "known", "node_id": node_id}

        # Chưa biết → lưu vào pending
        pending_key = node_id or (f"node_{mac.replace(':', '').lower()[-8:]}" if mac else "unknown_node")
        if mac:
            for k, v in list(self.data["pending"].items()):
                if k != pending_key and (k.upper() == mac.upper() or (v.get("mac") and v.get("mac").upper() == mac.upper())):
                    del self.data["pending"][k]

        self.data["pending"][pending_key] = {
            "device_id": pending_key, "mac": mac, "hardware": hardware,
            "serial": serial, "state": state, "ip": ip, "rssi": rssi,
            "rl": rl, "cfg": cfg, "last_seen": now, "ws_available": ws_available
        }
        self.save()
        return {"action": "pending", "node_id": pending_key}

    def update_relay_state(self, node_id: str, rl: list) -> bool:
        """Cập nhật trạng thái relay thực tế vào registry và lưu tức thì."""
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["relay_state"] = list(rl)
            self.save()
            return True
        return False

    def delete_node(self, node_id: str) -> bool:
        """Xóa hoàn toàn một thiết bị khỏi registry và SQLite."""
        deleted = False
        if node_id in self.data["nodes"]:
            n = self.data["nodes"].pop(node_id)
            deleted = True
            mac = n.get("address", {}).get("mac") or n.get("mac")
            if mac:
                for k, v in list(self.data["pending"].items()):
                    if (v.get("mac") and v.get("mac").upper() == mac.upper()) or k.upper() == mac.upper():
                        del self.data["pending"][k]

        if node_id in self.data["pending"]:
            del self.data["pending"][node_id]
            deleted = True

        try:
            with self._get_db() as conn:
                conn.execute("DELETE FROM devices WHERE device_id = ?", (node_id,))
                conn.execute("DELETE FROM device_configs WHERE device_id = ?", (node_id,))
                conn.execute("DELETE FROM device_capabilities WHERE device_id = ?", (node_id,))
                conn.commit()
            deleted = True
        except Exception as e:
            logger.error(f"Failed to delete node {node_id} from SQLite: {e}")

        self.save()
        logger.info(f"🗑️ [Registry] Deleted device: {node_id}")
        return deleted

    def provision_node(self, mac_or_id: str, room: str, rl1: str = "light", rl2: str = "fan",
                       node_short: str = None, description: str = None,
                       name: str = None, location: str = None) -> Optional[dict]:
        """
        WebUI gọi khi user gán tên + phòng + vị trí cho node pending.
        Tuân thủ chặt chẽ schema Image 1:
        - device_id (khóa chính)
        - name, room, location, description
        - address, capabilities, firmware, configuration, security
        """
        pending = None
        target_key = None
        matched_keys = []
        for k, p in list(self.data["pending"].items()):
            if k == mac_or_id or p.get("mac", "").upper() == mac_or_id.upper() or p.get("device_id") == mac_or_id:
                if pending is None:
                    pending = p
                    target_key = k
                matched_keys.append(k)

        # Xóa tất cả các entry pending trùng lặp
        for k in matched_keys:
            self.data["pending"].pop(k, None)

        if not pending and mac_or_id in self.data["nodes"]:
            pending = self.data["nodes"][mac_or_id]

        if not pending:
            # Fallback for manual addition: create minimal pending descriptor
            actual_id = mac_or_id if mac_or_id.startswith("node_") else (f"node_{mac_or_id.replace(':', '').lower()[-8:]}" if ":" in mac_or_id else f"node_{mac_or_id.lower()}")
            mac = mac_or_id.upper() if ":" in mac_or_id else ""
            pending = {
                "device_id": actual_id,
                "mac": mac,
                "hardware": "esp32s3",
                "serial": "S3-2026-000001",
                "state": "READY",
                "ip": None,
                "rssi": None,
                "rl": [0, 0]
            }

        # Dọn sạch thêm nếu còn entry nào có cùng MAC
        if pending.get("mac"):
            pmac = pending["mac"].upper()
            for k, p in list(self.data["pending"].items()):
                if (p.get("mac") and p.get("mac").upper() == pmac) or k.upper() == pmac:
                    self.data["pending"].pop(k, None)

        actual_id = pending.get("device_id") or mac_or_id
        mac = (pending.get("mac") or "").upper()
        hardware = pending.get("hardware", "esp32s3")
        serial = pending.get("serial", "S3-2026-000000")
        ip = pending.get("ip")
        rssi = pending.get("rssi")
        rl = pending.get("rl", [0, 0])

        room_s = slug(room)
        rl1_c = canon_device(rl1) if rl1 else "light"
        rl2_c = canon_device(rl2) if rl2 else "fan"

        dev_name = name or f"Loa {room_s.replace('_', ' ').title()}"
        dev_loc = location or f"Phòng {room_s.replace('_', ' ').title()}"
        dev_desc = description or "ESP32-S3 Voice & Smart Hub"

        now = datetime.now(TZ_VN).isoformat()
        channels: Dict[str, dict] = {
            "ch1": {
                "device_type": rl1_c, "fullname": f"{actual_id}-{rl1_c}",
                "name": rl1 or "Đèn", "aliases": [rl1_c], "gpio": 4, "rated_watts": 40,
                "description": rl1_c
            },
            "ch2": {
                "device_type": rl2_c, "fullname": f"{actual_id}-{rl2_c}",
                "name": rl2 or "Quạt", "aliases": [rl2_c], "gpio": 5, "rated_watts": 55,
                "description": rl2_c
            }
        }

        # Commercial Node Schema (Image 1)
        self.data["nodes"][actual_id] = {
            "device_id": actual_id,
            "name": dev_name,
            "room": room_s,
            "location": dev_loc,
            "description": dev_desc,
            "address": {
                "ip": ip,
                "mac": mac,
                "rssi": rssi,
                "last_seen": now
            },
            "capabilities": [
                "voice_wake", "audio_speaker", "microphone", "relay_2ch", "energy_monitor", "ota"
            ],
            "firmware": {
                "version": "2.1.0",
                "hardware": hardware,
                "serial": serial,
                "build_date": "2026-09-19"
            },
            "configuration": {
                "relays": {
                    "ch1": {"device_type": rl1_c, "fullname": f"{actual_id}-{rl1_c}", "name": rl1 or "Đèn", "gpio": 4},
                    "ch2": {"device_type": rl2_c, "fullname": f"{actual_id}-{rl2_c}", "name": rl2 or "Quạt", "gpio": 5}
                },
                "audio": {"sample_rate": 16000, "volume": 85},
                "cfg_version": 1
            },
            "security": {
                "state": "READY",
                "claimed_at": now
            },
            # Flat backwards compatibility fields:
            "node_id": actual_id,
            "mac": mac,
            "ip": ip,
            "rssi": rssi,
            "relay_state": rl,
            "status": "online",
            "last_seen": now,
            "cfg_version": 1,
            "channels": channels,
            "aliases": ROOM_ALIASES.get(room_s, [room_s])
        }

        self.save()
        logger.info(f"✨ Commercial Provisioned: {actual_id} -> Name='{dev_name}', Room='{room_s}', Serial='{serial}'")
        return self.data["nodes"][actual_id] | {"node_id": actual_id, "room_s": room_s, "rl1": rl1_c, "rl2": rl2_c}

    def update_device(self, device_id: str, d: dict) -> dict:
        """Cập nhật thông tin thân thiện (name, room, location, channels) của node."""
        if device_id not in self.data["nodes"]:
            raise ValueError(f"Thiết bị {device_id} không tồn tại trong hệ thống")

        n = self.data["nodes"][device_id]
        if "name" in d and d["name"]:
            n["name"] = str(d["name"]).strip()
        if "room" in d and d["room"]:
            rm = slug(d["room"])
            n["room"] = rm
            n["aliases"] = ROOM_ALIASES.get(rm, [rm])
        if "location" in d and d["location"] is not None:
            n["location"] = str(d["location"]).strip()
        if "description" in d and d["description"] is not None:
            n["description"] = str(d["description"]).strip()

        # Update channels if provided
        ch1_type = d.get("ch1_type") or d.get("rl1")
        ch1_name = d.get("ch1_name")
        ch2_type = d.get("ch2_type") or d.get("rl2")
        ch2_name = d.get("ch2_name")

        if "channels" not in n:
            n["channels"] = {}

        if ch1_type or ch1_name:
            ch1 = n["channels"].setdefault("ch1", {})
            if ch1_type:
                dt = canon_device(ch1_type)
                ch1["device_type"] = dt
                ch1["fullname"] = f"{device_id}-{dt}"
                ch1["aliases"] = [dt]
            if ch1_name:
                ch1["name"] = ch1_name

        if ch2_type or ch2_name:
            ch2 = n["channels"].setdefault("ch2", {})
            if ch2_type:
                dt = canon_device(ch2_type)
                ch2["device_type"] = dt
                ch2["fullname"] = f"{device_id}-{dt}"
                ch2["aliases"] = [dt]
            if ch2_name:
                ch2["name"] = ch2_name

        # Increment configuration version for Twin Sync
        cur_v = n.get("cfg_version", 1) + 1
        n["cfg_version"] = cur_v
        n["desired_config_version"] = cur_v
        n["sync_status"] = "SYNCING"
        n["last_seen"] = datetime.now(TZ_VN).isoformat()

        # Update configuration dictionary
        if "configuration" not in n:
            n["configuration"] = {"relays": {}, "audio": {"sample_rate": 16000, "volume": 85}}
        n["configuration"]["cfg_version"] = cur_v
        relays = n["configuration"].setdefault("relays", {})
        if "ch1" in n["channels"]:
            relays["ch1"] = {
                "device_type": n["channels"]["ch1"].get("device_type", "light"),
                "fullname": n["channels"]["ch1"].get("fullname", f"{device_id}-light"),
                "name": n["channels"]["ch1"].get("name", "Đèn"),
                "gpio": n["channels"]["ch1"].get("gpio", 4)
            }
        if "ch2" in n["channels"]:
            relays["ch2"] = {
                "device_type": n["channels"]["ch2"].get("device_type", "fan"),
                "fullname": n["channels"]["ch2"].get("fullname", f"{device_id}-fan"),
                "name": n["channels"]["ch2"].get("name", "Quạt"),
                "gpio": n["channels"]["ch2"].get("gpio", 5)
            }

        self.save()
        logger.info(f"✏️ [Registry] Updated device {device_id}: name='{n.get('name')}', room='{n.get('room')}', v={cur_v}")
        return n

    def get_provision_payload(self, node_id: str) -> Optional[dict]:
        """Payload cfg gửi xuống ESP32 theo đúng User Identity"""
        n = self.data["nodes"].get(node_id)
        if not n: return None
        cfg = n.get("configuration", {})
        relays = cfg.get("relays", {})
        ch1 = relays.get("ch1", {})
        ch2 = relays.get("ch2", {})
        return {
            "t": "cfg",
            "id": node_id,
            "name": n.get("name", "Voice Node"),
            "room": n.get("room", "unknown"),
            "location": n.get("location", ""),
            "description": n.get("description", ""),
            "rl1": ch1.get("device_type", "light"),
            "rl2": ch2.get("device_type", "fan"),
            "v": cfg.get("cfg_version", n.get("cfg_version", 1))
        }

    def bump_cfg_version(self, node_id: str) -> int:
        n = self.data["nodes"].get(node_id)
        if not n: return 0
        cur = n.get("configuration", {}).get("cfg_version") or n.get("cfg_version", 1)
        new_v = int(cur) + 1
        if "configuration" in n:
            n["configuration"]["cfg_version"] = new_v
        n["cfg_version"] = new_v
        n["desired_config_version"] = new_v
        n["sync_status"] = "SYNCING"
        self.save()
        return new_v

    # ── Device OS Twin: Desired / Reported Config (Spec Section 4 & 8) ─
    def update_desired_config(self, device_id: str, desired_dict: dict) -> Tuple[int, dict]:
        """
        Cập nhật Desired Configuration từ Gateway/User.
        - Tăng desired_config_version
        - Chuyển sync_status = 'SYNCING'
        - Lưu SQLite và JSON
        - Trả về (desired_config_version, payload_gửi_mqtt)
        """
        now = datetime.now(TZ_VN).isoformat()
        n = self.data["nodes"].get(device_id)
        if not n:
            # Tạo node tối thiểu nếu chưa có
            n = {
                "device_id": device_id,
                "name": desired_dict.get("name", f"Node {device_id}"),
                "room": desired_dict.get("room", "unknown"),
                "status": "online",
                "desired_config_version": 0,
                "reported_config_version": 0,
                "sync_status": "SYNCING"
            }
            self.data["nodes"][device_id] = n

        cur_v = int(n.get("desired_config_version", n.get("cfg_version", 1)))
        new_v = cur_v + 1
        n["desired_config_version"] = new_v
        n["cfg_version"] = new_v
        n["sync_status"] = "SYNCING"
        n["updated_at"] = now

        # Cập nhật identity fields nếu có trong desired_dict
        if "name" in desired_dict: n["name"] = desired_dict["name"]
        if "room" in desired_dict:
            n["room"] = slug(desired_dict["room"])
            n["aliases"] = ROOM_ALIASES.get(n["room"], [n["room"]])
        if "location" in desired_dict: n["location"] = desired_dict["location"]
        if "description" in desired_dict: n["description"] = desired_dict["description"]

        # Cập nhật relays configuration
        rl1 = desired_dict.get("rl1", desired_dict.get("relay1"))
        rl2 = desired_dict.get("rl2", desired_dict.get("relay2"))
        if rl1 or rl2:
            rl1_c = canon_device(rl1) if rl1 else "light"
            rl2_c = canon_device(rl2) if rl2 else "fan"
            n.setdefault("channels", {})
            n["channels"]["ch1"] = {
                "device_type": rl1_c, "fullname": f"{device_id}-{rl1_c}",
                "name": rl1 or "Đèn", "aliases": [rl1_c], "gpio": 4, "rated_watts": 40
            }
            n["channels"]["ch2"] = {
                "device_type": rl2_c, "fullname": f"{device_id}-{rl2_c}",
                "name": rl2 or "Quạt", "aliases": [rl2_c], "gpio": 5, "rated_watts": 55
            }
            n.setdefault("configuration", {})["relays"] = {
                "ch1": {"device_type": rl1_c, "fullname": f"{device_id}-{rl1_c}", "name": rl1 or "Đèn", "gpio": 4},
                "ch2": {"device_type": rl2_c, "fullname": f"{device_id}-{rl2_c}", "name": rl2 or "Quạt", "gpio": 5}
            }

        # Đảm bảo node tồn tại trong bảng devices của SQLite
        self._sync_node_to_sqlite(device_id, n)

        # Lưu vào SQLite
        try:
            with self._get_db() as conn:
                conn.execute("""
                    UPDATE devices
                    SET desired_config_version = ?,
                        sync_status = 'SYNCING',
                        name = ?,
                        room_id = ?,
                        location = ?,
                        description = ?,
                        updated_at = ?
                    WHERE device_id = ?
                """, (new_v, n.get("name"), n.get("room"), n.get("location"), n.get("description"), now, device_id))

                conn.execute("""
                    INSERT INTO device_configs (device_id, desired_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        desired_json = excluded.desired_json,
                        updated_at = excluded.updated_at
                """, (device_id, json.dumps(desired_dict, ensure_ascii=False), now))
        except Exception as e:
            logger.error(f"update_desired_config sqlite error for {device_id}: {e}")

        self.save()

        # Tạo payload đẩy sang MQTT theo chuẩn Spec Section 4
        desired_payload = {
            "device_id": device_id,
            "version": new_v,
            "name": n.get("name", "Voice Node"),
            "room": n.get("room", "unknown"),
            "location": n.get("location", ""),
            "description": n.get("description", ""),
            "rl1": n.get("channels", {}).get("ch1", {}).get("device_type", "light"),
            "rl2": n.get("channels", {}).get("ch2", {}).get("device_type", "fan"),
            "volume": desired_dict.get("volume", n.get("configuration", {}).get("audio", {}).get("volume", 85)),
            "timestamp": int(datetime.now(timezone.utc).timestamp())
        }
        return new_v, desired_payload

    def on_reported_config(self, device_id: str, reported_dict: dict) -> str:
        """
        Nhận Reported Configuration từ ESP32 gửi lên qua MQTT.
        - Kiểm tra reported_version so với desired_config_version
        - Nếu >= desired → chuyển sync_status = 'SYNCED'
        - Nếu < desired → sync_status = 'SYNCING'
        """
        now = datetime.now(TZ_VN).isoformat()
        rep_v = int(reported_dict.get("version", reported_dict.get("cfg_version", reported_dict.get("v", 0))))
        
        n = self.data["nodes"].get(device_id)
        des_v = int(n.get("desired_config_version", n.get("cfg_version", 1))) if n else rep_v
        sync_status = "SYNCED" if rep_v >= des_v else "SYNCING"

        if n:
            n["reported_config_version"] = rep_v
            n["sync_status"] = sync_status
            n["last_seen"] = now
            if "status" in n: n["status"] = "online"

            # Đảm bảo node đã được ghi vào bảng devices trước khi ghi device_configs (tránh lỗi FK)
            self._sync_node_to_sqlite(device_id, n)

            try:
                with self._get_db() as conn:
                    conn.execute("""
                        UPDATE devices
                        SET reported_config_version = ?,
                            sync_status = ?,
                            last_seen = ?,
                            updated_at = ?
                        WHERE device_id = ?
                    """, (rep_v, sync_status, now, now, device_id))

                    conn.execute("""
                        INSERT INTO device_configs (device_id, desired_json, reported_json, updated_at)
                        VALUES (?, '{}', ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            reported_json = excluded.reported_json,
                            updated_at = excluded.updated_at
                    """, (device_id, json.dumps(reported_dict, ensure_ascii=False), now))
            except Exception as e:
                logger.error(f"on_reported_config sqlite error for {device_id}: {e}")

            self.save()
            logger.info(f"🔄 Device Twin sync [{device_id}]: rep_v={rep_v}, des_v={des_v} -> Status={sync_status}")
            return sync_status
        else:
            # Thiết bị chưa được Claim / Provision vào hệ thống!
            # KHÔNG tự động thêm vào self.data["nodes"].
            if device_id in self.data["pending"]:
                p = self.data["pending"][device_id]
                p["cfg"] = rep_v
                p["last_seen"] = now
                self.save()
            logger.debug(f"Reported config from unprovisioned device [{device_id}] (cfg_version={rep_v})")
            return "UNPROVISIONED"

    def record_telemetry(self, device_id: str, telemetry_dict: dict):
        """Lưu bản ghi telemetry từ ESP32 vào SQLite và cập nhật node"""
        try:
            v = float(telemetry_dict.get("voltage", telemetry_dict.get("v", 0.0)))
            c = float(telemetry_dict.get("current", telemetry_dict.get("c", 0.0)))
            p = float(telemetry_dict.get("power", telemetry_dict.get("p", 0.0)))
            e = float(telemetry_dict.get("energy", telemetry_dict.get("e", 0.0)))
            heap = int(telemetry_dict.get("free_heap", telemetry_dict.get("heap", 0)))
            rssi = int(telemetry_dict.get("wifi_rssi", telemetry_dict.get("rssi", 0)))

            with self._get_db() as conn:
                conn.execute("""
                    INSERT INTO telemetry_records (
                        device_id, voltage, current, power, energy, free_heap, wifi_rssi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (device_id, v, c, p, e, heap, rssi))

            if device_id in self.data["nodes"]:
                n = self.data["nodes"][device_id]
                n["last_telemetry"] = {
                    "voltage": v, "current": c, "power": p, "energy": e,
                    "free_heap": heap, "rssi": rssi,
                    "recorded_at": datetime.now(TZ_VN).isoformat()
                }
                if rssi: n["rssi"] = rssi
                self.update_heartbeat(device_id)
        except Exception as err:
            logger.warning(f"record_telemetry error for {device_id}: {err}")

    def record_ota_history(self, device_id: str, firmware_file: str, status: str,
                           file_sha256: str = "", error_message: str = "",
                           from_version: str = "", to_version: str = "",
                           progress: int = 0, message: str = ""):
        """Ghi nhận log lịch sử OTA vào SQLite"""
        try:
            now = datetime.now(TZ_VN).isoformat()
            completed = now if status.upper() in ("SUCCESS", "FAILED") else None
            err_msg = error_message or message
            with self._get_db() as conn:
                conn.execute("""
                    INSERT INTO ota_history (
                        device_id, from_version, to_version, firmware_file,
                        file_sha256, status, error_message, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (device_id, from_version, to_version, firmware_file, file_sha256, status.upper(), err_msg, completed))
            logger.info(f"📜 OTA history recorded: {device_id} -> {status}")
        except Exception as err:
            logger.error(f"record_ota_history error: {err}")

    def get_ota_history(self, device_id: Optional[str] = None) -> list:
        """Truy vấn danh sách lịch sử OTA từ SQLite"""
        try:
            with self._get_db() as conn:
                if device_id:
                    rows = conn.execute(
                        "SELECT * FROM ota_history WHERE device_id = ? ORDER BY started_at DESC LIMIT 50",
                        (device_id,)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM ota_history ORDER BY started_at DESC LIMIT 50"
                    ).fetchall()
                return [dict(r) for r in rows]
        except Exception as err:
            logger.error(f"get_ota_history error: {err}")
            return []

    def get_device_twin(self, device_id: str) -> Optional[dict]:
        """Truy vấn toàn bộ Device OS Twin từ SQLite"""
        try:
            with self._get_db() as conn:
                dev = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,)).fetchone()
                if not dev: return None
                dev_dict = dict(dev)

                cfg = conn.execute("SELECT * FROM device_configs WHERE device_id = ?", (device_id,)).fetchone()
                if cfg:
                    dev_dict["desired_config"] = json.loads(cfg["desired_json"]) if cfg["desired_json"] else {}
                    dev_dict["reported_config"] = json.loads(cfg["reported_json"]) if cfg["reported_json"] else {}
                else:
                    dev_dict["desired_config"] = {}
                    dev_dict["reported_config"] = {}

                caps = conn.execute("SELECT * FROM device_capabilities WHERE device_id = ?", (device_id,)).fetchone()
                if caps:
                    dev_dict["capabilities"] = dict(caps)
                return dev_dict
        except Exception as e:
            logger.error(f"get_device_twin error for {device_id}: {e}")
            return None

    def get_telemetry_history(self, device_id: str, limit: int = 50) -> List[dict]:
        try:
            with self._get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM telemetry_records
                    WHERE device_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (device_id, limit)).fetchall()
                return [dict(r) for r in reversed(rows)]
        except Exception as e:
            logger.error(f"get_telemetry_history error for {device_id}: {e}")
            return []

    def get_ota_history(self, device_id: str = None, limit: int = 20) -> List[dict]:
        try:
            with self._get_db() as conn:
                if device_id:
                    rows = conn.execute("""
                        SELECT * FROM ota_history
                        WHERE device_id = ?
                        ORDER BY id DESC LIMIT ?
                    """, (device_id, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM ota_history
                        ORDER BY id DESC LIMIT ?
                    """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_ota_history error: {e}")
            return []


    # ── Legacy shim: register_node (để firmware cũ vẫn chạy) ───────────
    def register_node(self, node_id: str, mac: str, channels: dict = None,
                      area: str = None, description: str = None) -> dict:
        room = slug(area) if area else "unknown"
        if node_id in self.data["nodes"]:
            n = self.data["nodes"][node_id]
            n["last_seen"] = datetime.now(TZ_VN).isoformat()
            n["status"] = "online"
            if mac: n["mac"] = mac
            if room != "unknown": n["room"] = room
            if channels: n["channels"].update(channels)
            self.save()
            return n
        # node mới dạng legacy → tạo luôn (coi như đã provision)
        now = datetime.now(TZ_VN).isoformat()
        self.data["nodes"][node_id] = {
            "mac": mac, "room": room, "aliases": ROOM_ALIASES.get(room, [room]),
            "description": description or f"Node {node_id}",
            "channels": channels or {}, "sensors": {"pzem": True, "temperature": False},
            "cfg_version": 1, "registered_at": now, "last_seen": now, "status": "online",
        }
        self.save()
        return self.data["nodes"][node_id]

    def configure_node(self, node_id: str, area: str, description: str, channel_config: dict) -> bool:
        if node_id not in self.data["nodes"]: return False
        n = self.data["nodes"][node_id]
        n["room"] = slug(area)
        n["description"] = description
        n["status"] = "online"
        for k, v in channel_config.items(): n["channels"][k] = v
        n["cfg_version"] = int(n.get("cfg_version", 1)) + 1
        self.save()
        return True

    # ── Resolver 2 lớp (chống ảo giác) ──────────────────────────────────
    def find_node_by_device(self, device_type: str, area: str = None) -> Optional[Tuple[str, str]]:
        """
        Từ intent (device, location) → (node_id, channel).
        - device_type/location có thể là None → suy luận
        - chỉ trả về node online và channel tồn tại trong registry, KHÔNG bịa
        """
        dev = canon_device(device_type) if device_type else ""
        area_s = slug(area) if area else ""

        def matches_channel(ch_id: str, ch: dict) -> bool:
            if not dev: return True  # không nói thiết bị → chấp nhận mọi channel
            cid_s = slug(ch_id)
            if dev in (cid_s, f"relay_{cid_s[-1]}", f"cong_tac_{cid_s[-1]}", f"ch{cid_s[-1]}", f"relay{cid_s[-1]}", f"kenh_{cid_s[-1]}"):
                return True
            ct = slug(ch.get("device_type", ""))
            aliases = [slug(a) for a in ch.get("aliases", [])]
            if dev == ct or dev in aliases or ct in dev: return True
            # substring
            if dev in ct or ct in dev: return True
            if any(dev in a or a in dev for a in aliases): return True
            return False

        def matches_room(node: dict) -> bool:
            if not area_s or area_s in ("all","any","none","unknown"): return True
            nr = slug(node.get("room",""))
            aliases = [slug(a) for a in node.get("aliases", [])]
            if area_s == nr or area_s in nr or nr in area_s: return True
            if any(area_s in a or a in area_s for a in aliases): return True
            # ROOM_ALIASES mở rộng
            for canon, alist in ROOM_ALIASES.items():
                if area_s in [slug(x) for x in alist] and nr == canon: return True
                if nr in [slug(x) for x in alist] and area_s == canon: return True
            return False

        # Pass 1: đúng phòng + đúng thiết bị
        for nid, node in self.data["nodes"].items():
            if node.get("status") != "online": continue
            if not matches_room(node): continue
            for ch_id, ch in node.get("channels", {}).items():
                if matches_channel(ch_id, ch): return (nid, ch_id)

        # Nếu người dùng nêu rõ phòng nhưng phòng đó không có thiết bị -> Trả về None để thông báo không tìm thấy
        if area_s:
            return None

        # Nếu không nói phòng -> ưu tiên node duy nhất nếu cả nhà chỉ có 1 thiết bị loại này
        candidates = []
        for nid, node in self.data["nodes"].items():
            if node.get("status") != "online": continue
            for ch_id, ch in node.get("channels", {}).items():
                if matches_channel(ch_id, ch): candidates.append((nid, ch_id))
        if len(candidates) == 1:
            return candidates[0]
        # nếu mơ hồ (có nhiều thiết bị) mà không rõ phòng -> trả None để hỏi lại, tránh bấm nhầm
        return None

    def resolve_fullname(self, node_id: str, channel: str) -> str:
        ch = self.data["nodes"].get(node_id, {}).get("channels", {}).get(channel, {})
        return ch.get("fullname", f"{node_id}-{channel}")

    def next_seq(self, node_id: str) -> int:
        self._seq[node_id] = (self._seq.get(node_id, 0) + 1) & 0xFFFF
        return self._seq[node_id]

    # ── Helpers cho LLM prompt & grammar ─────────────────────────────────
    def allowed_rooms(self) -> List[str]:
        rooms = set()
        for n in self.data["nodes"].values():
            r = slug(n.get("room", ""))
            if r and r != "unknown":
                rooms.add(r)
            for a in n.get("aliases", []):
                sa = slug(a)
                if sa and sa != "unknown":
                    rooms.add(sa)
        # Phòng cơ bản luôn hợp lệ
        rooms.update(["phong_khach", "phong_ngu", "phong_bep", "phong_tam", "ban_cong"])
        return sorted(rooms)

    def allowed_devices(self) -> List[str]:
        devs = set()
        for n in self.data["nodes"].values():
            for ch in n.get("channels", {}).values():
                dt = slug(ch.get("device_type", ""))
                if dt: devs.add(dt)
                for a in ch.get("aliases", []):
                    sa = slug(a)
                    if sa: devs.add(sa)
        # luôn cho phép các thiết bị cơ bản
        devs.update(["den", "quat", "tivi", "dieu_hoa", "binh_nong_lanh", "den_ngu", "den_tran", "light", "fan"])
        return sorted(devs)

    def inventory_for_prompt(self) -> str:
        """Tóm tắt inventory để nhúng vào system prompt — giúp LLM không bịa."""
        lines = []
        for room, nids in self.data.get("rooms", {}).items():
            for nid in nids:
                n = self.data["nodes"][nid]
                chs = ", ".join(f"{cid}:{c.get('device_type')}" for cid,c in n.get("channels", {}).items())
                lines.append(f"- {nid} (room={room}) [{chs}]")
        return "\n".join(lines) if lines else "- (chưa có node nào được provision)"

    def gbnf_grammar(self) -> str:
        """Sinh GBNF ép LLM chỉ được sinh JSON đúng enum hiện có."""
        rooms = self.allowed_rooms()
        devs = self.allowed_devices()
        room_alt = " | ".join(f'"\\"{r}\\""' for r in rooms)
        dev_alt = " | ".join(f'"\\"{d}\\""' for d in devs)
        # GBNF cho llama.cpp: https://github.com/ggerganov/llama.cpp/blob/master/grammars/README.md
        return f'''
root ::= "{{" ws "\\"voice_reply\\"" ws ":" ws string ws "," ws "\\"command\\"" ws ":" ws command ws "}}" 
command ::= "{{" ws "\\"action\\"" ws ":" ws action ws "," ws "\\"device\\"" ws ":" ws device ws "," ws "\\"location\\"" ws ":" ws location ws "," ws "\\"value\\"" ws ":" ws value ws "}}"
action ::= "\\"turn_on\\"" | "\\"turn_off\\"" | "\\"unknown\\""
device ::= {dev_alt} | "null"
location ::= {room_alt} | "null"
value ::= [0-9]+ | "null"
string ::= "\\"" chars "\\""
chars ::= [^"\\\\]* 
ws ::= [ \\t\\n]*
'''.strip()

    # ── Getters ──────────────────────────────────────────────────────────
    def get_all_nodes(self) -> dict: return self.data.get("nodes", {})
    def get_pending(self) -> dict: return self.data.get("pending", {})
    def get_rooms(self) -> dict: return self.data.get("rooms", {})
    def get_online_nodes(self) -> dict:
        return {k:v for k,v in self.data.get("nodes", {}).items() if v.get("status")=="online"}
    def get_rated_watts(self, node_id: str, channel: str) -> float:
        return self.data["nodes"].get(node_id, {}).get("channels", {}).get(channel, {}).get("rated_watts", 0)

    def find_node_by_mac(self, mac: str) -> Optional[str]:
        """Tìm node_id đã provision theo MAC (uppercase chuẩn hoá)."""
        mac = (mac or "").upper()
        for nid, n in self.data["nodes"].items():
            if (n.get("mac") or "").upper() == mac:
                return nid
        return None

    def update_heartbeat(self, node_id: str):
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["last_seen"] = datetime.now(TZ_VN).isoformat()
            self.data["nodes"][node_id]["status"] = "online"
    def mark_offline(self, node_id: str):
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["status"] = "offline"
            logger.warning(f"Node offline: {node_id}")
