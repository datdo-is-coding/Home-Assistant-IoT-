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
        self.data: Dict[str, Any] = {"nodes": {}, "pending": {}, "rooms": {}}
        self._seq: Dict[str, int] = {}  # node_id -> last seq
        self.load()

    # ── Persistence ─────────────────────────────────────────────────────
    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # migrate old schema
            if "nodes" in raw:
                self.data["nodes"] = raw.get("nodes", {})
                self.data["pending"] = raw.get("pending", {})
                self.data["rooms"] = raw.get("rooms", {})
                # migrate từng node cũ: area->room, channels->{rl1,rl2} + fullname
                for nid, n in list(self.data["nodes"].items()):
                    self._migrate_node(nid, n)
                self._rebuild_rooms()
                logger.info(f"Registry loaded: {len(self.data['nodes'])} nodes, {len(self.data['pending'])} pending")
            else:
                self.data = {"nodes": {}, "pending": {}, "rooms": {}}
        else:
            self.save()
            logger.info("Created empty registry v2")

    def _migrate_node(self, nid: str, n: dict):
        if "room" not in n and "area" in n:
            n["room"] = slug(n.pop("area"))
        n.setdefault("room", "unknown")
        n.setdefault("aliases", [])
        n.setdefault("cfg_version", 1)
        n.setdefault("status", "online")
        n.setdefault("mac", n.get("mac", ""))
        # channels -> chuẩn hoá device_type + fullname
        for ch_id, ch in list(n.get("channels", {}).items()):
            if "device_type" in ch:
                dt = canon_device(ch["device_type"])
                ch["device_type"] = dt
                ch.setdefault("fullname", f"{nid}-{dt}")
                ch.setdefault("aliases", [])
        # pending phải có last_seen
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

    # ── HELLO / Pending flow ────────────────────────────────────────────
    def on_hello(self, payload: dict, ws_available: bool = False) -> dict:
        """
        Xử lý gói {"t":"hello", "mac":..., "id":..., "rl":[...], "cfg":n, ...}
        Trả về {"action":"pending"|"known"|"cfg_mismatch", "node_id":...}
        """
        mac = (payload.get("mac") or "").upper()
        node_id = payload.get("id")
        cfg = payload.get("cfg")
        rl = payload.get("rl", [0, 0])
        rssi = payload.get("rssi")
        ip = payload.get("ip")
        now = datetime.now(TZ_VN).isoformat()

        # Đã provision và có trong registry → update heartbeat
        if node_id and node_id in self.data["nodes"]:
            n = self.data["nodes"][node_id]
            n["last_seen"] = now
            n["status"] = "online"
            if rssi is not None: n["rssi"] = rssi
            if ip: n["ip"] = ip
            n["relay_state"] = rl
            # phát hiện lệch cfg
            expected = n.get("cfg_version", 1)
            if cfg is not None and cfg != expected:
                logger.warning(f"cfg mismatch {node_id}: node cfg={cfg} expected={expected} → will re-provision")
                self.save()
                return {"action": "cfg_mismatch", "node_id": node_id, "expected": expected, "got": cfg}
            self.save()
            return {"action": "known", "node_id": node_id}

        # Chưa biết → cho vào pending theo MAC
        if mac:
            self.data["pending"][mac] = {
                "mac": mac, "ip": ip, "rssi": rssi, "rl": rl,
                "cfg": cfg, "last_seen": now, "ws_available": ws_available
            }
            # nếu mac này từng là node_id cũ dạng mac-based thì giữ
            self.save()
            logger.info(f"Pending node hello: MAC={mac} cfg={cfg} ip={ip}")
            return {"action": "pending", "mac": mac}

        return {"action": "ignored"}

    def provision_node(self, mac: str, room: str, rl1: str, rl2: str,
                       node_short: str = None, description: str = None) -> Optional[dict]:
        """
        WebUI gọi khi user gán phòng + tên thiết bị cho node pending.
        Tạo node_id = {room}-{node_short} (tự tăng nếu trùng).
        """
        mac = mac.upper()
        if mac not in self.data["pending"]:
            logger.error(f"provision: pending MAC not found: {mac}")
            return None
        room_s = slug(room)
        rl1_c = canon_device(rl1) if rl1 else ""
        rl2_c = canon_device(rl2) if rl2 else ""
        if not rl1_c and not rl2_c:
            logger.error("provision: at least one of rl1/rl2 required")
            return None

        # node_short tự sinh nếu không truyền
        if not node_short:
            existing = [nid for nid in self.data["nodes"] if nid.startswith(room_s + "-")]
            node_short = f"node{len(existing)+1:02d}"
        node_short = slug(node_short).replace("_","")
        node_id = f"{room_s}-{node_short}"
        # tránh trùng
        suffix = 1
        base = node_id
        while node_id in self.data["nodes"]:
            suffix += 1
            node_id = f"{base}_{suffix}"

        pending = self.data["pending"].pop(mac)
        now = datetime.now(TZ_VN).isoformat()
        channels: Dict[str, dict] = {}
        if rl1_c:
            channels["ch1"] = {
                "device_type": rl1_c, "fullname": f"{node_id}-{rl1_c}",
                "aliases": [rl1_c], "gpio": 4, "rated_watts": 40,
                "description": rl1_c
            }
        if rl2_c:
            channels["ch2"] = {
                "device_type": rl2_c, "fullname": f"{node_id}-{rl2_c}",
                "aliases": [rl2_c], "gpio": 5, "rated_watts": 55,
                "description": rl2_c
            }

        self.data["nodes"][node_id] = {
            "mac": mac, "room": room_s,
            "aliases": ROOM_ALIASES.get(room_s, [room_s]),
            "description": description or f"Node {node_id} ({room_s})",
            "channels": channels,
            "sensors": {"pzem": True, "temperature": False},
            "cfg_version": 1,
            "relay_state": pending.get("rl", [0, 0]),
            "ip": pending.get("ip"), "rssi": pending.get("rssi"),
            "registered_at": now, "last_seen": now, "status": "online",
        }
        self.save()
        logger.info(f"Provisioned {mac} → {node_id} room={room_s} rl1={rl1_c} rl2={rl2_c}")
        return self.data["nodes"][node_id] | {"node_id": node_id, "room_s": room_s, "rl1": rl1_c, "rl2": rl2_c}

    def get_provision_payload(self, node_id: str) -> Optional[dict]:
        """Payload cfg gửi xuống ESP32: {"t":"cfg","id":...,"room":...,"rl1":...,"rl2":...,"v":n}"""
        n = self.data["nodes"].get(node_id)
        if not n: return None
        ch1 = n.get("channels", {}).get("ch1", {})
        ch2 = n.get("channels", {}).get("ch2", {})
        return {
            "t": "cfg", "id": node_id, "room": n.get("room", "unknown"),
            "rl1": ch1.get("device_type", ""), "rl2": ch2.get("device_type", ""),
            "v": n.get("cfg_version", 1)
        }

    def bump_cfg_version(self, node_id: str) -> int:
        n = self.data["nodes"].get(node_id)
        if not n: return 0
        n["cfg_version"] = int(n.get("cfg_version", 1)) + 1
        self.save()
        return n["cfg_version"]

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
