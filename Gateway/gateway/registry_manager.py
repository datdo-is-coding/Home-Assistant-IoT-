"""
Device Registry Manager v2 — quản lý theo phòng + fullname + provision flow.

- Mỗi node: id = {room}-{short}  e.g. livingroom-node01, bedroom-node02
- Mỗi relay: fullname = {node_id}-{dev} e.g. livingroom-node01-light
- ESP32 lưu {node_id, room, rl1, rl2, cfg_version} vào NVS và echo lại mỗi hello.
- Node mới (cfg==null) vào hàng chờ pending → WebUI đăng ký → Gateway gửi cfg.

Tương thích ngược: tự migrate file cũ (area/channels) sang schema mới khi load.
"""
import json
import math
import os
import re
import time
import copy
import sqlite3
import logging
import asyncio
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

import config

logger = logging.getLogger("registry")
TZ_VN = timezone(timedelta(hours=7))

_slug_re = re.compile(r"[^a-z0-9]+")
_slug_translation = str.maketrans(
    "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
    "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd",
)
def slug(s: str) -> str:
    s = (s or "").lower().strip()

    s = s.translate(_slug_translation)
    s = _slug_re.sub("_", s).strip("_")
    return s or "unknown"

DEVICE_CANON = {
    "den": "light", "light": "light", "bong_den": "light",
    "quat": "fan", "fan": "fan",
    "bom": "pump", "may_bom": "pump", "pump": "pump",
    "rem": "curtain", "man": "curtain",
    "o_cam": "socket", "socket": "socket", "outlet": "socket",
    "cong_tac": "switch", "switch": "switch",
    "dieu_hoa": "air_conditioner", "air_conditioner": "air_conditioner",
    "nong_lanh": "water_heater", "binh_nong_lanh": "water_heater",
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
    def __init__(self, registry_path: str = None, db_path: str = None):
        self.path = registry_path or config.REGISTRY_FILE
        self.db_path = db_path or getattr(config, "GATEWAY_DB", "/var/lib/smarthome/gateway.db")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        except Exception:
            pass
        self.data: Dict[str, Any] = {"nodes": {}, "pending": {}, "rooms": {}}
        self._seq: Dict[str, int] = {}
        self._persisted = {}
        self._telemetry_write_count = 0
        self._init_sqlite()
        self.load()

    @contextmanager
    def _get_db(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_sqlite(self):
        try:
            with self._get_db() as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS registry_entries (
                    kind TEXT NOT NULL, entry_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(kind, entry_id)
                );
                CREATE TABLE IF NOT EXISTS registry_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
                CREATE TABLE IF NOT EXISTS channel_telemetry_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(32) NOT NULL,
                    channel VARCHAR(8) NOT NULL,
                    current_ma REAL,
                    voltage_v REAL,
                    power_w REAL,
                    valid BOOLEAN NOT NULL DEFAULT 0,
                    quality VARCHAR(16) NOT NULL DEFAULT 'invalid',
                    sample_uptime_ms INTEGER,
                    received_at REAL,
                    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS zones (
                    zone_id VARCHAR(32) PRIMARY KEY,
                    display_name VARCHAR(64) NOT NULL,
                    controller_id VARCHAR(32),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_dev_time ON telemetry_records(device_id, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_channel_telemetry_dev_time
                    ON channel_telemetry_records(device_id, channel, recorded_at);
                """)

                try:
                    conn.execute("ALTER TABLE devices ADD COLUMN zone_id VARCHAR(32);")
                except Exception:
                    pass
            logger.info(f"✨ SQLite Gateway Registry initialized: {self.db_path} (WAL Mode)")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite Registry at {self.db_path}: {e}")
            raise

    def _sync_node_to_sqlite(self, nid: str, n: dict, connection=None):
        """Đồng bộ một node vào bảng devices và capabilities của SQLite."""
        try:
            now = datetime.now(TZ_VN).isoformat()
            hw = n.get("firmware", {}).get("hardware", n.get("hardware", "esp32s3"))
            serial = n.get("hardware_uid") or n.get("serial") or f"legacy:{nid}"
            caps = n.get("capabilities", [])
            dev_type = "voice_node" if "voice_wake" in caps or "microphone" in caps else "relay_node"
            name = n.get("name", nid)
            room = n.get("room", "unknown")
            location = n.get("location", "")
            description = n.get("description", "")
            raw_mac = n.get("address", {}).get("mac", n.get("mac", "")) if isinstance(n.get("address"), dict) else n.get("mac", "")
            mac = raw_mac if isinstance(raw_mac, str) else ""
            raw_ip = n.get("address", {}).get("ip", n.get("ip", "")) if isinstance(n.get("address"), dict) else n.get("ip", "")
            ip = raw_ip if isinstance(raw_ip, str) else ""
            rssi = n.get("address", {}).get("rssi", n.get("rssi")) if isinstance(n.get("address"), dict) else n.get("rssi")
            status = n.get("status", "online")
            des_ver = n.get("desired_config_version", n.get("cfg_version", 1))
            rep_ver = n.get("reported_config_version", des_ver)
            sync_st = n.get("sync_status", "SYNCED")
            last_seen = n.get("last_seen", now)

            with (nullcontext(connection) if connection is not None else self._get_db()) as conn:
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

                num_relays = 2
                channels_dict = n.get("channels")
                cfg_relays = n.get("configuration", {}).get("relays") if isinstance(n.get("configuration"), dict) else None
                relay_state = n.get("relay_state")
                hardware = str(n.get("hardware") or n.get("firmware", {}).get("hardware") or "")
                serial = str(n.get("serial") or n.get("firmware", {}).get("serial") or "")
                if "relay_3ch" in caps or "ch3" in (channels_dict or {}) or "AB2" in serial or hardware == "ActionBox":
                    num_relays = max(num_relays, 3)
                if isinstance(channels_dict, dict) and len(channels_dict) > 0:
                    num_relays = max(num_relays, len(channels_dict))
                if isinstance(cfg_relays, dict) and len(cfg_relays) > 0:
                    num_relays = max(num_relays, len(cfg_relays))
                if isinstance(relay_state, list) and len(relay_state) > 0:
                    num_relays = max(num_relays, len(relay_state))

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
                    True, num_relays, json.dumps(caps, ensure_ascii=False)
                ))
        except Exception as e:
            logger.warning(f"_sync_node_to_sqlite error for {nid}: {e}")
            raise

    def load(self):
        with self._get_db() as conn:
            initialized = conn.execute("SELECT 1 FROM registry_meta WHERE key='initialized'").fetchone()
            if initialized:
                for row in conn.execute("SELECT kind, entry_id, payload FROM registry_entries"):
                    self.data[row['kind']][row['entry_id']] = json.loads(row['payload'])
                    self._persisted[(row['kind'], row['entry_id'])] = row['payload']
                self._rebuild_rooms()
                return
            old_devices = list(conn.execute("SELECT * FROM devices"))

            if os.path.exists(self.path):
                with open(self.path, encoding='utf-8') as source:
                    legacy = json.load(source)
                self.data['nodes'] = legacy.get('nodes', {})
                self.data['pending'] = legacy.get('pending', {})
            for row in old_devices:
                node = self.data['nodes'].setdefault(row['device_id'], {})
                node.update(name=row['name'], room=row['room_id'] or 'unknown', mac=row['mac_address'],
                            desired_config_version=row['desired_config_version'],
                            reported_config_version=row['reported_config_version'], sync_status=row['sync_status'])
            for nid, node in self.data['nodes'].items():
                self._migrate_node(nid, node)
        self.save()
        logger.info('Migrated registry to SQLite; legacy JSON is now backup-only')

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

    def save(self, changed_node=None):
        self._rebuild_rooms()
        pending = {}
        for kind in ('nodes', 'pending'):
            entries = self.data.get(kind, {})
            for nid, node in entries.items():
                if changed_node is None or (kind == 'nodes' and nid == changed_node):
                    pending[(kind, nid)] = json.dumps(node, ensure_ascii=False, sort_keys=True)
        changed = {key: value for key, value in pending.items() if self._persisted.get(key) != value}
        deleted = set(self._persisted) - set(pending) if changed_node is None else set()
        with self._get_db() as conn:
            for (kind, nid), value in changed.items():
                conn.execute('INSERT OR REPLACE INTO registry_entries VALUES (?, ?, ?)', (kind, nid, value))
                if kind == 'nodes':
                    self._sync_node_to_sqlite(nid, self.data[kind][nid], connection=conn)
            for kind, nid in deleted:
                conn.execute('DELETE FROM registry_entries WHERE kind=? AND entry_id=?', (kind, nid))
            conn.execute("INSERT OR IGNORE INTO registry_meta VALUES ('initialized','1')")
        self._persisted.update(changed)
        for key in deleted:
            self._persisted.pop(key, None)

    def export_json(self, path):
        """Explicit backup only; normal operation never writes the legacy JSON."""
        tmp = str(path) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as target:
            json.dump(self.data, target, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def on_hello(self, payload: dict, ws_available: bool = False) -> dict:
        """
        Xử lý gói tin hello thương mại từ ESP32:
        {"t":"hello", "id":..., "mac":..., "hardware":..., "serial":..., "state":..., "rl":[...], "cfg":n, ...}
        """
        mac = (payload.get("mac") or "").upper()
        node_id = payload.get("id") or payload.get("node_id") or payload.get("device_id")
        hardware = payload.get("hardware", "esp32s3")
        serial = payload.get("serial", "S3-2026-000000")
        state = payload.get("state", "READY")
        cfg = payload.get("cfg")
        rl = payload.get("rl", [0, 0])
        rssi = payload.get("rssi")
        ip = payload.get("ip")
        owner_epoch = payload.get("owner_epoch", payload.get("epoch"))
        now = datetime.now(TZ_VN).isoformat()

        existing_node_id = None
        if node_id and node_id in self.data["nodes"]:
            existing_node_id = node_id
        elif mac:
            for nid, ninfo in self.data["nodes"].items():
                n_mac = (ninfo.get("mac") or ninfo.get("address", {}).get("mac") or "").upper()
                if n_mac == mac:
                    existing_node_id = nid
                    break

        # G3: Check tombstone — removed devices cannot restore ownership via legacy hello
        tombstone = self.get_tombstone(node_id) if hasattr(self, "get_tombstone") else None
        if not tombstone and mac and hasattr(self, "get_tombstone"):
            tombstone = self.get_tombstone(mac)
        if not existing_node_id and tombstone and state != "FACTORY_NEW":
            logger.warning(f"Rejected hello from tombstoned device {node_id or mac}: {tombstone.get('notice')}")
            return {"action": "rejected", "error": "device_removed_from_home", "node_id": node_id or mac}

        if existing_node_id and state == "FACTORY_NEW":
            logger.warning(
                f"Device {existing_node_id} (MAC={mac}) reported FACTORY_NEW. "
                "Rejecting auto-relink without setup proof (G3)."
            )
            return {"action": "rejected", "error": "proof_required_for_factory_new", "node_id": existing_node_id}

        if existing_node_id:
            curr_epoch = int(self.data["nodes"][existing_node_id].get("owner_epoch", self.data["nodes"][existing_node_id].get("epoch", 0)))
            if owner_epoch is not None:
                try:
                    new_epoch = int(owner_epoch)
                    if new_epoch < curr_epoch:
                        logger.warning(f"Rejected stale owner_epoch {new_epoch} < {curr_epoch} for node {existing_node_id}")
                        return {"action": "rejected", "error": "stale_epoch", "node_id": existing_node_id}
                except (ValueError, TypeError):
                    pass
            elif curr_epoch > 0:
                logger.warning(f"Rejected packet missing owner_epoch (epoch stripped) for node {existing_node_id}")
                return {"action": "rejected", "error": "epoch_stripped", "node_id": existing_node_id}

        if existing_node_id and (cfg is None or node_id != existing_node_id):
            logger.info(f"🔄 [Registry] Re-flashed device detected (MAC={mac}) -> Auto-relinking to existing node '{existing_node_id}'")

            if mac:
                for k, v in list(self.data["pending"].items()):
                    if k.upper() == mac.upper() or (v.get("mac") and v.get("mac").upper() == mac.upper()) or k == existing_node_id:
                        del self.data["pending"][k]
            elif existing_node_id in self.data["pending"]:
                del self.data["pending"][existing_node_id]

            n = self.data["nodes"][existing_node_id]
            n["last_seen"] = now
            n["status"] = "online"
            if rssi is not None: n["rssi"] = rssi
            if ip: n["ip"] = ip
            n["relay_state"] = rl
            if owner_epoch is not None:
                try:
                    n["owner_epoch"] = int(owner_epoch)
                except (ValueError, TypeError):
                    pass
            if "address" not in n: n["address"] = {}
            if ip: n["address"]["ip"] = ip
            if mac: n["address"]["mac"] = mac
            n["address"]["last_seen"] = now
            self._sync_node_to_sqlite(existing_node_id, n)
            self.save()
            return {"action": "cfg_mismatch", "node_id": existing_node_id, "mac": mac}

        is_factory = (state == "FACTORY_NEW" or cfg is None or not existing_node_id)
        if is_factory:
            clean_mac = mac.replace(":", "").lower()
            pending_key = node_id or (f"node_{clean_mac[-8:]}" if clean_mac else "unknown")

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

        if existing_node_id:

            if mac:
                for k, v in list(self.data["pending"].items()):
                    if k.upper() == mac.upper() or (v.get("mac") and v.get("mac").upper() == mac.upper()) or k == existing_node_id:
                        del self.data["pending"][k]
            elif existing_node_id in self.data["pending"]:
                del self.data["pending"][existing_node_id]

            n = self.data["nodes"][existing_node_id]
            n["last_seen"] = now
            n["status"] = "online"
            if rssi is not None: n["rssi"] = rssi
            if ip: n["ip"] = ip
            n["relay_state"] = rl
            if owner_epoch is not None:
                try:
                    n["owner_epoch"] = int(owner_epoch)
                except (ValueError, TypeError):
                    pass

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

                    if "configuration" not in n:
                        n["configuration"] = {}
                    n["configuration"]["cfg_version"] = cfg
                    n["cfg_version"] = cfg
                    n["reported_config_version"] = cfg
                    n["sync_status"] = "SYNCED"
                    logger.info(f"🔄 Auto-synced node {existing_node_id} registry version to node's newer cfg={cfg}")
                    self.save()
                    return {"action": "known", "node_id": existing_node_id}
                else:
                    logger.warning(f"cfg mismatch {existing_node_id}: node cfg={cfg} expected={expected} → will re-provision")
                    self.save()
                    return {"action": "cfg_mismatch", "node_id": existing_node_id, "expected": expected, "got": cfg}
            self.save()
            return {"action": "known", "node_id": existing_node_id}

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
            target_rl = list(rl)
            node = self.data["nodes"][node_id]
            caps = node.get("capabilities", [])
            min_relays = 3 if ("relay_3ch" in caps or len(node.get("channels") or {}) >= 3) else 2
            while len(target_rl) < max(min_relays, len(node.get("relay_state", []))):
                target_rl.append(0)
            if self.data["nodes"][node_id].get("relay_state") == target_rl:
                return True
            self.data["nodes"][node_id]["relay_state"] = target_rl
            self.save(changed_node=node_id)
            return True
        return False

    def update_relay_channel(self, node_id: str, channel: Any, state: Any) -> bool:
        """Cập nhật trạng thái một relay đơn lẻ cho ActionBox V2 (ch1, ch2, ch3)."""
        if node_id not in self.data["nodes"]:
            return False
        node = self.data["nodes"][node_id]
        ch_idx = {"ch1": 0, "ch2": 1, "ch3": 2, 1: 0, 2: 1, 3: 2, "1": 0, "2": 1, "3": 2}.get(channel)
        if ch_idx is None:
            return False
        caps = node.get("capabilities", [])
        min_relays = 3 if ("relay_3ch" in caps or len(node.get("channels") or {}) >= 3) else 2
        cur_rl = list(node.get("relay_state", []))
        while len(cur_rl) < max(min_relays, ch_idx + 1):
            cur_rl.append(0)
        cur_rl[ch_idx] = 1 if state in (1, True, "ON", "on") else 0
        return self.update_relay_state(node_id, cur_rl)

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
                conn.execute("DELETE FROM registry_entries WHERE entry_id = ?", (node_id,))
                conn.commit()
            deleted = True
        except Exception as e:
            logger.error(f"Failed to delete node {node_id} from SQLite: {e}")

        self.save()
        logger.info(f"🗑️ [Registry] Deleted device: {node_id}")
        return deleted

    def clear_tombstone(self, device_uid: str) -> bool:
        """Clear tombstone record for a device UID (e.g. when recommissioned)."""
        if not device_uid:
            return False
        try:
            with self._get_db() as conn:
                tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_tombstones'").fetchone()
                if tbl:
                    conn.execute("DELETE FROM device_tombstones WHERE device_uid = ?", (str(device_uid),))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear tombstone for {device_uid}: {e}")
            return False

    def get_tombstone(self, device_uid: str) -> Optional[dict]:
        """Check if device UID has a tombstone from being removed from home."""
        if not device_uid:
            return None
        try:
            with self._get_db() as conn:
                conn.row_factory = sqlite3.Row
                tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_tombstones'").fetchone()
                if not tbl:
                    return None
                row = conn.execute("SELECT * FROM device_tombstones WHERE device_uid = ?", (str(device_uid),)).fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    def provision_node(self, mac_or_id: str, room: str, rl1: str = "light", rl2: str = "fan",
                       rl3: Optional[str] = None,
                       node_short: str = None, description: str = None,
                       name: str = None, location: str = None,
                       subbox_id: Optional[str] = None) -> Optional[dict]:
        """
        WebUI gọi khi user gán tên + phòng + vị trí cho node pending.
        Tuân thủ chặt chẽ schema:
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

        if not pending and mac_or_id in self.data["nodes"]:
            pending = self.data["nodes"][mac_or_id]

        if not pending:
            logger.warning(f"Provision rejected: Device '{mac_or_id}' not found in pending candidates.")
            return None

        actual_id = pending.get("device_id") or mac_or_id
        mac = (pending.get("mac") or "").upper()
        room_s = slug(room)

        # Kiểm tra giới hạn phòng (tối đa 4 node)
        room_nodes = [n for n in self.data["nodes"].values() if n.get("room") == room_s]
        if len(room_nodes) >= 4 and actual_id not in self.data["nodes"]:
            logger.warning(f"Provision rejected: Room '{room_s}' already has {len(room_nodes)} nodes (limit 4).")
            return None

        # Kiểm tra giới hạn SubBox (tối đa 4 ActionBox trên một SubBox)
        target_subbox = subbox_id or pending.get("subbox_id")
        if target_subbox:
            subbox_nodes = [
                n for n in self.data["nodes"].values()
                if (n.get("subbox_id") == target_subbox or n.get("parent_subbox") == target_subbox)
            ]
            if len(subbox_nodes) >= 4 and actual_id not in self.data["nodes"]:
                logger.warning(f"Provision rejected: SubBox '{target_subbox}' already has {len(subbox_nodes)} nodes (limit 4).")
                return None

        # Chỉ pop pending sau khi đã vượt qua các kiểm tra giới hạn
        for k in matched_keys:
            self.data["pending"].pop(k, None)

        if mac:
            for k, p in list(self.data["pending"].items()):
                if (p.get("mac") and p.get("mac").upper() == mac) or k.upper() == mac:
                    self.data["pending"].pop(k, None)

        if rl3 is None:
            is_3ch = len(pending.get("rl", [])) >= 3 or "ActionBox" in pending.get("hardware", "") or pending.get("hardware") == "esp32s3"
            if is_3ch:
                rl3 = "switch"

        if mac:
            for old_id, old_node in list(self.data["nodes"].items()):
                if old_id != actual_id and old_node.get("address", {}).get("mac", "").upper() == mac:
                    logger.info(f"Removing obsolete node '{old_id}' with duplicate MAC '{mac}' during provisioning.")
                    self.data["nodes"].pop(old_id, None)
        hardware = pending.get("hardware", "esp32s3")
        serial = pending.get("serial", "S3-2026-000000")
        ip = pending.get("ip")
        rssi = pending.get("rssi")

        rl1_c = canon_device(rl1) if rl1 else "light"
        rl2_c = canon_device(rl2) if rl2 else "fan"
        rl3_c = canon_device(rl3) if rl3 else "switch"

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
        if rl3:
            channels["ch3"] = {
                "device_type": rl3_c, "fullname": f"{actual_id}-{rl3_c}",
                "name": rl3 or "Công tắc", "aliases": [rl3_c], "gpio": 5, "rated_watts": 100,
                "description": rl3_c
            }

        relay_cap = "relay_3ch" if len(channels) >= 3 else "relay_2ch"
        capabilities = [
            "voice_wake", "audio_speaker", "microphone", relay_cap, "energy_monitor", "ota"
        ]

        cfg_relays = {
            "ch1": {"device_type": rl1_c, "fullname": f"{actual_id}-{rl1_c}", "name": rl1 or "Đèn", "gpio": 4},
            "ch2": {"device_type": rl2_c, "fullname": f"{actual_id}-{rl2_c}", "name": rl2 or "Quạt", "gpio": 5}
        }
        if "ch3" in channels:
            cfg_relays["ch3"] = {
                "device_type": rl3_c, "fullname": f"{actual_id}-{rl3_c}", "name": rl3 or "Công tắc", "gpio": 5
            }

        rl = pending.get("rl")
        if not rl:
            rl = [0, 0, 0] if len(channels) >= 3 else [0, 0]
        elif len(rl) < len(channels):
            rl = list(rl) + [0] * (len(channels) - len(rl))

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
            "capabilities": capabilities,
            "firmware": {
                "version": "2.1.0",
                "hardware": hardware,
                "serial": serial,
                "build_date": "2026-09-19"
            },
            "configuration": {
                "relays": cfg_relays,
                "audio": {"sample_rate": 16000, "volume": 85},
                "cfg_version": 1
            },
            "security": {
                "state": "READY",
                "claimed_at": now
            },

            "node_id": actual_id,
            "mac": mac,
            "ip": ip,
            "rssi": rssi,
            "relay_state": rl,
            "status": "online",
            "last_seen": now,
            "cfg_version": 1,
            "channels": channels,
            "aliases": ROOM_ALIASES.get(room_s, [room_s]),
            "subbox_id": target_subbox,
        }

        self.clear_tombstone(actual_id)
        if mac:
            self.clear_tombstone(mac)

        self.save()
        logger.info(f"✨ Commercial Provisioned: {actual_id} -> Name='{dev_name}', Room='{room_s}', Serial='{serial}'")
        res = self.data["nodes"][actual_id] | {"node_id": actual_id, "room_s": room_s, "rl1": rl1_c, "rl2": rl2_c}
        if "ch3" in channels:
            res["rl3"] = rl3_c
        return res

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

        ch1_type = d.get("ch1_type") or d.get("rl1")
        ch1_name = d.get("ch1_name")
        ch1_aliases = d.get("ch1_aliases")
        ch2_type = d.get("ch2_type") or d.get("rl2")
        ch2_name = d.get("ch2_name")
        ch2_aliases = d.get("ch2_aliases")
        ch3_type = d.get("ch3_type") or d.get("rl3")
        ch3_name = d.get("ch3_name")
        ch3_aliases = d.get("ch3_aliases")

        if "channels" not in n:
            n["channels"] = {}

        if ch1_type or ch1_name or ch1_aliases is not None:
            ch1 = n["channels"].setdefault("ch1", {})
            if ch1_type:
                dt = canon_device(ch1_type)
                ch1["device_type"] = dt
                ch1["fullname"] = f"{device_id}-{dt}"
                if "aliases" not in ch1:
                    ch1["aliases"] = [dt]
                elif dt not in ch1["aliases"]:
                    ch1["aliases"].append(dt)
            if ch1_name:
                ch1["name"] = ch1_name
            if isinstance(ch1_aliases, list):
                ch1["aliases"] = [str(a).strip().lower() for a in ch1_aliases if str(a).strip()]

        if ch2_type or ch2_name or ch2_aliases is not None:
            ch2 = n["channels"].setdefault("ch2", {})
            if ch2_type:
                dt = canon_device(ch2_type)
                ch2["device_type"] = dt
                ch2["fullname"] = f"{device_id}-{dt}"
                if "aliases" not in ch2:
                    ch2["aliases"] = [dt]
                elif dt not in ch2["aliases"]:
                    ch2["aliases"].append(dt)
            if ch2_name:
                ch2["name"] = ch2_name
            if isinstance(ch2_aliases, list):
                ch2["aliases"] = [str(a).strip().lower() for a in ch2_aliases if str(a).strip()]

        if ch3_type or ch3_name or ch3_aliases is not None:
            ch3 = (n.get("channels") or {}).setdefault("ch3", {
                "device_type": "switch",
                "fullname": f"{device_id}-switch",
                "name": "Công tắc",
                "gpio": 5,
                "rated_watts": 100,
                "aliases": ["switch"]
            })
            if ch3_type:
                dt = canon_device(ch3_type)
                ch3["device_type"] = dt
                ch3["fullname"] = f"{device_id}-{dt}"
                if "aliases" not in ch3:
                    ch3["aliases"] = [dt]
                elif dt not in ch3["aliases"]:
                    ch3["aliases"].append(dt)
            if ch3_name:
                ch3["name"] = ch3_name
            if isinstance(ch3_aliases, list):
                ch3["aliases"] = [str(a).strip().lower() for a in ch3_aliases if str(a).strip()]

            caps = n.get("capabilities", [])
            if "relay_2ch" in caps:
                n["capabilities"] = [c if c != "relay_2ch" else "relay_3ch" for c in caps]
            elif "relay_3ch" not in caps:
                caps.append("relay_3ch")
                n["capabilities"] = caps

        cur_rl = list(n.get("relay_state") or [0, 0])
        while len(cur_rl) < len(n.get("channels") or {}):
            cur_rl.append(0)
        n["relay_state"] = cur_rl

        cur_v = n.get("cfg_version", 1) + 1
        n["cfg_version"] = cur_v
        n["desired_config_version"] = cur_v
        n["sync_status"] = "SYNCING"
        n["last_seen"] = datetime.now(TZ_VN).isoformat()

        if "configuration" not in n:
            n["configuration"] = {"relays": {}, "audio": {"sample_rate": 16000, "volume": 85}}
        n["configuration"]["cfg_version"] = cur_v
        relays = n["configuration"].setdefault("relays", {})
        channels = n.get("channels") or {}
        if "ch1" in channels:
            relays["ch1"] = {
                "device_type": channels["ch1"].get("device_type", "light"),
                "fullname": channels["ch1"].get("fullname", f"{device_id}-light"),
                "name": channels["ch1"].get("name", "Đèn"),
                "gpio": channels["ch1"].get("gpio", 4)
            }
        if "ch2" in channels:
            relays["ch2"] = {
                "device_type": channels["ch2"].get("device_type", "fan"),
                "fullname": channels["ch2"].get("fullname", f"{device_id}-fan"),
                "name": channels["ch2"].get("name", "Quạt"),
                "gpio": channels["ch2"].get("gpio", 5)
            }
        if "ch3" in channels:
            relays["ch3"] = {
                "device_type": channels["ch3"].get("device_type", "switch"),
                "fullname": channels["ch3"].get("fullname", f"{device_id}-switch"),
                "name": channels["ch3"].get("name", "Công tắc"),
                "gpio": channels["ch3"].get("gpio", 5)
            }

        self.save()
        logger.info(f"✏️ [Registry] Updated device {device_id}: name='{n.get('name')}', room='{n.get('room')}', v={cur_v}")
        return n

    def add_device_alias(self, node_id: str, channel: str, alias: str) -> bool:
        """Thêm từ vựng/khẩu lệnh cho một kênh thiết bị và lưu persistent vào SQLite."""
        if not node_id or not alias:
            return False

        if "::" in node_id:
            parts = node_id.split("::", 1)
            node_id = parts[0]
            if not channel:
                channel = parts[1]

        channel = channel or "ch1"
        clean_alias = str(alias).strip().lower()
        if not clean_alias:
            return False

        if node_id not in self.data["nodes"]:
            logger.warning(f"Device {node_id} not found when adding alias '{clean_alias}'")
            return False

        n = self.data["nodes"][node_id]
        channels = n.setdefault("channels", {})
        ch = channels.setdefault(channel, {})
        aliases = ch.setdefault("aliases", [])

        if clean_alias not in aliases:
            aliases.append(clean_alias)
            cur_v = n.get("cfg_version", 1) + 1
            n["cfg_version"] = cur_v
            n["last_seen"] = datetime.now(TZ_VN).isoformat()
            self.save()
            logger.info(f"[VOCAB][STORE] saved alias '{clean_alias}' for {node_id}::{channel}")
            return True
        return True

    def remove_device_alias(self, node_id: str, channel: str, alias: str) -> bool:
        """Xóa từ vựng/khẩu lệnh của một kênh thiết bị và lưu persistent vào SQLite."""
        if not node_id or not alias:
            return False

        if "::" in node_id:
            parts = node_id.split("::", 1)
            node_id = parts[0]
            if not channel:
                channel = parts[1]

        channel = channel or "ch1"
        clean_alias = str(alias).strip().lower()

        if node_id not in self.data["nodes"]:
            return False

        n = self.data["nodes"][node_id]
        channels = n.get("channels", {})
        ch = channels.get(channel)
        if not ch or "aliases" not in ch:
            return False

        if clean_alias in ch["aliases"]:
            ch["aliases"].remove(clean_alias)
            cur_v = n.get("cfg_version", 1) + 1
            n["cfg_version"] = cur_v
            n["last_seen"] = datetime.now(TZ_VN).isoformat()
            self.save()
            logger.info(f"[VOCAB][STORE] removed alias '{clean_alias}' from {node_id}::{channel}")
            return True
        return True

    def get_provision_payload(self, node_id: str) -> Optional[dict]:
        """Payload cfg gửi xuống ESP32 theo đúng User Identity"""
        n = self.data["nodes"].get(node_id)
        if not n: return None
        cfg = n.get("configuration", {})
        relays = cfg.get("relays", {})
        ch1 = relays.get("ch1", {})
        ch2 = relays.get("ch2", {})
        payload = {
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
        if "ch3" in relays:
            payload["rl3"] = relays["ch3"].get("device_type", "switch")
        return payload

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

        if "name" in desired_dict: n["name"] = desired_dict["name"]
        if "room" in desired_dict:
            n["room"] = slug(desired_dict["room"])
            n["aliases"] = ROOM_ALIASES.get(n["room"], [n["room"]])
        if "location" in desired_dict: n["location"] = desired_dict["location"]
        if "description" in desired_dict: n["description"] = desired_dict["description"]

        rl1 = desired_dict.get("rl1", desired_dict.get("relay1"))
        rl2 = desired_dict.get("rl2", desired_dict.get("relay2"))
        rl3 = desired_dict.get("rl3", desired_dict.get("relay3"))
        if rl1 or rl2 or rl3:
            rl1_c = canon_device(rl1) if rl1 else "light"
            rl2_c = canon_device(rl2) if rl2 else "fan"
            rl3_c = canon_device(rl3) if rl3 else "switch"
            n.setdefault("channels", {})
            n["channels"]["ch1"] = {
                "device_type": rl1_c, "fullname": f"{device_id}-{rl1_c}",
                "name": rl1 or "Đèn", "aliases": [rl1_c], "gpio": 4, "rated_watts": 40
            }
            n["channels"]["ch2"] = {
                "device_type": rl2_c, "fullname": f"{device_id}-{rl2_c}",
                "name": rl2 or "Quạt", "aliases": [rl2_c], "gpio": 5, "rated_watts": 55
            }
            cfg_relays = {
                "ch1": {"device_type": rl1_c, "fullname": f"{device_id}-{rl1_c}", "name": rl1 or "Đèn", "gpio": 4},
                "ch2": {"device_type": rl2_c, "fullname": f"{device_id}-{rl2_c}", "name": rl2 or "Quạt", "gpio": 5}
            }
            if rl3:
                n["channels"]["ch3"] = {
                    "device_type": rl3_c, "fullname": f"{device_id}-{rl3_c}",
                    "name": rl3 or "Công tắc", "aliases": [rl3_c], "gpio": 5, "rated_watts": 100
                }
                cfg_relays["ch3"] = {
                    "device_type": rl3_c, "fullname": f"{device_id}-{rl3_c}", "name": rl3 or "Công tắc", "gpio": 5
                }
            elif "ch3" in (n.get("channels") or {}):
                cfg_relays["ch3"] = {
                    "device_type": (n.get("channels") or {}).get("ch3", {}).get("device_type", "switch"),
                    "fullname": (n.get("channels") or {}).get("ch3", {}).get("fullname", f"{device_id}-switch"),
                    "name": (n.get("channels") or {}).get("ch3", {}).get("name", "Công tắc"),
                    "gpio": (n.get("channels") or {}).get("ch3", {}).get("gpio", 5)
                }
            n.setdefault("configuration", {})["relays"] = cfg_relays
            if "ch3" in (n.get("channels") or {}):
                caps = n.setdefault("capabilities", [])
                if "relay_2ch" in caps:
                    n["capabilities"] = [c if c != "relay_2ch" else "relay_3ch" for c in caps]
                elif "relay_3ch" not in caps:
                    caps.append("relay_3ch")

        cur_rl = list(n.get("relay_state") or [0, 0])
        while len(cur_rl) < len(n.get("channels") or {}):
            cur_rl.append(0)
        n["relay_state"] = cur_rl

        self._sync_node_to_sqlite(device_id, n)

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
        if "ch3" in n.get("channels", {}) or rl3:
            desired_payload["rl3"] = n.get("channels", {}).get("ch3", {}).get("device_type", "switch")
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

            if device_id in self.data["pending"]:
                p = self.data["pending"][device_id]
                p["cfg"] = rep_v
                p["last_seen"] = now
                self.save()
            logger.debug(f"Reported config from unprovisioned device [{device_id}] (cfg_version={rep_v})")
            return "UNPROVISIONED"

    def record_telemetry(self, device_id: str, telemetry_dict: dict):
        """Lưu bản ghi telemetry từ ESP32 vào SQLite và cập nhật node không chặn event loop"""
        try:
            v = float(telemetry_dict.get("voltage", telemetry_dict.get("v", 0.0)))
            c = float(telemetry_dict.get("current", telemetry_dict.get("c", 0.0)))
            p = float(telemetry_dict.get("power", telemetry_dict.get("p", 0.0)))
            e = float(telemetry_dict.get("energy", telemetry_dict.get("e", 0.0)))
            heap = int(telemetry_dict.get("free_heap", telemetry_dict.get("heap", 0)))
            rssi = int(telemetry_dict.get("wifi_rssi", telemetry_dict.get("rssi", 0)))

            if device_id in self.data["nodes"]:
                n = self.data["nodes"][device_id]
                n["last_telemetry"] = {
                    "voltage": v, "current": c, "power": p, "energy": e,
                    "free_heap": heap, "rssi": rssi,
                    "recorded_at": datetime.now(TZ_VN).isoformat()
                }
                if rssi: n["rssi"] = rssi
                if n.get("status") != "NEEDS_REPROVISION":
                    n["last_seen"] = datetime.now(TZ_VN).isoformat()
                    n["status"] = "online"

                # Store per-channel telemetry when device provides it
                channels_data = telemetry_dict.get("channels")
                if isinstance(channels_data, dict):
                    for ch_id, ch_val in channels_data.items():
                        if isinstance(ch_val, dict):
                            ch_target = n.setdefault("channels", {}).setdefault(ch_id, {})
                            if "telemetry" in ch_val and isinstance(ch_val["telemetry"], dict):
                                ch_target["telemetry"] = ch_val["telemetry"]
                            else:
                                ch_target["telemetry"] = {
                                    "power_w": float(ch_val.get("power_w", ch_val.get("power", ch_val.get("p", 0.0)))),
                                    "voltage_v": float(ch_val.get("voltage_v", ch_val.get("voltage", ch_val.get("v", v)))),
                                    "current_a": float(ch_val.get("current_a", ch_val.get("current", ch_val.get("c", 0.0)))),
                                    "energy_wh": float(ch_val.get("energy_wh", ch_val.get("energy", ch_val.get("e", 0.0)))),
                                }
                for ch_id in ("ch1", "ch2", "ch3"):
                    if ch_id in telemetry_dict and isinstance(telemetry_dict[ch_id], dict):
                        ch_val = telemetry_dict[ch_id]
                        ch_target = n.setdefault("channels", {}).setdefault(ch_id, {})
                        if "telemetry" in ch_val and isinstance(ch_val["telemetry"], dict):
                            ch_target["telemetry"] = ch_val["telemetry"]
                        else:
                            ch_target["telemetry"] = {
                                "power_w": float(ch_val.get("power_w", ch_val.get("power", ch_val.get("p", 0.0)))),
                                "voltage_v": float(ch_val.get("voltage_v", ch_val.get("voltage", ch_val.get("v", v)))),
                                "current_a": float(ch_val.get("current_a", ch_val.get("current", ch_val.get("c", 0.0)))),
                                "energy_wh": float(ch_val.get("energy_wh", ch_val.get("energy", ch_val.get("e", 0.0)))),
                            }

            node_snapshot = copy.deepcopy(self.data["nodes"][device_id]) if device_id in self.data["nodes"] else None

            def _db_work(snapshot=node_snapshot):
                try:
                    with self._get_db() as conn:
                        conn.execute("""
                            INSERT INTO telemetry_records (
                                device_id, voltage, current, power, energy, free_heap, wifi_rssi
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (device_id, v, c, p, e, heap, rssi))

                        if snapshot is not None:
                            self._sync_node_to_sqlite(device_id, snapshot, connection=conn)

                    self._telemetry_write_count += 1
                    if self._telemetry_write_count % 500 == 0:
                        self.prune_telemetry()
                except Exception as ex:
                    logger.warning(f"Async DB telemetry write failed for {device_id}: {ex}")

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(asyncio.to_thread(_db_work))
            except RuntimeError:
                _db_work()

        except Exception as err:
            logger.warning(f"record_telemetry error for {device_id}: {err}")

    async def record_telemetry_async(self, device_id: str, telemetry_dict: dict):
        """Asynchronously record telemetry without blocking the asyncio loop."""
        await asyncio.to_thread(self.record_telemetry, device_id, telemetry_dict)

    def record_channel_telemetry(self, device_id: str, channels: Dict[str, dict]) -> int:
        """Persist per-channel samples exactly as reported.

        Null voltage/power/energy values stay NULL. Invalid or stale samples are
        recorded with their quality so history can expose gaps instead of
        inventing zero watts.
        """
        if not device_id or not isinstance(channels, dict):
            return 0
        rows = []
        for ch_key, meter in channels.items():
            if not isinstance(ch_key, str) or not re.fullmatch(r"ch[1-3]", ch_key):
                continue
            if not isinstance(meter, dict):
                continue
            values = []
            for key in ("current_ma", "voltage_v", "power_w"):
                value = meter.get(key)
                values.append(float(value) if type(value) in (int, float) and math.isfinite(value) else None)
            valid = meter.get("valid") is True
            quality = meter.get("quality") if isinstance(meter.get("quality"), str) else ("good" if valid else "invalid")
            sample = meter.get("sample_uptime_ms")
            sample = sample if type(sample) is int and 0 <= sample <= 0xffffffff else None
            received = meter.get("received_at")
            received = float(received) if type(received) in (int, float) and math.isfinite(received) else time.time()
            rows.append((device_id, ch_key, *values, int(valid), quality, sample, received))
        if not rows:
            return 0
        try:
            with self._get_db() as conn:
                conn.executemany("""
                    INSERT INTO channel_telemetry_records (
                        device_id, channel, current_ma, voltage_v, power_w,
                        valid, quality, sample_uptime_ms, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
            return len(rows)
        except Exception as e:
            logger.error(f"record_channel_telemetry error for {device_id}: {e}")
            return 0

    def get_channel_telemetry_history(self, device_id: str, channel: Optional[str] = None,
                                      limit: int = 50) -> List[dict]:
        """Return newest channel samples in chronological order, nulls preserved."""
        try:
            limit = max(1, min(int(limit), 1000))
        except (TypeError, ValueError):
            limit = 50
        if channel is not None and not re.fullmatch(r"ch[1-3]", str(channel)):
            return []
        try:
            with self._get_db() as conn:
                if channel:
                    rows = conn.execute("""
                        SELECT * FROM channel_telemetry_records
                        WHERE device_id = ? AND channel = ?
                        ORDER BY id DESC LIMIT ?
                    """, (device_id, channel, limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM channel_telemetry_records
                        WHERE device_id = ?
                        ORDER BY id DESC LIMIT ?
                    """, (device_id, limit)).fetchall()
                result = []
                for row in reversed(rows):
                    record = dict(row)
                    record["valid"] = bool(record.get("valid"))
                    result.append(record)
                return result
        except Exception as e:
            logger.error(f"get_channel_telemetry_history error for {device_id}: {e}")
            return []

    def prune_telemetry(self, max_records: int = 50000, retention_days: int = 7) -> int:
        """
        Dọn dẹp (pruning/retention) dữ liệu telemetry:
        - Xóa bản ghi cũ hơn retention_days (mặc định 7 ngày).
        - Nếu vượt quá max_records (mặc định 50.000), xóa bản ghi cũ nhất vượt hạn mức.
        """
        deleted = 0
        try:
            with self._get_db() as conn:
                # 1. Prune by retention days
                res1 = conn.execute(
                    "DELETE FROM telemetry_records WHERE recorded_at < datetime('now', ?)",
                    (f"-{int(retention_days)} days",)
                )
                if res1.rowcount and res1.rowcount > 0:
                    deleted += res1.rowcount

                res1c = conn.execute(
                    "DELETE FROM channel_telemetry_records WHERE recorded_at < datetime('now', ?)",
                    (f"-{int(retention_days)} days",)
                )
                if res1c.rowcount and res1c.rowcount > 0:
                    deleted += res1c.rowcount

                # 2. Prune by max records cap
                cnt_row = conn.execute("SELECT COUNT(*) FROM telemetry_records").fetchone()
                total_cnt = cnt_row[0] if cnt_row else 0
                if total_cnt > max_records:
                    overflow = total_cnt - max_records
                    res2 = conn.execute("""
                        DELETE FROM telemetry_records WHERE id IN (
                            SELECT id FROM telemetry_records ORDER BY id ASC LIMIT ?
                        )
                    """, (overflow,))
                    if res2.rowcount and res2.rowcount > 0:
                        deleted += res2.rowcount

                cnt_row = conn.execute("SELECT COUNT(*) FROM channel_telemetry_records").fetchone()
                total_cnt = cnt_row[0] if cnt_row else 0
                if total_cnt > max_records:
                    overflow = total_cnt - max_records
                    res2c = conn.execute("""
                        DELETE FROM channel_telemetry_records WHERE id IN (
                            SELECT id FROM channel_telemetry_records ORDER BY id ASC LIMIT ?
                        )
                    """, (overflow,))
                    if res2c.rowcount and res2c.rowcount > 0:
                        deleted += res2c.rowcount

            if deleted > 0:
                logger.info(f"🧹 [Telemetry Prune] Cleaned {deleted} records (retention={retention_days}d, max={max_records})")
        except Exception as e:
            logger.error(f"prune_telemetry error: {e}")
        return deleted

    async def prune_telemetry_async(self, max_records: int = 50000, retention_days: int = 7) -> int:
        return await asyncio.to_thread(self.prune_telemetry, max_records=max_records, retention_days=retention_days)

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

    def find_device_candidates(self, device_type: str, area: str = None) -> List[Tuple[str, str]]:
        """
        Từ intent (device, location) → (node_id, channel).
        - device_type/location có thể là None → suy luận
        - chỉ trả về node online và channel tồn tại trong registry, KHÔNG bịa
        """
        query = slug(device_type) if device_type else ""
        dev = canon_device(device_type) if device_type else ""
        area_s = slug(area) if area else ""

        def matches_channel(ch_id: str, ch: dict) -> bool:
            if not dev: return True
            cid_s = slug(ch_id)
            if dev in (cid_s, f"relay_{cid_s[-1]}", f"cong_tac_{cid_s[-1]}", f"ch{cid_s[-1]}", f"relay{cid_s[-1]}", f"kenh_{cid_s[-1]}"):
                return True
            ct = slug(ch.get("device_type", ""))
            aliases = [slug(a) for a in ch.get("aliases", [])]
            dev_c = canon_device(dev)
            ct_c = canon_device(ct)
            if dev_c == ct_c or any(dev_c == canon_device(a) for a in aliases): return True
            if dev == slug(ch.get('name', '')) or dev == slug(ch.get('fullname', '')): return True
            if dev == ct or dev in aliases or (ct and ct in dev): return True

            if ct and (dev in ct or ct in dev): return True
            if any(dev in a or a in dev for a in aliases): return True
            return False

        def matches_room(node: dict) -> bool:
            if not area_s or area_s in ("all","any","none","unknown"): return True
            nr = slug(node.get("room",""))
            aliases = [slug(a) for a in node.get("aliases", [])]
            if area_s == nr or area_s in nr or nr in area_s: return True
            if any(area_s in a or a in area_s for a in aliases): return True

            for canon, alist in ROOM_ALIASES.items():
                if area_s in [slug(x) for x in alist] and nr == canon: return True
                if nr in [slug(x) for x in alist] and area_s == canon: return True
            return False

        now_utc = datetime.now(timezone.utc)
        candidates = []
        for nid, node in self.data["nodes"].items():
            if node.get("status") != "online" or nid in self.get_pending(): continue
            if str(nid).upper().startswith("SB") or "subbox" in str(nid).lower(): continue

            last_seen_str = node.get("last_seen")
            if last_seen_str and not node.get("mac"):
                try:
                    dt = datetime.fromisoformat(last_seen_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now_utc - dt).total_seconds() > 300:
                        continue
                except Exception:
                    pass
            if not matches_room(node): continue
            for ch_id, ch in node.get("channels", {}).items():
                if matches_channel(ch_id, ch): candidates.append((nid, ch_id))
        if query and query not in DEVICE_CANON:
            exact = [(nid, cid) for nid, cid in candidates
                     if query in [slug(self.data["nodes"][nid]["channels"][cid].get("name", "")),
                                  *[slug(a) for a in self.data["nodes"][nid]["channels"][cid].get("aliases", [])]]]
            if exact:
                return exact
        return candidates

    def find_node_by_device(self, device_type: str, area: str = None) -> Optional[Tuple[str, str]]:
        candidates = self.find_device_candidates(device_type, area)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def resolve_fullname(self, node_id: str, channel: str) -> str:
        ch = self.data["nodes"].get(node_id, {}).get("channels", {}).get(channel, {})
        return ch.get("fullname", f"{node_id}-{channel}")

    def next_seq(self, node_id: str) -> int:
        self._seq[node_id] = (self._seq.get(node_id, 0) + 1) & 0xFFFF
        return self._seq[node_id]

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

        rooms.update(["phong_khach", "phong_ngu", "phong_bep", "phong_tam", "ban_cong"])
        return sorted(rooms)

    def allowed_devices(self) -> List[str]:
        devs = set()
        for n in self.data["nodes"].values():
            for ch in n.get("channels", {}).values():
                if ch.get("name"):
                    devs.add(slug(ch["name"]))
                dt = slug(ch.get("device_type", ""))
                if dt: devs.add(dt)
                for a in ch.get("aliases", []):
                    sa = slug(a)
                    if sa: devs.add(sa)

        devs.update(["den", "quat", "tivi", "dieu_hoa", "binh_nong_lanh", "den_ngu", "den_tran", "light", "fan", "socket", "switch", "o_cam", "ch1", "ch2", "ch3", "relay_1", "relay_2", "relay_3", "all"])
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

    def get_all_nodes(self) -> dict: return self.data.get("nodes", {})

    def get_user_accessible_nodes(self, user: Optional[dict] = None) -> dict:
        """Trả về danh sách nodes mà user được phép truy cập theo phân quyền."""
        all_nodes = self.get_all_nodes()
        if not user or user.get("role") == "admin":
            return all_nodes
        gw = getattr(self, "gateway", None)
        auth = getattr(gw, "auth", None) if gw else getattr(self, "auth", None)
        if auth and hasattr(auth, "filter_nodes"):
            return auth.filter_nodes(user, all_nodes)
        if auth and hasattr(auth, "get_user_devices") and "id" in user:
            allowed = set(auth.get_user_devices(user["id"]))
            return {k: v for k, v in all_nodes.items() if k in allowed}
        if "device_ids" in user:
            allowed = set(user["device_ids"])
            return {k: v for k, v in all_nodes.items() if k in allowed}
        return {}

    def get_node_owner_epoch(self, node_id: str) -> int:
        """Trả về owner_epoch hiện tại của node từ registry, mặc định 0 nếu chưa set."""
        node = self.get_all_nodes().get(node_id, {})
        return int(node.get("owner_epoch", node.get("epoch", 0)))

    def update_node_owner_epoch(self, node_id: str, epoch: int):
        """Cập nhật owner_epoch cho node đã tồn tại trong registry."""
        if node_id in self.data.get("nodes", {}):
            try:
                new_epoch = int(epoch)
            except (ValueError, TypeError):
                return
            curr_epoch = self.get_node_owner_epoch(node_id)
            if new_epoch < curr_epoch:
                logger.warning(f"Ignored stale owner_epoch {new_epoch}")
                return
            self.data["nodes"][node_id]["owner_epoch"] = new_epoch
            self._sync_node_to_sqlite(node_id, self.data["nodes"][node_id])
            self.save()
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
            if self.data['nodes'][node_id].get('status') == 'NEEDS_REPROVISION':
                return
            self.data["nodes"][node_id]["last_seen"] = datetime.now(TZ_VN).isoformat()
            node = self.data["nodes"][node_id]
            node["status"] = "offline" if node.get("reported_claimed") is False else "online"
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(asyncio.to_thread(self.save, node_id))
            except RuntimeError:
                self.save(changed_node=node_id)

    async def update_heartbeat_async(self, node_id: str):
        """Execute heartbeat persistence in worker thread."""
        await asyncio.to_thread(self.update_heartbeat, node_id)

    async def save_async(self, changed_node=None):
        """Execute SQLite registry persistence in worker thread."""
        await asyncio.to_thread(self.save, changed_node)
    def mark_offline(self, node_id: str):
        if node_id in self.data["nodes"]:
            self.data["nodes"][node_id]["status"] = "offline"
            self.save(changed_node=node_id)
            logger.warning(f"Node offline: {node_id}")

    def register_zone(self, zone_id: str, display_name: str, controller_id: Optional[str] = None):
        """Đăng ký Zone (Tầng 2) quản lý một cụm các node chấp hành T1."""
        try:
            with self._get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO zones (zone_id, display_name, controller_id) VALUES (?, ?, ?)",
                    (zone_id, display_name, controller_id)
                )
                logger.info(f"🏡 Registered Zone: {zone_id} ({display_name}), controller={controller_id}")
        except Exception as e:
            logger.error(f"Failed to register zone {zone_id}: {e}")

    def get_zones(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả các Zone trong hệ thống 3 tầng."""
        try:
            with self._get_db() as conn:
                rows = conn.execute("SELECT * FROM zones ORDER BY zone_id ASC").fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get zones: {e}")
            return []

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin một Zone cụ thể."""
        try:
            with self._get_db() as conn:
                row = conn.execute("SELECT * FROM zones WHERE zone_id = ?", (zone_id,)).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get zone {zone_id}: {e}")
            return None

    def assign_device_zone(self, device_id: str, zone_id: str):
        """Gán node T1 hoặc controller T2 vào Zone."""
        try:
            with self._get_db() as conn:
                conn.execute("UPDATE devices SET zone_id = ? WHERE device_id = ?", (zone_id, device_id))
            if device_id in self.data["nodes"]:
                self.data["nodes"][device_id]["zone_id"] = zone_id
            logger.info(f"🔗 Assigned node {device_id} to zone {zone_id}")
        except Exception as e:
            logger.error(f"Failed to assign device to zone: {e}")

    def get_zone_nodes(self, zone_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách thiết bị thuộc một Zone."""
        try:
            with self._get_db() as conn:
                rows = conn.execute("SELECT * FROM devices WHERE zone_id = ?", (zone_id,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get nodes in zone {zone_id}: {e}")
            return []
