"""
DTV Smart Home Gateway — Multi-Turn Dialog & Slot-Filling Manager.
Quản lý hội thoại đa lượt, tự động phát hiện lệnh thiếu tham số (phòng, thiết bị, nhiệt độ),
và sinh câu hỏi làm rõ (clarification question) kèm cờ follow-up để ESP32 tự động mở mic.
"""

import time
import re
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

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
    missing_slot: str               # "location", "channel", "value"
    detected_room: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 15.0   # Hết hạn sau 15 giây nếu người dùng bỏ dở

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds


class DialogManager:
    """Quản lý các phiên hội thoại đa lượt và điền slot còn thiếu."""

    def __init__(self, registry=None):
        self.registry = registry
        # node_id / client_id -> DialogSession
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

        # 1. Tự động bù đắp phòng nếu Spatial Arbitration định vị được người dùng
        if not location and detected_room:
            logger.info(f"📍 Spatial Audio: Inferred room '{detected_room}' for ambiguous command")
            location = _slug(detected_room)
            cmd["location"] = location

        # 2. Kiểm tra điều hòa (dieu_hoa): nếu bật mà thiếu nhiệt độ
        if device in ("dieu_hoa", "may_lanh") and action == "turn_on":
            # Kiểm tra xem có số độ trong user_text hoặc value không
            if value is None:
                question = f"Bạn muốn cài đặt điều hòa {('ở ' + location) if location else ''} bao nhiêu độ ạ?"
                session = DialogSession(
                    node_id=client_key, client_id=client_key,
                    pending_intent=intent, missing_slot="value", detected_room=location
                )
                self._sessions[client_key] = session
                logger.info(f"❓ Clarification needed (dieu_hoa temperature): {question}")
                return True, question, "value", intent

        # 3. Kiểm tra kênh thiết bị bị trùng lặp trong phòng (ví dụ: phòng có cả đèn ngủ lẫn đèn trần)
        if self.registry and location and device:
            room_nodes = self.registry.get_rooms().get(location, [])
            matching_channels = []
            for nid in room_nodes:
                node = self.registry.get_all_nodes().get(nid, {})
                for ch_id, ch in node.get("channels", {}).items():
                    dt = _slug(ch.get("device_type", ""))
                    aliases = [_slug(a) for a in ch.get("aliases", [])]
                    desc = ch.get("description", "")
                    if device == dt or device in dt or any(device in a for a in aliases):
                        matching_channels.append(desc or ch.get("fullname", dt))

            if len(matching_channels) >= 2:
                # Phòng có nhiều đèn khác nhau mà người dùng chỉ nói "bật đèn"
                ch_names = " hay ".join(matching_channels[:2])
                question = f"Bạn muốn {('bật' if action == 'turn_on' else 'tắt')} {ch_names} ạ?"
                session = DialogSession(
                    node_id=client_key, client_id=client_key,
                    pending_intent=intent, missing_slot="channel", detected_room=location
                )
                self._sessions[client_key] = session
                logger.info(f"❓ Clarification needed (channel ambiguity in {location}): {question}")
                return True, question, "channel", intent

        # 4. Kiểm tra thiếu vị trí phòng khi cả nhà có nhiều thiết bị cùng loại
        if not location and device and self.registry:
            # Đếm xem cả nhà có bao nhiêu phòng có loại thiết bị này
            rooms_with_device = set()
            for nid, node in self.registry.get_all_nodes().items():
                if node.get("status") != "online":
                    continue
                nr = node.get("room", "")
                for ch_id, ch in node.get("channels", {}).items():
                    dt = _slug(ch.get("device_type", ""))
                    aliases = [_slug(a) for a in ch.get("aliases", [])]
                    if device == dt or device in dt or any(device in a for a in aliases):
                        if nr and nr != "unknown":
                            rooms_with_device.add(nr)

            if len(rooms_with_device) > 1:
                # Có nhiều phòng có thiết bị này -> BẮT BUỘC hỏi lại phòng!
                room_list_str = ", ".join(sorted(rooms_with_device))
                question = f"Bạn muốn {('bật' if action == 'turn_on' else 'tắt')} {device} ở phòng nào ạ? Hiện có {room_list_str}."
                session = DialogSession(
                    node_id=client_key, client_id=client_key,
                    pending_intent=intent, missing_slot="location", detected_room=None
                )
                self._sessions[client_key] = session
                logger.info(f"❓ Clarification needed (location ambiguity): {question}")
                return True, question, "location", intent

        # Đã đủ thông tin hoặc tự động giải quyết được
        return False, None, None, intent

    def fill_slot(self, session: DialogSession, follow_up_text: str) -> Dict[str, Any]:
        """
        Gộp câu trả lời tiếp nối của người dùng vào phiên hội thoại dở dang.
        Ví dụ:
          - Đang thiếu 'value' (nhiệt độ) -> Người dùng nói "26 độ" -> gán value=26
          - Đang thiếu 'location' (phòng) -> Người dùng nói "phòng ngủ" -> gán location=phong_ngu
          - Đang thiếu 'channel' (loại đèn) -> Người dùng nói "đèn trần" -> gán device=den_tran
        """
        intent = session.pending_intent
        cmd = intent.setdefault("command", {})
        missing = session.missing_slot
        norm_text = follow_up_text.lower().strip()

        logger.info(f"🧩 Merging slot [{missing}] from follow-up text: '{follow_up_text}'")

        if missing == "value":
            # Trích xuất số nhiệt độ (ví dụ: "25", "hai mươi sáu", "26 độ")
            num_match = re.search(r"(\d{2})", norm_text)
            if num_match:
                val = int(num_match.group(1))
                cmd["value"] = val
                intent["voice_reply"] = f"Đã cài đặt điều hòa {val} độ ạ."
            else:
                # Text số cơ bản
                text_map = {"hai lam": 25, "hai muoi lam": 25, "hai sau": 26, "hai bay": 27, "hai tam": 28}
                found = False
                for k, v in text_map.items():
                    if k in _slug(norm_text):
                        cmd["value"] = v
                        intent["voice_reply"] = f"Đã cài đặt điều hòa {v} độ ạ."
                        found = True
                        break
                if not found:
                    cmd["value"] = 26  # Giá trị mặc định an toàn

        elif missing == "location":
            # Tìm phòng trong câu trả lời
            if self.registry:
                for r in self.registry.allowed_rooms():
                    if r in _slug(norm_text) or _slug(norm_text) in r:
                        cmd["location"] = r
                        break
            if not cmd.get("location"):
                cmd["location"] = _slug(norm_text)

        elif missing == "channel":
            # Phân biệt đèn ngủ vs đèn trần, quạt bàn vs quạt trần
            if any(w in norm_text for w in ("ngu", "dau giuong", "ban")):
                cmd["device"] = "den_ngu" if "den" in cmd.get("device", "") else "quat_ban"
            elif any(w in norm_text for w in ("tran", "chieu sang", "chinh")):
                cmd["device"] = "den_tran" if "den" in cmd.get("device", "") else "quat_tran"
            else:
                cmd["device"] = _slug(norm_text)

        return intent
