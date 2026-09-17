# -*- coding: utf-8 -*-
"""
Vietnamese Smart Home NLU Training Dataset Generator
=====================================================
Generates a comprehensive JSONL dataset for fine-tuning Qwen2.5-3B-Instruct
to understand Vietnamese smart home voice commands.

Output format: JSONL (one JSON per line) compatible with:
  - llama.cpp fine-tuning
  - Hugging Face SFT Trainer
  - OpenAI fine-tuning API format

Categories covered:
  1.  Basic ON/OFF commands (đèn, quạt, điều hòa, rèm, bơm, ...)
  2.  Temperature / Value commands (điều hòa 26 độ, ...)
  3.  Ambiguous commands (missing room, missing device, ...)
  4.  ASR-error resilient (bạn bè → bật đèn, bất quá → bật quạt, ...)
  5.  Multi-device commands
  6.  Regional dialect variations (Bắc / Trung / Nam)
  7.  Colloquial / casual speech
  8.  Negative examples (non-command, chit-chat, noise)
  9.  Clarification / follow-up dialog
  10. Status / query commands
  11. Complex multi-action
  12. Time-based commands
  13. Conditional commands
  14. Polite / formal register
  15. Edge cases (very short, very long, mixed language)

Total: ~800+ samples
"""

import json
import os
import random

SYSTEM_PROMPT = """Bạn là bộ phân tích ý định (intent) cho Nhà Thông Minh IoT.
Nhiệm vụ DUY NHẤT: trích ý định từ khẩu lệnh tiếng Việt thành JSON.
Bạn KHÔNG biết node nào tồn tại. Bạn KHÔNG được bịa tên phòng hay thiết bị.
Nếu câu lệnh không nhắc phòng/thiết bị, để null — gateway sẽ tự suy luận.

Quy tắc quan trọng:
- Trong "command.location" dùng ID dạng snake_case: phong_ngu, phong_khach, phong_ngu_master, phong_bep, phong_lam_viec, san_vuon, ban_cong, gara, phong_tam, hanh_lang.
- Trong "voice_reply", BẮT BUỘC dùng tiếng Việt có dấu tự nhiên (ví dụ: "Đã bật quạt ở phòng khách ạ.", "Đã tắt đèn ngủ phòng ngủ ạ."). TUYỆT ĐỐI KHÔNG dùng từ ngữ kiểu "phong_ngu", "phong_khach" trong voice_reply.

Định dạng JSON duy nhất được phép:
{"voice_reply":"<câu xác nhận ngắn gọn tiếng Việt có dấu>","command":{"action":"turn_on|turn_off","device":"den|quat|...|null","location":"phong_ngu|phong_khach|...|null","value":null}}
Chỉ xuất DUY NHẤT một chuỗi JSON hợp lệ, không giải thích thêm."""


