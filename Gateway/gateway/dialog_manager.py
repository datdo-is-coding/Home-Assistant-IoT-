"""
DTV Smart Home Gateway — Multi-Turn Dialog & Slot-Filling Manager.
Quản lý hội thoại đa lượt, tự động phát hiện lệnh thiếu tham số (phòng, thiết bị, nhiệt độ),
và sinh câu hỏi làm rõ (clarification question) kèm cờ follow-up để ESP32 tự động mở mic.
"""

import time
import re
import logging
from copy import deepcopy
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from registry_manager import ROOM_ALIASES
from display_names import get_room_name, get_device_name, clean_voice_text

logger = logging.getLogger("dialog_manager")

def _slug(s: str) -> str:
    if not s:
        return ""
    s = str(s).lower().strip()
    tbl = str.maketrans("áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
                        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd")
    s = s.translate(tbl)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s

@dataclass
class DialogSession:
    """Lưu trữ trạng thái phiên hỏi đáp dở dang giữa Gateway và một Node."""
    node_id: str
    client_id: str
    pending_intent: Dict[str, Any]
    missing_slot: str
    detected_room: Optional[str] = None
    candidates: list = field(default_factory=list)
    clarification_attempts: int = 0
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 15.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds

class DialogManager:
    """Quản lý các phiên hội thoại đa lượt và điền slot còn thiếu."""

    def __init__(self, registry=None):
        self.registry = registry

        self._sessions: Dict[str, DialogSession] = {}

    def set_registry(self, registry):
        self.registry = registry

    def get_active_session(self, client_key: str) -> Optional[DialogSession]:
        """Lấy phiên hội thoại còn hiệu lực của node/client."""
        session = self._sessions.get(client_key)
        if session:
            if session.is_expired:
                logger.info(f"⏳ Dialog session for {client_key} expired (15s timeout)")
                self._sessions.pop(client_key, None)
                return None
            return session
        return None

    def clear_session(self, client_key: str):
        """Xóa phiên hội thoại sau khi hoàn tất lệnh hoặc hủy bỏ."""
        self._sessions.pop(client_key, None)

    def inspect_intent(
        self,
        intent: Dict[str, Any],
        detected_room: Optional[str] = None,
        client_key: str = "default"
    ) -> Tuple[bool, Optional[str], Optional[str], Dict[str, Any]]:
        """
        Kiểm tra xem ý định trích xuất có bị thiếu thông tin hoặc mơ hồ không:
        Returns:
            (needs_clarification: bool, question: str, missing_slot: str, updated_intent: dict)
        """
        if not intent or "command" not in intent:
            return False, None, None, intent

        cmd = intent["command"]
        action = cmd.get("action")
        device = _slug(cmd.get("device"))
        location = _slug(cmd.get("location"))
        value = cmd.get("value")

        if not location and detected_room:
            logger.info(f"📍 Spatial Audio: Inferred room '{detected_room}' for ambiguous command")
            location = _slug(detected_room)
            cmd["location"] = location

        if device in ("dieu_hoa", "may_lanh", "air_conditioner", "dieuhoa", "maylanh", "ac") and action in ("turn_on", "set"):

            if value is None:
                r_name = get_room_name(location)
                loc_str = f"ở {r_name}" if r_name else ""
                question = clean_voice_text(f"Cài đặt điều hòa {loc_str} bao nhiêu độ?")
                session = DialogSession(
                    node_id=client_key, client_id=client_key,
                    pending_intent=intent, missing_slot="value", detected_room=location
                )
                self._sessions[client_key] = session
                logger.info(f"❓ Clarification needed (dieu_hoa temperature): {question}")
                return True, question, "value", intent

        if self.registry and device and device != "all" and not cmd.get("node_id") and "targets" not in cmd:
            candidates = self.registry.find_device_candidates(device, location)
            if len(candidates) > 1:
                nodes = self.registry.get_all_nodes()
                labels = []
                for nid, cid in candidates:
                    node = nodes[nid]
                    room = _slug(node.get("room", ""))
                    room = next((key for key, aliases in ROOM_ALIASES.items() if room in aliases), room)
                    labels.append(f"{get_device_name(node['channels'][cid])} ở {get_room_name(room)}, "
                                  f"kênh {cid[-1]} bo {nid[-4:]}")
                action_name = "bật" if action == "turn_on" else "tắt"
                question = f"Bạn muốn {action_name} " + " hay ".join(labels[:3]) + "?"
                self._sessions[client_key] = DialogSession(
                    node_id=client_key, client_id=client_key, pending_intent=intent,
                    missing_slot="channel", detected_room=location, candidates=candidates[:3])
                return True, question, "channel", intent

        return False, None, None, intent

    def fill_slot(self, session: DialogSession, follow_up_text: str) -> Dict[str, Any]:
        """
        Gộp câu trả lời tiếp nối của người dùng vào phiên hội thoại dở dang.
        Ví dụ:
          - Đang thiếu 'value' (nhiệt độ) -> Người dùng nói "26 độ" -> gán value=26
          - Đang thiếu 'location' (phòng) -> Người dùng nói "phòng ngủ" -> gán location=phong_ngu
          - Đang thiếu 'channel' (loại đèn) -> Người dùng nói "đèn trần" -> gán device=den_tran
        """
        intent = deepcopy(session.pending_intent)
        cmd = intent.setdefault("command", {})
        missing = session.missing_slot
        norm_text = follow_up_text.lower().strip()

        logger.info(f"🧩 Merging slot [{missing}] from follow-up text: '{follow_up_text}'")

        if missing == "value":

            num_match = re.search(r"(\d{2})", norm_text)
            if num_match:
                val = int(num_match.group(1))
                cmd["value"] = val
                intent["voice_reply"] = f"Đã cài đặt điều hòa {val} độ ạ."
            else:

                text_map = {"hai lam": 25, "hai muoi lam": 25, "hai sau": 26, "hai bay": 27, "hai tam": 28}
                found = False
                for k, v in text_map.items():
                    if k in _slug(norm_text):
                        cmd["value"] = v
                        intent["voice_reply"] = f"Đã cài đặt điều hòa {v} độ ạ."
                        found = True
                        break
                if not found:
                    cmd["value"] = 26

        elif missing == "location":

            found_room = None
            room_map = [
                (r"\b(phòng ngủ master|phòng master|ngủ master)\b", "phong_ngu_master"),
                (r"\b(phòng ngủ con|ngủ con)\b", "phong_ngu_con"),
                (r"\b(phòng ngủ|phong ngu|bedroom|ngủ)\b", "phong_ngu"),
                (r"\b(phòng khách|phong khach|living room|livingroom|khách)\b", "phong_khach"),
                (r"\b(phòng bếp|phong bep|bếp|nhà bếp|kitchen)\b", "phong_bep"),
                (r"\b(nhà vệ sinh|vệ sinh|toilet|wc|phòng tắm|bathroom|tắm)\b", "phong_ve_sinh"),
                (r"\b(ban công|balcony)\b", "ban_cong"),
                (r"\b(sân thượng|rooftop)\b", "san_thuong"),
                (r"\b(sân vườn|ngoài sân|vườn|san vuon|garden)\b", "san_vuon"),
                (r"\b(gara|nhà xe|ga ra)\b", "gara"),
                (r"\b(phòng thờ)\b", "phong_tho"),
                (r"\b(phòng làm việc|làm việc|phòng học)\b", "phong_lam_viec"),
                (r"\b(hành lang|cầu thang)\b", "hanh_lang"),
            ]
            for pat, r_id in room_map:
                if re.search(pat, norm_text):
                    found_room = r_id
                    break
            if not found_room and self.registry:
                for r in self.registry.allowed_rooms():
                    if r in _slug(norm_text) or _slug(norm_text) in r:
                        found_room = r
                        break
            cmd["location"] = found_room

        elif missing == "channel":
            if session.candidates and self.registry:
                nodes = self.registry.get_all_nodes()
                answer = _slug(norm_text)
                action_match = re.match(r"^(bat|mo|tat|dong)_", answer)
                if action_match:
                    cmd["action"] = "turn_on" if action_match[1] in ("bat", "mo") else "turn_off"
                    answer = answer[action_match.end():]
                if answer in ("ca_hai", "ca_2", "ca_hai_cai", "hai_cai") and len(session.candidates) == 2:
                    cmd["targets"] = list(session.candidates)
                    return intent
                current = set(self.registry.find_device_candidates(None, cmd.get("location")))
                matches = []
                ordinal = {"cai_dau_tien": 0, "thu_nhat": 0, "mot": 0, "1": 0,
                           "cai_thu_hai": 1, "thu_hai": 1, "hai": 1, "2": 1,
                           "cai_thu_ba": 2, "thu_ba": 2, "ba": 2, "3": 2}.get(answer)
                for nid, cid in session.candidates:
                    if (nid, cid) not in current:
                        continue
                    ch = nodes[nid]["channels"][cid]
                    names = [_slug(ch.get("name", "")), *[_slug(a) for a in ch.get("aliases", [])]]
                    if answer in names or answer in (_slug(nid), _slug(nid[-4:])):
                        matches.append((nid, cid))
                if ordinal is not None and ordinal < len(session.candidates):
                    choice = session.candidates[ordinal]
                    matches = [choice] if choice in current else []
                if len(matches) == 1:
                    cmd["node_id"], cmd["channel"] = matches[0]
                return intent


            if any(w in norm_text for w in ("ngủ", "đầu giường", "bàn", "den ngu")):
                cmd["device"] = "den_ngu" if "den" in cmd.get("device", "") or cmd.get("device") == "light" else "quat_ban"
            elif any(w in norm_text for w in ("trần", "chiếu sáng", "chính", "chùm", "tuýp", "led")):
                cmd["device"] = "den_tran" if "den" in cmd.get("device", "") or cmd.get("device") == "light" else "quat_tran"
            elif any(w in norm_text for w in ("1", "một", "mot", "ch1", "relay 1", "công tắc 1", "kênh 1", "kenh 1")):
                cmd["device"] = "ch1"
            elif any(w in norm_text for w in ("2", "hai", "ch2", "relay 2", "công tắc 2", "kênh 2", "kenh 2")):
                cmd["device"] = "ch2"
            elif any(w in norm_text for w in ("3", "ba", "ch3", "relay 3", "công tắc 3", "kênh 3", "kenh 3")):
                cmd["device"] = "ch3"
            else:
                cmd["device"] = None

        return intent
