"""
Display Names & Natural Vietnamese Voice Normalization Module
=============================================================
Maps internal identifiers (e.g. phong_ngu, phong_khach, den_ngu)
to natural, accented Vietnamese names for UI and speech synthesis.
Bảo đảm loa AI luôn đọc đúng tên tiếng Việt có dấu, không bao giờ đọc id_room snake_case.
"""

import re
from typing import Optional, Any

ROOM_DISPLAY_NAMES = {
    "phong_khach": "phòng khách",
    "phong_ngu": "phòng ngủ",
    "phong_ngu_master": "phòng ngủ Master",
    "phong_ngu_con": "phòng ngủ con",
    "phong_bep": "phòng bếp",
    "phong_lam_viec": "phòng làm việc",
    "san_vuon": "sân vườn",
    "ban_cong": "ban công",
    "gara": "gara",
    "phong_tam": "phòng tắm",
    "phong_ve_sinh": "phòng vệ sinh",
    "hanh_lang": "hành lang",
    "san_thuong": "sân thượng",
    "phong_tho": "phòng thờ",
    "unknown": "phòng"
}

DEVICE_DISPLAY_NAMES = {
    "light": "đèn",
    "den": "đèn",
    "den_ngu": "đèn ngủ",
    "den_tran": "đèn trần",
    "den_chum": "đèn chùm",
    "den_bep": "đèn bếp",
    "den_ban": "đèn bàn",
    "den_hoc": "đèn học",
    "den_san": "đèn sân",
    "den_cong": "đèn cổng",
    "den_hat": "đèn hắt",
    "den_guong": "đèn gương",
    "den_tam": "đèn phòng tắm",
    "fan": "quạt",
    "quat": "quạt",
    "quat_tran": "quạt trần",
    "quat_cay": "quạt cây",
    "quat_treo": "quạt treo tường",
    "quat_thong_gio": "quạt thông gió",
    "quat_hut": "quạt hút ẩm",
    "may_hut_mui": "máy hút mùi",
    "hut_mui": "máy hút mùi",
    "air_conditioner": "điều hòa",
    "dieu_hoa": "điều hòa",
    "may_lanh": "máy lạnh",
    "pump": "máy bơm",
    "bom": "máy bơm",
    "bom_tuoi_cay": "bơm tưới cây",
    "curtain": "rèm cửa",
    "rem": "rèm cửa",
    "rem_cua": "rèm cửa",
    "cua_cuon": "cửa cuốn",
    "gian_phoi": "giàn phơi",
    "switch": "công tắc",
    "binh_nong_lanh": "bình nóng lạnh",
    "tivi": "tivi",
    "noi_com": "nồi cơm điện",
    "noi_com_dien": "nồi cơm điện",
    "lo_vi_song": "lò vi sóng",
    "vi_song": "lò vi sóng",
    "may_tinh": "máy tính",
    "may_in": "máy in",
    "sac_xe_dien": "sạc xe điện",
    "bom_hoi": "máy bơm hơi",
    "he_thong_chong_trom": "hệ thống chống trộm",
    "cam_bien": "cảm biến"
}


def get_room_name(room_id: Optional[str]) -> str:
    """Chuyển room_id snake_case (phong_ngu) thành tên tiếng Việt tự nhiên (phòng ngủ)."""
    if not room_id:
        return ""
    r = str(room_id).lower().strip()
    return ROOM_DISPLAY_NAMES.get(r, r.replace("_", " "))


def get_device_name(device_id_or_info: Any) -> str:
    """Chuyển device_id/ch_info thành tên tiếng Việt tự nhiên (quạt trần, đèn ngủ)."""
    if not device_id_or_info:
        return "thiết bị"
    if isinstance(device_id_or_info, dict):
        if device_id_or_info.get("name"):
            return device_id_or_info["name"]
        if device_id_or_info.get("description"):
            desc = device_id_or_info["description"]
            if "-" in desc:
                return desc.split("-")[-1].strip()
            return desc
        dev_type = device_id_or_info.get("device_type", "")
        return DEVICE_DISPLAY_NAMES.get(dev_type, dev_type.replace("_", " "))

    s = str(device_id_or_info).strip()
    if "-" in s:
        parts = s.split("-")
        s = parts[-1]
    return DEVICE_DISPLAY_NAMES.get(s, s.replace("_", " "))


def clean_voice_text(text: str) -> str:
    """
    Rà soát và thay thế toàn bộ mã ID tiếng Anh/snake_case còn sót trong văn bản
    thành tên tiếng Việt tự nhiên có dấu trước khi đưa vào bộ tổng hợp giọng nói TTS.
    """
    if not text:
        return ""

    # 1. Thay thế fullname kiểu 'phong_ngu_master-pnm_node01-den_ngu'
    def _sub_fullname(match):
        part = match.group(1).split("-")[-1]
        return DEVICE_DISPLAY_NAMES.get(part, part.replace("_", " "))
    text = re.sub(r"\b([a-z0-9_]+-[a-z0-9_]+-[a-z0-9_]+)\b", _sub_fullname, text)

    # 2. Thay thế room_id dài trước, ngắn sau để tránh match tiền tố
    for r_id in sorted(ROOM_DISPLAY_NAMES.keys(), key=lambda x: -len(x)):
        if r_id in ("unknown",): continue
        r_name = ROOM_DISPLAY_NAMES[r_id]
        text = re.sub(rf"\b{r_id}\b", r_name, text)

    # 3. Thay thế device_id
    for d_id in sorted(DEVICE_DISPLAY_NAMES.keys(), key=lambda x: -len(x)):
        if len(d_id) > 2 and d_id in text:
            d_name = DEVICE_DISPLAY_NAMES[d_id]
            text = re.sub(rf"\b{d_id}\b", d_name, text)

    return text