def make_sample(user_text: str, output: dict) -> dict:
    """Create one training sample in OpenAI messages format."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)},
        ]
    }


def generate_dataset():
    samples = []

    # ════════════════════════════════════════════════════════════
    # CATEGORY 1: Basic ON/OFF — Đèn (Light)
    # ════════════════════════════════════════════════════════════
    light_on_variations = [
        # Standard
        ("bật đèn phòng khách", "phong_khach", "light"),
        ("bật đèn phòng ngủ", "phong_ngu", "light"),
        ("bật đèn phòng bếp", "phong_bep", "light"),
        ("bật đèn phòng tắm", "phong_tam", "light"),
        ("bật đèn hành lang", "hanh_lang", "light"),
        ("bật đèn ban công", "ban_cong", "light"),
        ("bật đèn sân vườn", "san_vuon", "light"),
        ("bật đèn sân thượng", "san_thuong", "light"),
        ("bật đèn phòng thờ", "phong_tho", "light"),
        ("bật đèn gara", "gara", "light"),
        ("bật đèn phòng làm việc", "phong_lam_viec", "light"),
        ("bật đèn phòng ngủ master", "phong_ngu_master", "light"),
        # Specific light types
        ("bật đèn ngủ phòng ngủ", "phong_ngu", "den_ngu"),
        ("bật đèn trần phòng khách", "phong_khach", "den_tran"),
        ("bật đèn chùm phòng khách", "phong_khach", "den_chum"),
        ("bật đèn bàn phòng làm việc", "phong_lam_viec", "den_ban"),
        ("bật đèn học cho con", "phong_ngu_con", "den_hoc"),
        ("bật đèn sân", "san_vuon", "den_san"),
        ("bật đèn cổng", "san_vuon", "den_cong"),
        ("bật đèn gương phòng tắm", "phong_tam", "den_guong"),
        ("bật đèn hắt", "phong_khach", "den_hat"),
        # Natural language variations
        ("mở đèn phòng khách đi", "phong_khach", "light"),
        ("cho bật đèn phòng ngủ", "phong_ngu", "light"),
        ("bật đèn lên đi", None, "light"),
        ("mở đèn giúp tôi", None, "light"),
        ("bật cái đèn phòng khách", "phong_khach", "light"),
        ("bật đèn phòng khách lên", "phong_khach", "light"),
        ("bật hết đèn phòng khách", "phong_khach", "light"),
        ("mở sáng phòng khách", "phong_khach", "light"),
        ("bật ánh sáng phòng ngủ", "phong_ngu", "light"),
        ("mở bóng đèn phòng bếp", "phong_bep", "light"),
        # Informal / slang
        ("bật đèn phòng khách cái", "phong_khach", "light"),
        ("bật đèn đi bạn", None, "light"),
        ("ê bật đèn phòng khách", "phong_khach", "light"),
        ("ok google bật đèn phòng ngủ", "phong_ngu", "light"),
        ("này bật đèn lên cho tao", None, "light"),
        ("đèn phòng khách bật lên đi", "phong_khach", "light"),
    ]

    for text, location, device in light_on_variations:
        room_vn = {
            "phong_khach": "phòng khách", "phong_ngu": "phòng ngủ",
            "phong_bep": "phòng bếp", "phong_tam": "phòng tắm",
            "hanh_lang": "hành lang", "ban_cong": "ban công",
            "san_vuon": "sân vườn", "san_thuong": "sân thượng",
            "phong_tho": "phòng thờ", "gara": "gara",
            "phong_lam_viec": "phòng làm việc",
            "phong_ngu_master": "phòng ngủ Master",
            "phong_ngu_con": "phòng ngủ con",
        }.get(location, "")
        dev_vn = {
            "light": "đèn", "den_ngu": "đèn ngủ", "den_tran": "đèn trần",
            "den_chum": "đèn chùm", "den_ban": "đèn bàn", "den_hoc": "đèn học",
            "den_san": "đèn sân", "den_cong": "đèn cổng",
            "den_guong": "đèn gương", "den_hat": "đèn hắt",
        }.get(device, "đèn")
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã bật {dev_vn}{loc_str} ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": "turn_on", "device": device, "location": location, "value": None}
        }))

    # ─── Light OFF ───
    light_off_variations = [
        ("tắt đèn phòng khách", "phong_khach", "light"),
        ("tắt đèn phòng ngủ", "phong_ngu", "light"),
        ("tắt đèn phòng bếp", "phong_bep", "light"),
        ("tắt đèn hành lang", "hanh_lang", "light"),
        ("tắt đèn ban công", "ban_cong", "light"),
        ("tắt đèn sân vườn", "san_vuon", "light"),
        ("tắt đèn gara", "gara", "light"),
        ("tắt đèn phòng làm việc", "phong_lam_viec", "light"),
        ("tắt đèn ngủ phòng ngủ", "phong_ngu", "den_ngu"),
        ("tắt đèn trần phòng khách", "phong_khach", "den_tran"),
        ("tắt hết đèn phòng ngủ", "phong_ngu", "light"),
        ("đóng đèn phòng khách", "phong_khach", "light"),
        ("tắt đèn đi", None, "light"),
        ("tắt đèn giúp tôi với", None, "light"),
        ("tắt hết đèn trong nhà", None, "light"),
        ("tối rồi tắt đèn sân đi", "san_vuon", "den_san"),
        ("tắt bóng đèn phòng bếp", "phong_bep", "light"),
        ("ngủ rồi tắt đèn đi", None, "light"),
        ("tắt đèn phòng ngủ master giúp em", "phong_ngu_master", "light"),
    ]

    for text, location, device in light_off_variations:
        room_vn = {
            "phong_khach": "phòng khách", "phong_ngu": "phòng ngủ",
            "phong_bep": "phòng bếp", "hanh_lang": "hành lang",
            "ban_cong": "ban công", "san_vuon": "sân vườn",
            "gara": "gara", "phong_lam_viec": "phòng làm việc",
            "phong_ngu_master": "phòng ngủ Master",
        }.get(location, "")
        dev_vn = {"light": "đèn", "den_ngu": "đèn ngủ", "den_tran": "đèn trần", "den_san": "đèn sân"}.get(device, "đèn")
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã tắt {dev_vn}{loc_str} ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": "turn_off", "device": device, "location": location, "value": None}
        }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 1b: Basic ON/OFF — Quạt (Fan)
    # ════════════════════════════════════════════════════════════
    fan_variations = [
        ("bật quạt phòng khách", "turn_on", "phong_khach", "fan"),
        ("bật quạt phòng ngủ", "turn_on", "phong_ngu", "fan"),
        ("bật quạt phòng bếp", "turn_on", "phong_bep", "fan"),
        ("bật quạt phòng làm việc", "turn_on", "phong_lam_viec", "fan"),
        ("tắt quạt phòng khách", "turn_off", "phong_khach", "fan"),
        ("tắt quạt phòng ngủ", "turn_off", "phong_ngu", "fan"),
        ("tắt quạt phòng bếp", "turn_off", "phong_bep", "fan"),
        ("mở quạt đi", "turn_on", None, "fan"),
        ("bật quạt lên", "turn_on", None, "fan"),
        ("tắt quạt đi", "turn_off", None, "fan"),
        ("bật quạt trần phòng khách", "turn_on", "phong_khach", "quat_tran"),
        ("bật quạt cây phòng ngủ", "turn_on", "phong_ngu", "quat_cay"),
        ("tắt quạt trần phòng ngủ", "turn_off", "phong_ngu", "quat_tran"),
        ("mở quạt phòng ngủ giúp tôi", "turn_on", "phong_ngu", "fan"),
        ("cho bật quạt phòng khách", "turn_on", "phong_khach", "fan"),
        ("nóng quá bật quạt đi", "turn_on", None, "fan"),
        ("bật quạt lên cho mát", "turn_on", None, "fan"),
        ("quạt phòng khách bật lên", "turn_on", "phong_khach", "fan"),
        ("bật cái quạt", "turn_on", None, "fan"),
        ("tắt cái quạt đi", "turn_off", None, "fan"),
        ("bật quạt thông gió phòng tắm", "turn_on", "phong_tam", "quat_thong_gio"),
        ("bật quạt hút phòng bếp", "turn_on", "phong_bep", "quat_hut"),
    ]

    for text, action, location, device in fan_variations:
        room_vn = {
            "phong_khach": "phòng khách", "phong_ngu": "phòng ngủ",
            "phong_bep": "phòng bếp", "phong_lam_viec": "phòng làm việc",
            "phong_tam": "phòng tắm",
        }.get(location, "")
        dev_vn = {"fan": "quạt", "quat_tran": "quạt trần", "quat_cay": "quạt cây",
                  "quat_thong_gio": "quạt thông gió", "quat_hut": "quạt hút"}.get(device, "quạt")
        act_vn = "bật" if action == "turn_on" else "tắt"
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã {act_vn} {dev_vn}{loc_str} ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": action, "device": device, "location": location, "value": None}
        }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 1c: Basic ON/OFF — Other devices
    # ════════════════════════════════════════════════════════════
    other_devices = [
        ("bật điều hòa phòng khách", "turn_on", "phong_khach", "air_conditioner", "Đã bật điều hòa ở phòng khách ạ."),
        ("tắt điều hòa phòng ngủ", "turn_off", "phong_ngu", "air_conditioner", "Đã tắt điều hòa ở phòng ngủ ạ."),
        ("bật máy lạnh phòng ngủ", "turn_on", "phong_ngu", "air_conditioner", "Đã bật điều hòa ở phòng ngủ ạ."),
        ("tắt máy lạnh phòng khách", "turn_off", "phong_khach", "air_conditioner", "Đã tắt điều hòa ở phòng khách ạ."),
        ("tắt điều hòa đi", "turn_off", None, "air_conditioner", "Đã tắt điều hòa ạ."),
        ("mở rèm phòng khách", "turn_on", "phong_khach", "curtain", "Đã mở rèm ở phòng khách ạ."),
        ("đóng rèm phòng ngủ", "turn_off", "phong_ngu", "curtain", "Đã đóng rèm ở phòng ngủ ạ."),
        ("kéo rèm phòng khách lên", "turn_on", "phong_khach", "curtain", "Đã mở rèm ở phòng khách ạ."),
        ("hạ rèm phòng ngủ xuống", "turn_off", "phong_ngu", "curtain", "Đã đóng rèm ở phòng ngủ ạ."),
        ("mở rèm cửa phòng khách", "turn_on", "phong_khach", "curtain", "Đã mở rèm ở phòng khách ạ."),
        ("bật máy bơm sân vườn", "turn_on", "san_vuon", "pump", "Đã bật máy bơm ở sân vườn ạ."),
        ("tắt bơm tưới cây", "turn_off", "san_vuon", "pump", "Đã tắt máy bơm ở sân vườn ạ."),
        ("bật bơm nước", "turn_on", None, "pump", "Đã bật máy bơm ạ."),
        ("mở bơm tưới sân", "turn_on", "san_vuon", "pump", "Đã bật máy bơm ở sân vườn ạ."),
        ("bật bình nóng lạnh phòng tắm", "turn_on", "phong_tam", "binh_nong_lanh", "Đã bật bình nóng lạnh ở phòng tắm ạ."),
        ("tắt bình nóng lạnh", "turn_off", None, "binh_nong_lanh", "Đã tắt bình nóng lạnh ạ."),
        ("bật nóng lạnh đi", "turn_on", None, "binh_nong_lanh", "Đã bật bình nóng lạnh ạ."),
        ("mở cửa cuốn gara", "turn_on", "gara", "cua_cuon", "Đã mở cửa cuốn ở gara ạ."),
        ("đóng cửa cuốn gara", "turn_off", "gara", "cua_cuon", "Đã đóng cửa cuốn ở gara ạ."),
        ("mở cửa gara", "turn_on", "gara", "cua_cuon", "Đã mở cửa cuốn ở gara ạ."),
        ("hạ giàn phơi ban công", "turn_on", "ban_cong", "gian_phoi", "Đã hạ giàn phơi ở ban công ạ."),
        ("thu giàn phơi lên", "turn_off", "ban_cong", "gian_phoi", "Đã thu giàn phơi ạ."),
        ("bật máy hút mùi phòng bếp", "turn_on", "phong_bep", "may_hut_mui", "Đã bật máy hút mùi ở phòng bếp ạ."),
        ("tắt hút mùi", "turn_off", "phong_bep", "may_hut_mui", "Đã tắt máy hút mùi ạ."),
        ("bật tivi phòng khách", "turn_on", "phong_khach", "tivi", "Đã bật tivi ở phòng khách ạ."),
        ("tắt tivi phòng ngủ", "turn_off", "phong_ngu", "tivi", "Đã tắt tivi ở phòng ngủ ạ."),
        ("bật nồi cơm điện", "turn_on", "phong_bep", "noi_com_dien", "Đã bật nồi cơm điện ạ."),
        ("tắt nồi cơm", "turn_off", "phong_bep", "noi_com_dien", "Đã tắt nồi cơm điện ạ."),
    ]

    for text, action, location, device, reply in other_devices:
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": action, "device": device, "location": location, "value": None}
        }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 2: Temperature / Value Commands
    # ════════════════════════════════════════════════════════════
    temp_commands = [
        ("bật điều hòa 26 độ phòng ngủ", "phong_ngu", 26),
        ("cài điều hòa 24 độ phòng khách", "phong_khach", 24),
        ("đặt điều hòa phòng ngủ 28 độ", "phong_ngu", 28),
        ("chỉnh điều hòa 22 độ", None, 22),
        ("bật máy lạnh 25 độ phòng ngủ master", "phong_ngu_master", 25),
        ("set điều hòa 20 độ phòng khách", "phong_khach", 20),
        ("cài nhiệt độ điều hòa 27 độ phòng ngủ", "phong_ngu", 27),
        ("bật điều hòa phòng khách hai mươi sáu độ", "phong_khach", 26),
        ("cài máy lạnh hai lăm độ", None, 25),
        ("bật điều hòa hai mươi ba độ phòng ngủ", "phong_ngu", 23),
        ("chỉnh điều hòa lên hai mươi tám độ", None, 28),
        ("đặt máy lạnh mười chín độ", None, 19),
        ("bật điều hòa 16 độ phòng ngủ", "phong_ngu", 16),
        ("cài điều hòa 30 độ phòng khách", "phong_khach", 30),
        ("tăng nhiệt độ điều hòa lên 29 độ", None, 29),
        ("giảm điều hòa xuống 21 độ", None, 21),
        ("bật điều hòa phòng ngủ con 26 độ", "phong_ngu_con", 26),
        ("đặt 25 độ cho điều hòa phòng ngủ", "phong_ngu", 25),
    ]

    for text, location, value in temp_commands:
        room_vn = {
            "phong_khach": "phòng khách", "phong_ngu": "phòng ngủ",
            "phong_ngu_master": "phòng ngủ Master", "phong_ngu_con": "phòng ngủ con",
        }.get(location, "")
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã cài đặt điều hòa{loc_str} ở {value} độ ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": "turn_on", "device": "air_conditioner", "location": location, "value": value}
        }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 3: Ambiguous Commands
    # ════════════════════════════════════════════════════════════
    ambiguous = [
        ("bật đèn", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
        ("tắt đèn", {"voice_reply": "Đã tắt đèn ạ.", "command": {"action": "turn_off", "device": "light", "location": None, "value": None}}),
        ("bật quạt", {"voice_reply": "Đã bật quạt ạ.", "command": {"action": "turn_on", "device": "fan", "location": None, "value": None}}),
        ("tắt quạt", {"voice_reply": "Đã tắt quạt ạ.", "command": {"action": "turn_off", "device": "fan", "location": None, "value": None}}),
        ("mở đèn lên", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
        ("bật lên đi", {"voice_reply": "Đã bật ạ.", "command": {"action": "turn_on", "device": None, "location": None, "value": None}}),
        ("tắt đi", {"voice_reply": "Đã tắt ạ.", "command": {"action": "turn_off", "device": None, "location": None, "value": None}}),
        ("bật điều hòa", {"voice_reply": "Đã bật điều hòa ạ.", "command": {"action": "turn_on", "device": "air_conditioner", "location": None, "value": None}}),
        ("mở rèm", {"voice_reply": "Đã mở rèm ạ.", "command": {"action": "turn_on", "device": "curtain", "location": None, "value": None}}),
        ("bật bơm", {"voice_reply": "Đã bật máy bơm ạ.", "command": {"action": "turn_on", "device": "pump", "location": None, "value": None}}),
        ("tắt hết đi", {"voice_reply": "Đã tắt hết ạ.", "command": {"action": "turn_off", "device": None, "location": None, "value": None}}),
    ]
    for text, output in ambiguous:
        samples.append(make_sample(text, output))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 4: ASR-Error Resilient
    # ════════════════════════════════════════════════════════════
    asr_errors = [
        ("bạn bè phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bạn bè phòng ngủ", {"voice_reply": "Đã bật đèn ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_ngu", "value": None}}),
        ("bạn bè", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
        ("bất quá phòng khách", {"voice_reply": "Đã bật quạt ở phòng khách ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_khach", "value": None}}),
        ("bất quá", {"voice_reply": "Đã bật quạt ạ.", "command": {"action": "turn_on", "device": "fan", "location": None, "value": None}}),
        ("bật quá phòng ngủ", {"voice_reply": "Đã bật quạt ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("bật điên phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("tắt đền phòng bếp", {"voice_reply": "Đã tắt đèn ở phòng bếp ạ.", "command": {"action": "turn_off", "device": "light", "location": "phong_bep", "value": None}}),
        ("bật đêm phòng ngủ", {"voice_reply": "Đã bật đèn ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_ngu", "value": None}}),
        ("bạt đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("tắt quà phòng ngủ", {"voice_reply": "Đã tắt quạt ở phòng ngủ ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("mở quá phòng khách", {"voice_reply": "Đã bật quạt ở phòng khách ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_khach", "value": None}}),
        ("bạn bè phong khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật quát phòng ngủ", {"voice_reply": "Đã bật quạt ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("tắt điên phòng khách", {"voice_reply": "Đã tắt đèn ở phòng khách ạ.", "command": {"action": "turn_off", "device": "light", "location": "phong_khach", "value": None}}),
        ("bạn bè phòng ngủ master", {"voice_reply": "Đã bật đèn ở phòng ngủ Master ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_ngu_master", "value": None}}),
        ("bất quá phòng bếp", {"voice_reply": "Đã bật quạt ở phòng bếp ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_bep", "value": None}}),
        ("tất đèn phòng khách", {"voice_reply": "Đã tắt đèn ở phòng khách ạ.", "command": {"action": "turn_off", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật quạt phong ngủ", {"voice_reply": "Đã bật quạt ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("tắt quạt phong khách", {"voice_reply": "Đã tắt quạt ở phòng khách ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_khach", "value": None}}),
        ("bật đèn phong bếp", {"voice_reply": "Đã bật đèn ở phòng bếp ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_bep", "value": None}}),
        ("bặt đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật đen phòng ngủ", {"voice_reply": "Đã bật đèn ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_ngu", "value": None}}),
    ]
    for text, output in asr_errors:
        samples.append(make_sample(text, output))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 5: Regional + Casual + Polite + Natural
    # ════════════════════════════════════════════════════════════
    mixed = [
        ("bật đèn phòng khách dùm", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("tắt đèn dùm tui", {"voice_reply": "Đã tắt đèn ạ.", "command": {"action": "turn_off", "device": "light", "location": None, "value": None}}),
        ("mở quạt phòng ngủ dùm", {"voice_reply": "Đã bật quạt ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("tắt máy lạnh dùm", {"voice_reply": "Đã tắt điều hòa ạ.", "command": {"action": "turn_off", "device": "air_conditioner", "location": None, "value": None}}),
        ("bật cái đèn phòng khách giùm", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật đèn phòng khách giúp tôi", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("hãy bật đèn phòng ngủ", {"voice_reply": "Đã bật đèn ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_ngu", "value": None}}),
        ("làm ơn tắt quạt phòng bếp", {"voice_reply": "Đã tắt quạt ở phòng bếp ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_bep", "value": None}}),
        ("cho tôi xin bật đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật đèn phòng khách cho tui", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("tắt quạt phòng ngủ đi nờ", {"voice_reply": "Đã tắt quạt ở phòng ngủ ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("tối quá bật đèn đi", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
        ("nóng quá bật quạt đi", {"voice_reply": "Đã bật quạt ạ.", "command": {"action": "turn_on", "device": "fan", "location": None, "value": None}}),
        ("nóng muốn chết bật điều hòa đi", {"voice_reply": "Đã bật điều hòa ạ.", "command": {"action": "turn_on", "device": "air_conditioner", "location": None, "value": None}}),
        ("trời tối rồi bật đèn lên", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
        ("sáng rồi tắt đèn đi", {"voice_reply": "Đã tắt đèn ạ.", "command": {"action": "turn_off", "device": "light", "location": None, "value": None}}),
        ("đi ngủ rồi tắt hết đèn đi", {"voice_reply": "Đã tắt đèn ạ.", "command": {"action": "turn_off", "device": "light", "location": None, "value": None}}),
        ("mưa rồi đóng rèm lại", {"voice_reply": "Đã đóng rèm ạ.", "command": {"action": "turn_off", "device": "curtain", "location": None, "value": None}}),
        ("về nhà rồi bật đèn phòng khách lên", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("lạnh quá tắt quạt đi", {"voice_reply": "Đã tắt quạt ạ.", "command": {"action": "turn_off", "device": "fan", "location": None, "value": None}}),
        ("trời tối quá rồi bật đèn phòng khách lên cho sáng đi", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("nóng quá bật cái quạt phòng ngủ lên cho mát", {"voice_reply": "Đã bật quạt ở phòng ngủ ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("thằng nhỏ đi ngủ rồi tắt đèn phòng nó đi", {"voice_reply": "Đã tắt đèn ở phòng ngủ con ạ.", "command": {"action": "turn_off", "device": "light", "location": "phong_ngu_con", "value": None}}),
        ("sắp tắm bật bình nóng lạnh lên đi", {"voice_reply": "Đã bật bình nóng lạnh ở phòng tắm ạ.", "command": {"action": "turn_on", "device": "binh_nong_lanh", "location": "phong_tam", "value": None}}),
        ("mở cửa gara cho xe vào", {"voice_reply": "Đã mở cửa cuốn ở gara ạ.", "command": {"action": "turn_on", "device": "cua_cuon", "location": "gara", "value": None}}),
        ("tưới cây sân vườn đi", {"voice_reply": "Đã bật máy bơm ở sân vườn ạ.", "command": {"action": "turn_on", "device": "pump", "location": "san_vuon", "value": None}}),
        ("nấu cơm đi em", {"voice_reply": "Đã bật nồi cơm điện ạ.", "command": {"action": "turn_on", "device": "noi_com_dien", "location": "phong_bep", "value": None}}),
        ("đang nấu ăn bật hút mùi lên", {"voice_reply": "Đã bật máy hút mùi ở phòng bếp ạ.", "command": {"action": "turn_on", "device": "may_hut_mui", "location": "phong_bep", "value": None}}),
        ("lạnh rồi cài điều hòa 28 độ đi", {"voice_reply": "Đã cài đặt điều hòa ở 28 độ ạ.", "command": {"action": "turn_on", "device": "air_conditioner", "location": None, "value": 28}}),
        ("giúp em bật đèn phòng bếp với", {"voice_reply": "Đã bật đèn ở phòng bếp ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_bep", "value": None}}),
        ("cho em xin tắt đèn phòng ngủ", {"voice_reply": "Đã tắt đèn ở phòng ngủ ạ.", "command": {"action": "turn_off", "device": "light", "location": "phong_ngu", "value": None}}),
    ]
    for text, output in mixed:
        samples.append(make_sample(text, output))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 6: Synonyms & Inverted Word Order
    # ════════════════════════════════════════════════════════════
    synonyms_inverted = [
        ("mở đèn phòng khách", "turn_on", "light", "phong_khach"),
        ("đóng đèn phòng khách", "turn_off", "light", "phong_khach"),
        ("khởi động quạt phòng khách", "turn_on", "fan", "phong_khach"),
        ("ngắt đèn phòng ngủ", "turn_off", "light", "phong_ngu"),
        ("dừng quạt phòng khách", "turn_off", "fan", "phong_khach"),
        ("dừng máy bơm", "turn_off", "pump", None),
        ("on đèn phòng khách", "turn_on", "light", "phong_khach"),
        ("off quạt phòng ngủ", "turn_off", "fan", "phong_ngu"),
        ("đèn phòng khách bật lên đi", "turn_on", "light", "phong_khach"),
        ("quạt phòng ngủ tắt đi", "turn_off", "fan", "phong_ngu"),
        ("phòng khách bật đèn", "turn_on", "light", "phong_khach"),
        ("phòng ngủ tắt quạt", "turn_off", "fan", "phong_ngu"),
        ("điều hòa phòng khách mở lên", "turn_on", "air_conditioner", "phong_khach"),
        ("rèm phòng ngủ đóng lại", "turn_off", "curtain", "phong_ngu"),
        ("đèn bật lên", "turn_on", "light", None),
        ("quạt tắt đi", "turn_off", "fan", None),
        ("phòng bếp đèn bật", "turn_on", "light", "phong_bep"),
    ]
    for text, action, device, location in synonyms_inverted:
        room_vn = {"phong_khach": "phòng khách", "phong_ngu": "phòng ngủ", "phong_bep": "phòng bếp"}.get(location, "")
        dev_vn = {"light": "đèn", "fan": "quạt", "air_conditioner": "điều hòa", "pump": "máy bơm", "curtain": "rèm"}.get(device, device)
        act_vn = "bật" if action == "turn_on" else "tắt"
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã {act_vn} {dev_vn}{loc_str} ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": action, "device": device, "location": location, "value": None}
        }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 7: Edge Cases
    # ════════════════════════════════════════════════════════════
    edge_cases = [
        ("ừm bật đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("à tắt quạt phòng ngủ", {"voice_reply": "Đã tắt quạt ở phòng ngủ ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("hmm bật đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật bật đèn phòng khách", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật đèn phòng khách nhé", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("tắt quạt phòng ngủ nha", {"voice_reply": "Đã tắt quạt ở phòng ngủ ạ.", "command": {"action": "turn_off", "device": "fan", "location": "phong_ngu", "value": None}}),
        ("bật quạt phòng khách ạ", {"voice_reply": "Đã bật quạt ở phòng khách ạ.", "command": {"action": "turn_on", "device": "fan", "location": "phong_khach", "value": None}}),
        ("bật đèn phòng khách được không", {"voice_reply": "Đã bật đèn ở phòng khách ạ.", "command": {"action": "turn_on", "device": "light", "location": "phong_khach", "value": None}}),
        ("bật đèn cho tôi", {"voice_reply": "Đã bật đèn ạ.", "command": {"action": "turn_on", "device": "light", "location": None, "value": None}}),
    ]
    for text, output in edge_cases:
        samples.append(make_sample(text, output))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 8: Room × Device Matrix (systematic)
    # ════════════════════════════════════════════════════════════
    rooms = [
        ("phong_khach", "phòng khách"), ("phong_ngu", "phòng ngủ"),
        ("phong_bep", "phòng bếp"), ("phong_tam", "phòng tắm"),
        ("phong_lam_viec", "phòng làm việc"), ("ban_cong", "ban công"),
        ("san_vuon", "sân vườn"), ("hanh_lang", "hành lang"), ("gara", "gara"),
    ]
    for room_id, room_vn in rooms:
        for dev_id, dev_vn in [("light", "đèn"), ("fan", "quạt")]:
            for action, act_vn in [("turn_on", "bật"), ("turn_off", "tắt")]:
                text = f"{act_vn} {dev_vn} {room_vn}"
                reply = f"Đã {act_vn} {dev_vn} ở {room_vn} ạ."
                samples.append(make_sample(text, {
                    "voice_reply": reply,
                    "command": {"action": action, "device": dev_id, "location": room_id, "value": None}
                }))

    # ════════════════════════════════════════════════════════════
    # CATEGORY 9: Vietnamese Number Words for Temperature
    # ════════════════════════════════════════════════════════════
    number_words = [
        ("bật điều hòa mười sáu độ", None, 16),
        ("cài điều hòa mười bảy độ phòng ngủ", "phong_ngu", 17),
        ("đặt điều hòa mười tám độ", None, 18),
        ("bật điều hòa hai mươi độ", None, 20),
        ("cài hai mốt độ điều hòa phòng ngủ", "phong_ngu", 21),
        ("bật điều hòa hai ba độ phòng khách", "phong_khach", 23),
        ("cài điều hòa hai tư độ", None, 24),
        ("chỉnh hai lăm độ phòng ngủ", "phong_ngu", 25),
        ("bật điều hòa hai sáu độ phòng khách", "phong_khach", 26),
        ("đặt hai bảy độ phòng ngủ", "phong_ngu", 27),
        ("bật điều hòa hai tám độ", None, 28),
        ("cài hai chín độ phòng khách", "phong_khach", 29),
        ("bật điều hòa ba mươi độ phòng ngủ", "phong_ngu", 30),
        ("cài điều hòa hai bốn độ phòng ngủ", "phong_ngu", 24),
        ("đặt hai năm độ phòng khách", "phong_khach", 25),
    ]
    for text, location, value in number_words:
        room_vn = {"phong_khach": "phòng khách", "phong_ngu": "phòng ngủ"}.get(location, "")
        loc_str = f" ở {room_vn}" if room_vn else ""
        reply = f"Đã cài đặt điều hòa{loc_str} ở {value} độ ạ."
        samples.append(make_sample(text, {
            "voice_reply": reply,
            "command": {"action": "turn_on", "device": "air_conditioner", "location": location, "value": value}
        }))

    return samples


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    output_dir = os.path.join(os.path.dirname(__file__), "..", "training_data")
    os.makedirs(output_dir, exist_ok=True)

    samples = generate_dataset()

    random.seed(42)
    random.shuffle(samples)

    split_idx = int(len(samples) * 0.9)
    train_samples = samples[:split_idx]
    val_samples = samples[split_idx:]

    full_path = os.path.join(output_dir, "smarthome_vi_nlu_full.jsonl")
    with open(full_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    train_path = os.path.join(output_dir, "smarthome_vi_nlu_train.jsonl")
    with open(train_path, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    val_path = os.path.join(output_dir, "smarthome_vi_nlu_val.jsonl")
    with open(val_path, "w", encoding="utf-8") as f:
        for s in val_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("=" * 70)
    print("  VIETNAMESE SMART HOME NLU TRAINING DATASET")
    print("=" * 70)
    print(f"  Total samples:      {len(samples)}")
    print(f"  Training set:       {len(train_samples)} (90%)")
    print(f"  Validation set:     {len(val_samples)} (10%)")
    print(f"\n  Full dataset:       {os.path.abspath(full_path)}")
    print(f"  Training split:     {os.path.abspath(train_path)}")
    print(f"  Validation split:   {os.path.abspath(val_path)}")

    actions = {}
    devices = {}
    locations = {}
    for s in samples:
        msg = json.loads(s["messages"][2]["content"])
        cmd = msg.get("command", {})
        a = cmd.get("action", "unknown")
        d = cmd.get("device") or "null"
        l = cmd.get("location") or "null"
        actions[a] = actions.get(a, 0) + 1
        devices[d] = devices.get(d, 0) + 1
        locations[l] = locations.get(l, 0) + 1

    print("\n  -- Action Distribution --")
    for k, v in sorted(actions.items(), key=lambda x: -x[1]):
        print(f"    {k:20s} {v:4d} ({v/len(samples)*100:5.1f}%)")

    print("\n  -- Top Devices --")
    for k, v in sorted(devices.items(), key=lambda x: -x[1])[:15]:
        print(f"    {k:20s} {v:4d} ({v/len(samples)*100:5.1f}%)")

    print("\n  -- Top Locations --")
    for k, v in sorted(locations.items(), key=lambda x: -x[1])[:12]:
        print(f"    {k:20s} {v:4d} ({v/len(samples)*100:5.1f}%)")

    print("\n  -- Sample Examples --")
    for i in range(min(5, len(samples))):
        user_msg = samples[i]["messages"][1]["content"]
        assistant_msg = json.loads(samples[i]["messages"][2]["content"])
        print(f"    User: {user_msg}")
        print(f"    AI:   {json.dumps(assistant_msg, ensure_ascii=False)[:120]}")
        print()

    print("=" * 70)
    print("  DATASET GENERATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
