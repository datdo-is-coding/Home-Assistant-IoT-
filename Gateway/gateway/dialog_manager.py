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
        if device in ("dieu_hoa", "may_lanh", "air_conditioner", "dieuhoa", "maylanh", "ac") and action in ("turn_on", "set"):
            # Kiểm tra xem có số độ trong user_text hoặc value không
            if value is None:
                r_name = get_room_name(location)
                loc_str = f"ở {r_name}" if r_name else ""
                question = clean_voice_text(f"Dạ anh muốn cài đặt điều hòa {loc_str} bao nhiêu độ vậy anh?")
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
                    if isinstance(ch, str):
                        dt = _slug(ch)
                        aliases = []
                        fullname = ch
                        ch_dict = {"device_type": dt, "fullname": fullname}
                    else:
                        dt = _slug(ch.get("device_type", ""))
                        aliases = [_slug(a) for a in ch.get("aliases", [])]
                        fullname = ch.get("fullname", dt)
                        ch_dict = ch

                    if device == dt or device in dt or any(device in a for a in aliases) or (device in ("light", "den") and "den" in dt):
                        friendly_dev = get_device_name(ch_dict)
                        if not friendly_dev or friendly_dev in ("đèn", "quạt"):
                            ch_num = ch_id[-1] if ch_id else "1"
                            friendly_dev = f"{friendly_dev or 'thiết bị'} {ch_num}"
                        if friendly_dev not in matching_channels:
                            matching_channels.append(friendly_dev)

            if len(matching_channels) >= 2:
                # Phòng có nhiều đèn khác nhau mà người dùng chỉ nói "bật đèn"
                ch_names = " hay ".join(matching_channels[:2])
                act_vn = "bật" if action == "turn_on" else "tắt"
                r_name = get_room_name(location)
                question = clean_voice_text(f"Dạ anh muốn {act_vn} {ch_names} {('ở ' + r_name) if r_name else ''} vậy ạ?")
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
                room_names = [get_room_name(r) for r in sorted(rooms_with_device)]
                room_list_str = ", ".join(room_names)
                dev_vn = get_device_name(device)
                act_vn = "bật" if action == "turn_on" else "tắt"
                question = clean_voice_text(f"Dạ anh muốn {act_vn} {dev_vn} ở phòng nào thế anh? Hiện có {room_list_str} nè~")
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
            # Tìm phòng trong câu trả lời theo danh sách phòng hợp lệ
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
            # Phân biệt đèn ngủ vs đèn trần, quạt bàn vs quạt trần, 1 vs 2
            if any(w in norm_text for w in ("ngủ", "đầu giường", "bàn", "den ngu")):
                cmd["device"] = "den_ngu" if "den" in cmd.get("device", "") or cmd.get("device") == "light" else "quat_ban"
            elif any(w in norm_text for w in ("trần", "chiếu sáng", "chính", "chùm", "tuýp", "led")):
                cmd["device"] = "den_tran" if "den" in cmd.get("device", "") or cmd.get("device") == "light" else "quat_tran"
            elif any(w in norm_text for w in ("1", "một", "mot", "ch1", "relay 1", "công tắc 1")):
                cmd["device"] = "ch1"
            elif any(w in norm_text for w in ("2", "hai", "ch2", "relay 2", "công tắc 2")):
                cmd["device"] = "ch2"
            else:
                cmd["device"] = None

        return intent
