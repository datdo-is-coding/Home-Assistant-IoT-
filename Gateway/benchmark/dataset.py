"""
Bộ dữ liệu đánh giá độ chính xác toàn diện cho Voice NLU (Qwen2.5-3B & Gemini).
Bao gồm 64 ca kiểm thử trên 7 chiều đánh giá thực tế.
"""

TEST_CASES = [
    # ── 1. Direct Explicit Commands (Lệnh trực tiếp chuẩn hóa) ──
    {
        "id": "DIR_01",
        "category": "Direct",
        "input": "bật đèn phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lệnh bật đèn phòng ngủ cơ bản"
    },
    {
        "id": "DIR_02",
        "category": "Direct",
        "input": "tắt đèn phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lệnh tắt đèn phòng ngủ cơ bản"
    },
    {
        "id": "DIR_03",
        "category": "Direct",
        "input": "bật quạt phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Lệnh bật quạt phòng ngủ"
    },
    {
        "id": "DIR_04",
        "category": "Direct",
        "input": "tắt quạt phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Lệnh tắt quạt phòng ngủ"
    },
    {
        "id": "DIR_05",
        "category": "Direct",
        "input": "mở đèn phòng khách",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,  # Chưa có node phòng khách
        "description": "Đồng nghĩa mở = bật tại phòng khách"
    },
    {
        "id": "DIR_06",
        "category": "Direct",
        "input": "tắt đèn phòng khách",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Tắt đèn phòng khách"
    },
    {
        "id": "DIR_07",
        "category": "Direct",
        "input": "khởi động quạt phòng khách",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Khởi động = bật"
    },
    {
        "id": "DIR_08",
        "category": "Direct",
        "input": "ngắt điện quạt phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Ngắt điện = tắt"
    },
    {
        "id": "DIR_09",
        "category": "Direct",
        "input": "bật đèn phòng bếp",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_bep",
        "should_resolve": False,
        "description": "Bật đèn phòng bếp"
    },
    {
        "id": "DIR_10",
        "category": "Direct",
        "input": "tắt quạt phòng bếp",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_bep",
        "should_resolve": False,
        "description": "Tắt quạt phòng bếp"
    },

    # ── 2. Natural Language / Implicit Intent (Ngữ cảnh ẩn) ──
    {
        "id": "NAT_01",
        "category": "Implicit",
        "input": "phòng ngủ tối quá không thấy gì cả",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Tối quá -> bật đèn"
    },
    {
        "id": "NAT_02",
        "category": "Implicit",
        "input": "phòng ngủ nóng quá ngột ngạt quá",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Nóng quá -> bật quạt"
    },
    {
        "id": "NAT_03",
        "category": "Implicit",
        "input": "chuẩn bị đi ngủ rồi tắt điện đi",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Đi ngủ -> tắt điện phòng ngủ"
    },
    {
        "id": "NAT_04",
        "category": "Implicit",
        "input": "phòng ngủ sáng quá chói mắt",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Sáng quá -> tắt đèn"
    },
    {
        "id": "NAT_05",
        "category": "Implicit",
        "input": "phòng khách lạnh quá rồi gió to quá",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Lạnh quá -> tắt quạt"
    },
    {
        "id": "NAT_06",
        "category": "Implicit",
        "input": "trong bếp tối om chẳng thấy đường nấu ăn",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_bep",
        "should_resolve": False,
        "description": "Bếp tối -> bật đèn bếp"
    },
    {
        "id": "NAT_07",
        "category": "Implicit",
        "input": "ra ngoài phòng khách ngồi tối thế",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Phòng khách tối -> bật đèn"
    },
    {
        "id": "NAT_08",
        "category": "Implicit",
        "input": "nóng nực thế này bật tí gió phòng ngủ đi",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Bật tí gió -> bật quạt"
    },
    {
        "id": "NAT_09",
        "category": "Implicit",
        "input": "vào phòng ngủ bật sáng lên",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Bật sáng -> bật đèn"
    },
    {
        "id": "NAT_10",
        "category": "Implicit",
        "input": "trời sáng rõ rồi tắt điện phòng ngủ đi",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Trời sáng -> tắt đèn"
    },

    # ── 3. Vietnamese Dialects & Colloquialisms (Khẩu ngữ địa phương) ──
    {
        "id": "DIAL_01",
        "category": "Dialect",
        "input": "bật giùm cái quạt ở trong buồng ngủ với",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Buồng ngủ = phòng ngủ, bật giùm = bật"
    },
    {
        "id": "DIAL_02",
        "category": "Dialect",
        "input": "cho xin tí ánh sáng phòng ngủ nào",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Tí ánh sáng = đèn"
    },
    {
        "id": "DIAL_03",
        "category": "Dialect",
        "input": "dẹp cái quạt phòng ngủ đi giùm cái",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Dẹp đi = tắt"
    },
    {
        "id": "DIAL_04",
        "category": "Dialect",
        "input": "thắp cái đèn gian khách lên xem nào",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Thắp đèn = bật đèn, gian khách = phòng khách"
    },
    {
        "id": "DIAL_05",
        "category": "Dialect",
        "input": "hạ cái quạt ở phòng ngủ xuống",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Hạ quạt = tắt quạt"
    },
    {
        "id": "DIAL_06",
        "category": "Dialect",
        "input": "bật cho anh cái bóng điện phòng khách",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Bóng điện = đèn"
    },
    {
        "id": "DIAL_07",
        "category": "Dialect",
        "input": "tắt cái quạt máy trong buồng ngủ đi em",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Quạt máy = quạt, buồng ngủ = phòng ngủ"
    },
    {
        "id": "DIAL_08",
        "category": "Dialect",
        "input": "mở quạt mát ở phòng khách giùm đi",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Quạt mát = quạt"
    },
    {
        "id": "DIAL_09",
        "category": "Dialect",
        "input": "tắt ngúm cái đèn ngủ đi",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Tắt ngúm = tắt, đèn ngủ -> phòng ngủ"
    },
    {
        "id": "DIAL_10",
        "category": "Dialect",
        "input": "bật quạt trần phòng ngủ lên",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Quạt trần = quạt"
    },

    # ── 4. Negation & Adversarial Traps (Phủ định & Câu bẫy ngữ nghĩa) ──
    {
        "id": "NEG_01",
        "category": "Negation",
        "input": "đừng tắt đèn phòng ngủ nhé",
        "expected_action": None,  # Không được sinh turn_off
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Phủ định: đừng tắt đèn -> không hành động"
    },
    {
        "id": "NEG_02",
        "category": "Negation",
        "input": "không bật quạt phòng ngủ đâu",
        "expected_action": None,  # Không được sinh turn_on
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Phủ định: không bật quạt"
    },
    {
        "id": "NEG_03",
        "category": "Negation",
        "input": "tôi bảo bật đèn chứ không bảo bật quạt phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Phân biệt bật đèn vs không bật quạt"
    },
    {
        "id": "NEG_04",
        "category": "Negation",
        "input": "đang lạnh đừng có mở quạt phòng ngủ",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Cấm mở quạt -> không hành động"
    },
    {
        "id": "NEG_05",
        "category": "Negation",
        "input": "tắt đèn nhưng đừng tắt quạt phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lệnh kép: tắt đèn, giữ quạt"
    },
    {
        "id": "NEG_06",
        "category": "Negation",
        "input": "bật đèn đừng bật quạt ở phòng khách",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Lệnh kép: bật đèn, cấm bật quạt"
    },
    {
        "id": "NEG_07",
        "category": "Negation",
        "input": "hôm nay không cần bật đèn phòng ngủ đâu",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Không cần bật -> không hành động"
    },
    {
        "id": "NEG_08",
        "category": "Negation",
        "input": "ai bảo bật quạt đấy tắt quạt phòng ngủ ngay",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Trích xuất ý định cốt lõi: tắt quạt phòng ngủ"
    },

    # ── 5. Ambiguity & Missing Slots (Lệnh thiếu thông tin) ──
    {
        "id": "AMB_01",
        "category": "Ambiguity",
        "input": "bật đèn",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": None,  # Không nêu phòng
        "should_resolve": True,     # Vì hiện chỉ có 1 phòng có đèn -> auto-resolve
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Thiếu vị trí phòng: bật đèn"
    },
    {
        "id": "AMB_02",
        "category": "Ambiguity",
        "input": "tắt quạt",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": None,
        "should_resolve": True,     # Auto-resolve sang phòng ngủ duy nhất
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Thiếu vị trí phòng: tắt quạt"
    },
    {
        "id": "AMB_03",
        "category": "Ambiguity",
        "input": "phòng ngủ",
        "expected_action": None,
        "expected_device": None,
        "expected_location": "phong_ngu",
        "should_resolve": False,
        "description": "Chỉ nói tên phòng không có hành động"
    },
    {
        "id": "AMB_04",
        "category": "Ambiguity",
        "input": "bật lên",
        "expected_action": "turn_on",
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Chỉ nói bật lên, thiếu cả phòng lẫn thiết bị"
    },
    {
        "id": "AMB_05",
        "category": "Ambiguity",
        "input": "tắt đi",
        "expected_action": "turn_off",
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Chỉ nói tắt đi, thiếu thiết bị"
    },
    {
        "id": "AMB_06",
        "category": "Ambiguity",
        "input": "bật đèn ở đây",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": None,
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Từ ngữ chỉ định 'ở đây' coi như chưa rõ phòng"
    },
    {
        "id": "AMB_07",
        "category": "Ambiguity",
        "input": "tắt thiết bị trong phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": None,
        "expected_location": "phong_ngu",
        "should_resolve": False,
        "description": "Thiếu loại thiết bị cụ thể"
    },
    {
        "id": "AMB_08",
        "category": "Ambiguity",
        "input": "mở quạt lên nào",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": None,
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Mở quạt không rõ phòng"
    },

    # ── 6. Out-of-Domain & Hallucination Resistance (Bẫy ảo giác & OOD) ──
    {
        "id": "OOD_01",
        "category": "Hallucination",
        "input": "thời tiết hôm nay ở Hà Nội thế nào",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Câu hỏi thời tiết, không phải lệnh IoT"
    },
    {
        "id": "OOD_02",
        "category": "Hallucination",
        "input": "1 cộng 1 bằng mấy",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Câu hỏi toán học, không được sinh lệnh bật/tắt"
    },
    {
        "id": "OOD_03",
        "category": "Hallucination",
        "input": "bật máy bay trực thăng lên",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Thiết bị bịa đặt, GBNF phải chặn"
    },
    {
        "id": "OOD_04",
        "category": "Hallucination",
        "input": "kể cho tôi nghe một câu chuyện",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Yêu cầu kể chuyện, không phải lệnh IoT"
    },
    {
        "id": "OOD_05",
        "category": "Hallucination",
        "input": "mở cửa sổ phòng ngủ ra",
        "expected_action": None,
        "expected_device": None,
        "expected_location": "phong_ngu",
        "should_resolve": False,
        "description": "Cửa sổ không có trong registry thiết bị"
    },
    {
        "id": "OOD_06",
        "category": "Hallucination",
        "input": "bật lò vi sóng ở gara ô tô",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Cả phòng gara lẫn lò vi sóng đều không tồn tại"
    },
    {
        "id": "OOD_07",
        "category": "Hallucination",
        "input": "tắt tivi ở bể bơi",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Bể bơi không có trong inventory"
    },
    {
        "id": "OOD_08",
        "category": "Hallucination",
        "input": "cho tôi hỏi bây giờ là mấy giờ",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Hỏi giờ, không được kích hoạt relay"
    },
    {
        "id": "OOD_09",
        "category": "Hallucination",
        "input": "bật máy tính phòng làm việc",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Phòng làm việc không có trong danh sách phòng"
    },
    {
        "id": "OOD_10",
        "category": "Hallucination",
        "input": "mở nhạc sơn tùng mtp",
        "expected_action": None,
        "expected_device": None,
        "expected_location": None,
        "should_resolve": False,
        "description": "Lệnh nghe nhạc, không điều khiển relay"
    },

    # ── 7. ASR Noise & Phonetic Errors (Nhiễu nhận dạng giọng nói) ──
    {
        "id": "NOISE_01",
        "category": "ASR_Noise",
        "input": "bặt đèn phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lỗi nhận dạng: bặt -> bật"
    },
    {
        "id": "NOISE_02",
        "category": "ASR_Noise",
        "input": "bật đền phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lỗi nhận dạng: đền -> đèn"
    },
    {
        "id": "NOISE_03",
        "category": "ASR_Noise",
        "input": "tắc quạt phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Lỗi nhận dạng: tắc -> tắt"
    },
    {
        "id": "NOISE_04",
        "category": "ASR_Noise",
        "input": "bật quặt phòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Lỗi nhận dạng: quặt -> quạt"
    },
    {
        "id": "NOISE_05",
        "category": "ASR_Noise",
        "input": "bật đèn fòng ngủ",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lỗi telex: fòng -> phòng"
    },
    {
        "id": "NOISE_06",
        "category": "ASR_Noise",
        "input": "tắt quạt fòng ngũ",
        "expected_action": "turn_off",
        "expected_device": "quat",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch2",
        "description": "Lỗi dấu hỏi/ngã: ngũ -> ngủ"
    },
    {
        "id": "NOISE_07",
        "category": "ASR_Noise",
        "input": "mở đèn phòng khác",
        "expected_action": "turn_on",
        "expected_device": "den",
        "expected_location": "phong_khach",
        "should_resolve": False,
        "description": "Lỗi âm cuối: khác -> khách"
    },
    {
        "id": "NOISE_08",
        "category": "ASR_Noise",
        "input": "tắt đèng phòng ngủ",
        "expected_action": "turn_off",
        "expected_device": "den",
        "expected_location": "phong_ngu",
        "should_resolve": True,
        "expected_node": "esp32s3_master",
        "expected_channel": "ch1",
        "description": "Lỗi phương ngữ Nam Bộ: đèng -> đèn"
    },
]
