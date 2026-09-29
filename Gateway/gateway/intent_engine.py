"""
Intent Engine v3 — Hệ thống phân tích ý định khẩu lệnh tiếng Việt (Production-Ready for Raspberry Pi 4)
===================================================================================================

Triết lý kiến trúc chuẩn:
    ASR ≠ Intent ≠ Device ≠ Node ≠ Execution ≠ Response

Pipeline:
    ASR text
       ↓
    ASR Normalizer (âm vị, độ tin cậy, không phá vỡ ngữ cảnh)
       ↓
    Negation Detector (chặn câu phủ định, không biến thành turn_on)
       ↓
    Fast Path / Rule Engine (phân cấp HIGH / MEDIUM / AMBIGUOUS)
       ↓ (nếu HIGH ≥ 0.95 → bypass LLM)
    Context Resolver (Multi-turn Context với TTL, kế thừa an toàn)
       ↓ (nếu cần LLM / phức tạp)
    LLM NLU Engine (Gemini Flash Cloud / Local Qwen 2.5 với prompt siêu gọn & GBNF)
       ↓
    Intent Normalization
       ↓
    Strict Validator (đối chiếu Registry: Exact → Alias → Unique Fuzzy → Reject)
       ↓
    IntentResult (Dữ liệu cấu trúc + tương thích ngược dictionary)

Nguyên tắc bất biến:
- Intent Engine KHÔNG điều khiển GPIO, KHÔNG quyết định node_id/channel
- Intent Engine KHÔNG hallucinate thiết bị/phòng ngoài Registry
- Intent Engine KHÔNG tự nhận định command thành công trước khi Verifier/MQTT trả kết quả
- Response hoàn tất ("Dạ em đã bật...") chỉ do Verifier/Response Generator sinh sau khi ESP32 thực thi
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

try:
    import httpx
except ImportError:
    httpx = None

import config
from display_names import get_room_name, get_device_name, clean_voice_text

logger = logging.getLogger("intent")


# ── BẢNG TỪ ĐIỂN VÀ ALIASES CHUẨN HOÁ ────────────────────────────────────────

def slug(s: Optional[str]) -> str:
    """Chuyển đổi chuỗi tiếng Việt có dấu thành slug không dấu dạng snake_case."""
    if s is None:
        return ""
    s = str(s).lower().strip()
    tbl = str.maketrans(
        "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
    )
    s = s.translate(tbl)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


# Danh mục thiết bị chuẩn (Canonical Device Mapping)
DEVICE_ALIASES: Dict[str, List[str]] = {
    "light": [
        "đèn", "bóng đèn", "đèn điện", "ánh sáng", "light", "den", "bong_den",
        "đèn trần", "den_tran", "đèn chùm", "đèn tuýp", "đèn led", "đèn bàn", "đèn học"
    ],
    "den_ngu": [
        "đèn ngủ", "den_ngu", "đèn đầu giường", "den ngu"
    ],
    "fan": [
        "quạt", "quạt điện", "quạt máy", "quat", "fan",
        "quạt trần", "quạt cây", "quạt đứng", "quạt bàn", "quạt treo", "quạt thông gió"
    ],
    "air_conditioner": [
        "điều hòa", "máy lạnh", "máy điều hòa", "dieu_hoa", "may_lanh", "ac",
        "air conditioner", "air_conditioner", "máy lạng", "máy lặng"
    ],
    "pump": [
        "máy bơm", "bơm", "máy tưới", "tưới cây", "tưới", "pump", "may_bom"
    ],
    "curtain": [
        "rèm", "rèm cửa", "màn", "màn cửa", "curtain", "rem"
    ],
    "tivi": [
        "tivi", "ti vi", "tv", "television"
    ],
    "binh_nong_lanh": [
        "bình nóng lạnh", "bình nước nóng", "nước nóng", "binh_nong_lanh"
    ],
    "may_hut_mui": [
        "hút mùi", "máy hút mùi", "may_hut_mui", "quạt hút mùi"
    ],
    "socket": [
        "ổ cắm", "o_cam", "ổ điện", "phích cắm", "socket", "ổ", "o cam", "o dien",
        "ổ cắm điện", "phích cắm điện"
    ],
    "ch1": [
        "relay 1", "relay một", "công tắc 1", "công tắc một", "kênh 1", "kênh một", "nút 1"
    ],
    "ch2": [
        "relay 2", "relay hai", "công tắc 2", "công tắc hai", "kênh 2", "kênh hai", "nút 2"
    ],
    "all": [
        "tất cả", "toàn bộ", "hết", "toàn bộ thiết bị", "tất cả thiết bị"
    ]
}

# Danh mục phòng chuẩn (Canonical Room Mapping)
ROOM_ALIASES: Dict[str, List[str]] = {
    "phong_ngu": [
        "phòng ngủ", "phong ngu", "ngủ", "bedroom", "p_ngu"
    ],
    "phong_ngu_master": [
        "phòng ngủ master", "phòng master", "ngủ master", "master bedroom"
    ],
    "phong_ngu_con": [
        "phòng ngủ con", "ngủ con", "phòng con"
    ],
    "phong_khach": [
        "phòng khách", "phong khach", "khách", "living room", "livingroom", "p_khach"
    ],
    "phong_bep": [
        "phòng bếp", "phong bep", "bếp", "nhà bếp", "kitchen", "p_bep"
    ],
    "phong_tam": [
        "nhà vệ sinh", "vệ sinh", "toilet", "wc", "phòng tắm", "bathroom", "tắm", "phong_ve_sinh"
    ],
    "ban_cong": [
        "ban công", "balcony"
    ],
    "san_thuong": [
        "sân thượng", "rooftop"
    ],
    "san_vuon": [
        "sân vườn", "ngoài sân", "vườn", "garden", "san vuon"
    ],
    "gara": [
        "gara", "nhà xe", "ga ra", "garage"
    ],
    "phong_tho": [
        "phòng thờ"
    ],
    "phong_lam_viec": [
        "phòng làm việc", "làm việc", "phòng học"
    ],
    "hanh_lang": [
        "hành lang", "cầu thang"
    ]
}

# Bảng số từ tiếng Việt biểu diễn nhiệt độ điều hòa (16 - 32 độ C)
VIETNAMESE_NUMBERS: Dict[str, int] = {
    "mười sáu": 16, "mười bảy": 17, "mười tám": 18, "mười chín": 19,
    "hai mươi": 20, "hai mốt": 21, "hai mươi mốt": 21,
    "hai hai": 22, "hai mươi hai": 22,
    "hai ba": 23, "hai mươi ba": 23,
    "hai tư": 24, "hai bốn": 24, "hai mươi tư": 24, "hai mươi bốn": 24,
    "hai lăm": 25, "hai năm": 25, "hai mươi lăm": 25, "hai mươi năm": 25,
    "hai sáu": 26, "hai mươi sáu": 26,
    "hai bảy": 27, "hai mươi bảy": 27,
    "hai tám": 28, "hai mươi tám": 28,
    "hai chín": 29, "hai mươi chín": 29,
    "ba mươi": 30, "ba chục": 30,
    "ba mốt": 31, "ba mươi mốt": 31,
    "ba hai": 32, "ba mươi hai": 32
}


# ── DATA STRUCTURES & INTENT RESULT ──────────────────────────────────────────

@dataclass
class Target:
    """Mục tiêu điều khiển của Intent (Device Type, Specific Name, Room)."""
    device_type: Optional[str] = None
    device_name: Optional[str] = None
    room: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "device_type": self.device_type,
            "device_name": self.device_name,
            "room": self.room,
        }


@dataclass
class NormalizedText:
    """Kết quả sau khi chuẩn hóa âm vị và phát hiện lỗi ASR."""
    text: str
    original_text: str
    corrections: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 1.0


class IntentResult(dict):
    """
    Kết quả ý định trích xuất chuẩn hoá v3.
    Đồng thời kế thừa dict để tương thích ngược hoàn toàn 100% với:
    - main.py: intent["command"]["action"], intent["command"]["device"], intent["voice_reply"]
    - evaluator.py: raw_intent["command"]
    """
    def __init__(
        self,
        intent: str,
        target: Optional[Target] = None,
        value: Optional[Any] = None,
        unit: Optional[str] = None,
        confidence: float = 1.0,
        source: str = "fast_path",
        needs_clarification: bool = False,
        clarification_reason: Optional[str] = None,
        negated: bool = False,
        raw_text: str = "",
        normalized_text: str = "",
        voice_reply: Optional[str] = None,
        commands: Optional[List["IntentResult"]] = None,
        scene: Optional[str] = None,
        **extra
    ):
        super().__init__()
        self.intent = intent
        self.target = target or Target()
        self.value = value
        self.unit = unit
        self.confidence = float(confidence)
        self.source = source
        self.needs_clarification = needs_clarification
        self.clarification_reason = clarification_reason
        self.negated = negated
        self.raw_text = raw_text
        self.normalized_text = normalized_text
        self.voice_reply = voice_reply
        self.commands = commands or []
        self.scene = scene

        self._sync_dict()

    def _sync_dict(self):
        """Cập nhật các key từ điển để bảo đảm tương thích ngược với main.py."""
        action = self.intent
        if self.intent in ("set_temperature", "set_value"):
            action = "set_value"
        elif self.intent in ("query_state", "query_sensor", "scene"):
            action = self.intent
        elif self.intent not in ("turn_on", "turn_off", "unknown"):
            action = "unknown"

        self["intent"] = self.intent
        self["target"] = self.target.to_dict()
        self["value"] = self.value
        self["unit"] = self.unit
        self["confidence"] = self.confidence
        self["source"] = self.source
        self["needs_clarification"] = self.needs_clarification
        self["clarification_reason"] = self.clarification_reason
        self["negated"] = self.negated
        self["raw_text"] = self.raw_text
        self["normalized_text"] = self.normalized_text
        self["scene"] = self.scene
        self["commands"] = [
            cmd.to_dict() if isinstance(cmd, IntentResult) else cmd for cmd in self.commands
        ]
        self["voice_reply"] = self.voice_reply

        # Legacy command object format mong đợi bởi main.py
        self["command"] = {
            "action": action,
            "device": self.target.device_type,
            "location": self.target.room,
            "value": self.value
        }

    def to_dict(self) -> Dict[str, Any]:
        self._sync_dict()
        return dict(self)

    def __repr__(self) -> str:
        return (
            f"IntentResult(intent='{self.intent}', target={self.target.to_dict()}, "
            f"val={self.value}, conf={self.confidence:.2f}, src='{self.source}', "
            f"clarify={self.needs_clarification}, negated={self.negated})"
        )


# ── MODULE 1: ASR NORMALIZER ─────────────────────────────────────────────────

class ASRNormalizer:
    """
    Module chuẩn hóa âm vị và khắc phục lỗi ASR tiếng Việt chuyên sâu.
    Tách biệt hoàn toàn khỏi logic trích xuất ý định.
    Ghi nhận confidence và danh sách corrections.
    """
    def __init__(self):
        self.phonetic_rules: List[Tuple[str, str, float, str]] = [
            # Lỗi đặc thù nghiêm trọng của ASR: "bạn bè" -> "bật đèn"
            (r"\bbạn bè phòng\b", "bật đèn phòng", 0.96, "bạn bè phòng → bật đèn phòng"),
            (r"\bbạn bè\b", "bật đèn", 0.95, "bạn bè → bật đèn"),
            (r"\bbạn về\b", "bật đèn", 0.94, "bạn về → bật đèn"),
            (r"\bbạn đề\b", "bật đèn", 0.94, "bạn đề → bật đèn"),

            # Họ âm vị quạt: "bất quá / bật quà / bật quát" -> "bật quạt"
            (r"\bbất quá\b", "bật quạt", 0.95, "bất quá → bật quạt"),
            (r"\bbật quà\b", "bật quạt", 0.95, "bật quà → bật quạt"),
            (r"\bbật quát\b", "bật quạt", 0.95, "bật quát → bật quạt"),
            (r"\bbắt quạt\b", "bật quạt", 0.95, "bắt quạt → bật quạt"),
            (r"\bbật quét\b", "bật quạt", 0.94, "bật quét → bật quạt"),
            (r"\bbất quạt\b", "bật quạt", 0.95, "bất quạt → bật quạt"),
            (r"\bmở quá\b", "mở quạt", 0.95, "mở quá → mở quạt"),
            (r"\bmở quà\b", "mở quạt", 0.95, "mở quà → mở quạt"),
            (r"\btắt quá\b", "tắt quạt", 0.95, "tắt quá → tắt quạt"),
            (r"\btắt quà\b", "tắt quạt", 0.95, "tắt quà → tắt quạt"),

            # Họ âm vị đèn
            (r"\bbật điên\b", "bật đèn", 0.95, "bật điên → bật đèn"),
            (r"\btắt điên\b", "tắt đèn", 0.95, "tắt điên → tắt đèn"),
            (r"\bbật đền\b", "bật đèn", 0.95, "bật đền → bật đèn"),
            (r"\btắt đền\b", "tắt đèn", 0.95, "tắt đền → tắt đèn"),
            (r"\bbật đêm\b", "bật đèn", 0.95, "bật đêm → bật đèn"),
            (r"\btắt đêm\b", "tắt đèn", 0.95, "tắt đêm → tắt đèn"),
            (r"\bbạt đèn\b", "bật đèn", 0.96, "bạt đèn → bật đèn"),
            (r"\bbạt đền\b", "bật đèn", 0.95, "bạt đền → bật đèn"),
            (r"\btác đèn\b", "tắt đèn", 0.95, "tác đèn → tắt đèn"),

            # Họ điều hòa / máy lạnh
            (r"\bmáy lặng\b", "máy lạnh", 0.97, "máy lặng → máy lạnh"),
            (r"\bmáy lạng\b", "máy lạnh", 0.97, "máy lạng → máy lạnh"),
            (r"\bđiều hoà\b", "điều hòa", 0.99, "điều hoà → điều hòa"),
            (r"\bmáy điều hòa\b", "điều hòa", 0.99, "máy điều hòa → điều hòa"),

            # Phòng
            (r"\bphòng ngue\b", "phòng ngủ", 0.96, "phòng ngue → phòng ngủ"),
            (r"\bphòng nghủ\b", "phòng ngủ", 0.96, "phòng nghủ → phòng ngủ"),
            (r"\bphòng khash\b", "phòng khách", 0.96, "phòng khash → phòng khách"),
            (r"\bphòng khác\b", "phòng khách", 0.92, "phòng khác → phòng khách"),
            (r"\bphòng bép\b", "phòng bếp", 0.96, "phòng bép → phòng bếp"),
            (r"\bnhà bép\b", "nhà bếp", 0.96, "nhà bép → nhà bếp"),

            # Đồng nghĩa thiết bị
            (r"\bquạt điện\b", "quạt", 0.98, "quạt điện → quạt"),
            (r"\bquạt máy\b", "quạt", 0.98, "quạt máy → quạt"),
            (r"\bbóng đèn\b", "đèn", 0.98, "bóng đèn → đèn"),

            # Lỗi nhầm lẫn âm học đặc thù từ Zipformer ASR
            (r"\bban đêm không ngủ\b", "bật quạt phòng ngủ", 0.98, "ban đêm không ngủ → bật quạt phòng ngủ"),
            (r"\bđêm qua không ngủ\b", "bật quạt phòng ngủ", 0.98, "đêm qua không ngủ → bật quạt phòng ngủ"),
            (r"\bkhông ngủ\b", "phòng ngủ", 0.96, "không ngủ → phòng ngủ"),
            (r"\bkhong ngu\b", "phòng ngủ", 0.96, "khong ngu → phòng ngủ"),
            (r"\bhòng ngủ\b", "phòng ngủ", 0.96, "hòng ngủ → phòng ngủ"),
            (r"\bphòng ngũ\b", "phòng ngủ", 0.96, "phòng ngũ → phòng ngủ"),
            (r"\bđêm qua\b", "bật quạt", 0.95, "đêm qua → bật quạt"),
            (r"\bban đêm\b", "bật đèn", 0.95, "ban đêm → bật đèn"),
            (r"\bbật qua\b", "bật quạt", 0.95, "bật qua → bật quạt"),
            (r"\bbắt quạt\b", "bật quạt", 0.95, "bắt quạt → bật quạt"),
            (r"\btắt qua\b", "tắt quạt", 0.95, "tắt qua → tắt quạt"),
            (r"\btác quạt\b", "tắt quạt", 0.95, "tác quạt → tắt quạt"),
        ]

        self.noise_fillers = [
            r"\b(ừm|ơ|à|ờ|hmm|uh|ơi|nhé|nha|giúp|hộ|cho tui|cho mình|cho tôi|làm ơn)\b"
        ]

    def normalize(self, raw_text: str) -> NormalizedText:
        if not raw_text or not raw_text.strip():
            return NormalizedText(text="", original_text="", confidence=1.0)

        cleaned = raw_text.lower().strip()
        corrections: List[Dict[str, str]] = []
        accumulated_confidence = 1.0

        for pattern, replacement, conf, desc in self.phonetic_rules:
            if re.search(pattern, cleaned):
                cleaned = re.sub(pattern, replacement, cleaned)
                corrections.append({"rule": desc, "confidence": conf})
                accumulated_confidence = min(accumulated_confidence, conf)

        for filler in self.noise_fillers:
            cleaned = re.sub(filler, " ", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return NormalizedText(
            text=cleaned,
            original_text=raw_text,
            corrections=corrections,
            confidence=accumulated_confidence
        )


# ── MODULE 2: NEGATION DETECTOR ──────────────────────────────────────────────

class NegationDetector:
    """
    Nhận diện câu phủ định để TUYỆT ĐỐI KHÔNG chuyển thành hành động kích hoạt.
    Ví dụ: 'đừng bật đèn', 'không bật quạt', 'tôi không muốn bật điều hòa'.
    """
    NEGATION_TRIGGERS = [
        r"\bđừng\b",
        r"\bkhông\b",
        r"\bchớ\b",
        r"\bkhông được\b",
        r"\bkhông cần\b",
        r"\bchẳng cần\b",
        r"\btôi không muốn\b",
        r"\bchưa muốn\b",
        r"\bđừng có\b",
    ]

    @classmethod
    def is_negated(cls, text: str) -> bool:
        t = text.lower()
        for pattern in cls.NEGATION_TRIGGERS:
            if re.search(pattern + r"\s+(?:bật|mở|khởi động|kích hoạt|cài|đặt|chỉnh|tăng|hạ|cho|làm)", t):
                return True
            if re.search(r"nhưng\s+" + pattern, t):
                return True
            if re.search(r"mà\s+" + pattern, t):
                return True
        return False


# ── MODULE 3: MULTI-TURN CONTEXT MANAGER ─────────────────────────────────────

class IntentContextManager:
    """
    Quản lý ngữ cảnh đối thoại đa lượt (Multi-Turn Context) với TTL.
    Kế thừa thông tin một cách an toàn và ngăn chặn suy diễn vô hạn.
    """
    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl_seconds = ttl_seconds
        self.last_device_type: Optional[str] = None
        self.last_room: Optional[str] = None
        self.last_intent: Optional[str] = None
        self.last_value: Optional[Any] = None
        self.updated_at: float = 0.0

    @property
    def is_valid(self) -> bool:
        return (time.time() - self.updated_at) <= self.ttl_seconds and self.updated_at > 0

    def update(self, result: IntentResult):
        """Cập nhật ngữ cảnh khi có một lệnh rõ ràng."""
        if result.intent in ("turn_on", "turn_off", "set_temperature", "set_value"):
            if result.target.device_type:
                self.last_device_type = result.target.device_type
            if result.target.room:
                self.last_room = result.target.room
            self.last_intent = result.intent
            if result.value is not None:
                self.last_value = result.value
            self.updated_at = time.time()
            logger.debug(
                f"🧠 [Context Updated] device={self.last_device_type}, "
                f"room={self.last_room}, intent={self.last_intent}, val={self.last_value}"
            )

    def resolve(self, raw_intent: IntentResult, raw_user_text: str) -> IntentResult:
        """
        Bổ sung các slot thiếu thông qua ngữ cảnh hợp lệ gần nhất.
        """
        if not self.is_valid:
            return raw_intent

        text = raw_user_text.lower()
        has_pronoun = bool(re.search(r"\b(nó|cái này|cái kia|cái đó|thiết bị đó|ở đó)\b", text))

        # Trường hợp 1: Đại từ thay thế ("bật nó lên", "tắt nó đi")
        if has_pronoun:
            if not raw_intent.target.device_type and self.last_device_type:
                raw_intent.target.device_type = self.last_device_type
            if not raw_intent.target.room and self.last_room:
                raw_intent.target.room = self.last_room
            raw_intent.source = "context"
            raw_intent.confidence = 0.92
            raw_intent.needs_clarification = False
            raw_intent.clarification_reason = None
            raw_intent._sync_dict()
            return raw_intent

        # Trường hợp 2: Lệnh cài đặt nhiệt độ thiếu thiết bị/phòng ("Cài 25 độ", "Tăng lên 26 độ")
        if raw_intent.intent in ("set_temperature", "set_value"):
            if self.last_device_type in ("air_conditioner", "dieu_hoa", "may_lanh"):
                if not raw_intent.target.device_type:
                    raw_intent.target.device_type = "air_conditioner"
                if not raw_intent.target.room and self.last_room:
                    raw_intent.target.room = self.last_room
                raw_intent.source = "context"
                raw_intent.confidence = 0.95
                raw_intent.needs_clarification = False
                raw_intent.clarification_reason = None
                raw_intent._sync_dict()
                return raw_intent

        # Trường hợp 3: Nguyên tắc an toàn CHỐNG suy diễn vô hạn:
        # Nếu người dùng đổi sang thiết bị khác (ví dụ trước đó 'Bật đèn phòng ngủ', giờ 'Bật quạt')
        # Tuyệt đối KHÔNG tự ý gán quạt vào phòng ngủ nếu người dùng không nói rõ!
        if raw_intent.target.device_type and raw_intent.target.device_type != self.last_device_type:
            pass

        return raw_intent

    def clear(self):
        self.last_device_type = None
        self.last_room = None
        self.last_intent = None
        self.last_value = None
        self.updated_at = 0.0


# ── MODULE 4: STRICT VALIDATOR ───────────────────────────────────────────────

class StrictValidator:
    """
    Xác thực nghiêm ngặt đối chiếu với Registry thực tế.
    Loại bỏ hoàn toàn các heuristic kiểm tra độ dài len(s) > 20.
    Thứ tự: Exact Match -> Alias Match -> Unique Fuzzy Match -> Reject.
    """
    def __init__(self, registry=None):
        self.registry = registry

    def set_registry(self, registry):
        self.registry = registry

    def resolve_room(self, room_input: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Trả về (canonical_room, is_ambiguous).
        Nếu không tìm thấy hoặc hallucinated -> (None, False).
        """
        if not room_input:
            return None, False

        r_slug = slug(room_input)
        allowed_rooms = set(self.registry.allowed_rooms()) if self.registry else set(ROOM_ALIASES.keys())

        # 1. Exact match
        if r_slug in allowed_rooms:
            return r_slug, False

        # 2. Alias match
        for canon, aliases in ROOM_ALIASES.items():
            if canon in allowed_rooms or not self.registry:
                for a in aliases:
                    if r_slug == slug(a) or slug(a) == r_slug:
                        return canon, False

        # 3. Unique Fuzzy match (khoảng cách sai biệt 1 ký tự hoặc tiền tố duy nhất)
        candidates = []
        for ar in allowed_rooms:
            if ar.startswith(r_slug) or r_slug.startswith(ar):
                candidates.append(ar)
        if len(candidates) == 1:
            return candidates[0], False
        elif len(candidates) > 1:
            return None, True

        # 4. Hallucination / Không tồn tại
        return None, False

    def resolve_device(self, device_input: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Trả về (canonical_device, is_ambiguous).
        Nếu không tìm thấy hoặc hallucinated -> (None, False).
        """
        if not device_input:
            return None, False

        d_slug = slug(device_input)
        allowed_devs = set(self.registry.allowed_devices()) if self.registry else set(DEVICE_ALIASES.keys())

        # 1. Exact match
        if d_slug in allowed_devs:
            return d_slug, False

        # 2. Alias match
        for canon, aliases in DEVICE_ALIASES.items():
            for a in aliases:
                if d_slug == slug(a):
                    target_dev = "light" if canon in ("den", "bong_den") else canon
                    return target_dev, False

        # 3. Unique Fuzzy match
        candidates = []
        for ad in allowed_devs:
            if ad.startswith(d_slug) or d_slug.startswith(ad):
                candidates.append(ad)
        if len(candidates) == 1:
            return candidates[0], False
        elif len(candidates) > 1:
            return None, True

        # 4. Hallucination
        return None, False

    def validate(self, result: IntentResult) -> IntentResult:
        """Thực thi kiểm định nghiêm ngặt trên IntentResult."""
        if not self.registry:
            return result

        # Validate Room
        if result.target.room:
            clean_r, is_ambig = self.resolve_room(result.target.room)
            if clean_r:
                result.target.room = clean_r
            elif is_ambig:
                result.target.room = None
                result.needs_clarification = True
                result.clarification_reason = "ambiguous_room"
            else:
                logger.warning(f"🚫 [StrictValidator] Rejected hallucinated room '{result.target.room}'")
                result.target.room = None
                result.needs_clarification = True
                result.clarification_reason = "unregistered_room"

        # Validate Device
        if result.target.device_type and result.target.device_type != "all":
            clean_d, is_ambig = self.resolve_device(result.target.device_type)
            if clean_d:
                result.target.device_type = clean_d
            elif is_ambig:
                result.target.device_type = None
                result.needs_clarification = True
                result.clarification_reason = "ambiguous_device"
            else:
                logger.warning(f"🚫 [StrictValidator] Rejected hallucinated device '{result.target.device_type}'")
                result.target.device_type = None
                result.needs_clarification = True
                result.clarification_reason = "unregistered_device"

        result._sync_dict()
        return result


# ── MODULE 5: FAST PATH ENGINE ───────────────────────────────────────────────

class FastPathEngine:
    """
    Fast-Path Rule Matcher hiệu năng cao (< 5ms trên Pi 4).
    Phân cấp độ tin cậy rõ ràng:
      HIGH (≥ 0.95): Thực thi tức thì, bypass LLM.
      MEDIUM (0.60 - 0.94): Cảm xúc/ngữ cảnh, có thể nhờ LLM nếu cần.
      AMBIGUOUS (< 0.60): Thiếu slot, chuyển Context Resolver hoặc hỏi lại.
    """

    def extract(self, norm: NormalizedText) -> Optional[IntentResult]:
        text = norm.text
        if not text:
            return None

        # 1. Kiểm tra Negation trước tiên
        if NegationDetector.is_negated(text):
            return IntentResult(
                intent="unknown",
                target=Target(),
                confidence=0.99,
                source="fast_path",
                negated=True,
                raw_text=norm.original_text,
                normalized_text=norm.text,
                needs_clarification=True,
                clarification_reason="negation_detected",
                voice_reply="Đã hủy lệnh."
            )

        # 2. Xử lý Scene / Ngữ cảnh sinh hoạt
        scene_intent = self._extract_scene(norm)
        if scene_intent:
            return scene_intent

        # 3. Xử lý Query vs Command (Truy vấn trạng thái / Cảm biến)
        query_intent = self._extract_query(norm)
        if query_intent:
            return query_intent

        # 4. Trích xuất Action cơ bản
        action, action_conf = self._extract_action(text)

        # 5. Trích xuất Value (Nhiệt độ điều hòa số hoặc chữ)
        value = self._extract_temperature(text)

        # 6. Trích xuất Thiết bị & Phòng
        device, dev_conf = self._extract_device(text)
        room, room_conf = self._extract_room(text)

        # Cảm xúc / Sensory trigger (nóng quá, tối quá, lạnh quá, cho mát)
        sensory_intent = self._extract_sensory(norm)
        if sensory_intent and not action:
            return sensory_intent

        # Nếu không có action và không có value nhiệt độ
        if not action and value is None:
            if device:
                return IntentResult(
                    intent="unknown",
                    target=Target(device_type=device, room=room),
                    confidence=0.50,
                    source="fast_path",
                    needs_clarification=True,
                    clarification_reason="missing_action",
                    raw_text=norm.original_text,
                    normalized_text=norm.text,
                    voice_reply=f"Bạn muốn bật hay tắt {get_device_name(device)}?"
                )
            return None

        # Nếu có giá trị nhiệt độ mà không có action rõ ràng -> set_temperature
        if value is not None and not action:
            action = "set_temperature"
            action_conf = 0.95

        # Nếu điều hòa và set_value -> chuyển về set_temperature
        if action == "set_value" and value is not None:
            action = "set_temperature"

        # Tính toán mức độ tin cậy tổng thể (Confidence Calibration)
        confidence = norm.confidence * action_conf
        needs_clarify = False
        clarify_reason = None

        if not device and not room and action in ("turn_on", "turn_off"):
            if re.search(r"\b(hết|tất cả|toàn bộ)\b", text):
                device = "all"
                confidence = 0.98

        if device and room:
            confidence = min(0.99, norm.confidence * 0.98)
        elif device and not room:
            # Lệnh đơn (bật đèn, tắt quạt, bật relay 1)
            confidence = min(0.98, norm.confidence * 0.98)
        elif not device and room and action != "set_temperature":
            confidence = 0.60
            needs_clarify = True
            clarify_reason = "missing_device"
        elif not device and not room:
            confidence = 0.45
            needs_clarify = True
            clarify_reason = "missing_slots"

        target = Target(device_type=device, room=room)

        # Pre-computed refined Vietnamese voice reply
        v_reply = None
        if action in ("turn_on", "turn_off"):
            act_vi = "bật" if action == "turn_on" else "tắt"
            if device == "all":
                v_reply = f"Đã {act_vi} tất cả thiết bị."
            elif device:
                dev_vi = get_device_name(device)
                room_vi = get_room_name(room)
                if room_vi:
                    v_reply = f"Đã {act_vi} {dev_vi} {room_vi}."
                else:
                    v_reply = f"Đã {act_vi} {dev_vi}."
        elif action == "set_temperature" and value:
            v_reply = f"Đã chỉnh điều hòa {value} độ."

        return IntentResult(
            intent=action or "unknown",
            target=target,
            value=value,
            unit="degree_celsius" if value else None,
            confidence=round(confidence, 2),
            source="fast_path",
            needs_clarification=needs_clarify,
            clarification_reason=clarify_reason,
            negated=False,
            raw_text=norm.original_text,
            normalized_text=norm.text,
            voice_reply=v_reply
        )

    def _extract_action(self, text: str) -> Tuple[Optional[str], float]:
        if re.search(r"\b(bật|mở|khởi động|kích hoạt|on|thắp|cho chạy)\b", text):
            return "turn_on", 0.98
        if re.search(r"\b(tắt|đóng|ngắt|dừng|off|cúp|hạ quạt)\b", text):
            return "turn_off", 0.98
        if re.search(r"\b(cài|đặt|chỉnh|set|tăng|giảm)\b", text):
            return "set_value", 0.95
        return None, 0.0

    def _extract_device(self, text: str) -> Tuple[Optional[str], float]:
        for canon, aliases in DEVICE_ALIASES.items():
            for a in aliases:
                pattern = r"\b" + re.escape(a) + r"\b"
                if re.search(pattern, text):
                    dev = "light" if canon in ("den", "bong_den") else canon
                    return dev, 0.98
        return None, 0.0

    def _extract_room(self, text: str) -> Tuple[Optional[str], float]:
        for canon, aliases in ROOM_ALIASES.items():
            for a in aliases:
                pattern = r"\b" + re.escape(a) + r"\b"
                if re.search(pattern, text):
                    return canon, 0.98
        return None, 0.0

    def _extract_temperature(self, text: str) -> Optional[int]:
        # 1. Dạng số chữ số: 25 độ, 26, 24 độ c
        num_match = re.search(r"\b(1[6-9]|2[0-9]|3[0-2])\s*(?:độ|do|c)?\b", text)
        if num_match:
            return int(num_match.group(1))

        # 2. Dạng số từ tiếng Việt: ưu tiên cụm từ dài trước (ví dụ 'hai mươi lăm' trước 'hai mươi')
        for word, val in sorted(VIETNAMESE_NUMBERS.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = r"\b" + re.escape(word) + r"(?:\s*độ)?\b"
            if re.search(pattern, text):
                return val

        return None

    def _extract_query(self, norm: NormalizedText) -> Optional[IntentResult]:
        text = norm.text
        # Query sensor: "phòng ngủ bao nhiêu độ", "nhiệt độ phòng khách"
        if re.search(r"\b(bao nhiêu độ|nhiệt độ|độ ẩm|mấy độ)\b", text):
            room, _ = self._extract_room(text)
            return IntentResult(
                intent="query_sensor",
                target=Target(room=room),
                value="temperature",
                confidence=0.96,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )

        # Query state: "đèn phòng ngủ đang bật không", "quạt có đang chạy không", "quạt đang chạy không"
        if re.search(r"\b(?:có\s+)?đang\s+(?:bật|tắt|chạy|mở|hoạt động)\s+(?:không|chưa)\b|\b(?:bật|tắt|chạy|mở)\s+chưa\b", text):
            device, _ = self._extract_device(text)
            room, _ = self._extract_room(text)
            return IntentResult(
                intent="query_state",
                target=Target(device_type=device, room=room),
                confidence=0.96,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )

        return None

    def _extract_scene(self, norm: NormalizedText) -> Optional[IntentResult]:
        text = norm.text
        if re.search(r"\b(đi ngủ|ngủ thôi|ngủ đây|chúc ngủ ngon|tắt đèn đi ngủ)\b", text):
            return IntentResult(
                intent="scene",
                target=Target(),
                scene="sleep",
                confidence=0.95,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        if re.search(r"\b(ra ngoài|đi làm|đi vắng|rời nhà)\b", text):
            return IntentResult(
                intent="scene",
                target=Target(),
                scene="leave_home",
                confidence=0.95,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        return None

    def _extract_sensory(self, norm: NormalizedText) -> Optional[IntentResult]:
        text = norm.text
        room, _ = self._extract_room(text)
        if re.search(r"\b(nóng quá|trời nóng|oi bức|nóng nực)\b", text):
            dev = "air_conditioner" if re.search(r"\b(điều hòa|máy lạnh)\b", text) else "fan"
            return IntentResult(
                intent="turn_on",
                target=Target(device_type=dev, room=room),
                confidence=0.70,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        if re.search(r"\b(tối quá|trời tối|tối thui|chẳng thấy gì)\b", text):
            return IntentResult(
                intent="turn_on",
                target=Target(device_type="light", room=room),
                confidence=0.70,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        if re.search(r"\b(lạnh quá|rét quá)\b", text):
            return IntentResult(
                intent="turn_off",
                target=Target(device_type="air_conditioner", room=room),
                confidence=0.70,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        if re.search(r"\b(mát|cho mát|mát hơn|làm mát|mát mẻ)\b", text):
            dev = "air_conditioner" if re.search(r"\b(điều hòa|máy lạnh)\b", text) else "fan"
            return IntentResult(
                intent="turn_on",
                target=Target(device_type=dev, room=room),
                confidence=0.65,
                source="fast_path",
                raw_text=norm.original_text,
                normalized_text=norm.text
            )
        return None


# ── MAIN INTENT ENGINE V3 ───────────────────────────────────────────────────

class IntentEngine:
    """
    Bộ xử lý ý định thế hệ 3 (Production-Ready Smart Home Intent Engine v3).
    Hỗ trợ Hybrid (Fast-Path → Context → Gemini Cloud → Qwen Local)
    Tối ưu độ trễ thấp trên Raspberry Pi 4 4GB.
    """
    def __init__(self, registry=None):
        self.url = config.LLAMA_URL
        self.registry = registry
        self._base_prompt = config.SYSTEM_PROMPT
        self.active_engine = "Fast-Path"

        # Khởi tạo các module con
        self.normalizer = ASRNormalizer()
        self.fast_path = FastPathEngine()
        self.context_manager = IntentContextManager(
            ttl_seconds=getattr(config, "CONTEXT_TTL", 60.0)
        )
        self._session_contexts = {}
        self.validator = StrictValidator(registry=self.registry)

    def set_registry(self, registry):
        self.registry = registry
        self.validator.set_registry(registry)

    def _is_potential_command(self, text: str) -> bool:
        """Kiểm tra nhanh (0.0001s) xem câu nói có bất kỳ từ khóa smarthome nào không."""
        if not text or len(text.strip()) < 2:
            return False
        t = text.lower().strip()
        keywords = [
            "bật", "tắt", "mở", "đóng", "cài", "đặt", "chỉnh", "tăng", "giảm",
            "set", "on", "off", "khởi động", "ngắt", "dừng", "kích hoạt",
            "bạn bè", "bất quá", "bật quà", "bật quát", "bạt đèn", "đèn", "quạt",
            "máy lạnh", "điều hòa", "bơm", "rèm", "tivi", "tv", "nóng", "lạnh", "tối",
            "phòng", "bếp", "khách", "ngủ", "độ", "nhiệt độ", "đi ngủ", "ra ngoài", "mát",
            "ổ cắm", "ổ điện", "socket", "ban đêm", "đêm qua", "không ngủ"
        ]
        return any(k in t for k in keywords)

    def _split_compound_command(self, raw_text: str) -> List[str]:
        """Tách câu lệnh ghép (Compound / Multi-command) thành các mệnh đề riêng biệt."""
        parts = re.split(r"\b(?:và|đồng thời|rồi sau đó|rồi|với lại)\b|,", raw_text)
        clean_parts = [p.strip() for p in parts if len(p.strip()) > 3]
        return clean_parts if len(clean_parts) > 1 else [raw_text]

    async def extract(self, user_text: str, session_key: str = None) -> IntentResult:
        """
        Entry Point chính: Nhận khẩu lệnh ASR text và trả về IntentResult chuẩn cấu trúc.
        """
        context = self.context_manager
        if session_key is not None:
            now = time.monotonic()
            ttl = getattr(config, "CONTEXT_TTL", 60.0)
            self._session_contexts = {k: v for k, v in self._session_contexts.items()
                                      if now - v[0] < ttl}
            entry = self._session_contexts.pop(session_key, None)
            context = entry[1] if entry else IntentContextManager(ttl_seconds=ttl)
            if len(self._session_contexts) >= 128:
                self._session_contexts.pop(next(iter(self._session_contexts)))
            self._session_contexts[session_key] = (now, context)
        t0 = time.time()
        logger.info(f"🎤 [ASR] original=\"{user_text}\"")

        # ── 1. Kiểm tra câu lệnh ghép (Multi-command) ──
        clauses = self._split_compound_command(user_text)
        if len(clauses) > 1:
            sub_results: List[IntentResult] = []
            for clause in clauses:
                sub_res = await self._extract_single(clause, context)
                sub_results.append(sub_res)

            min_conf = min((r.confidence for r in sub_results), default=0.9)
            multi_result = IntentResult(
                intent="multi_command",
                target=Target(),
                confidence=min_conf,
                source="fast_path_compound",
                raw_text=user_text,
                commands=sub_results
            )
            if sub_results:
                multi_result["command"] = sub_results[0]["command"]
            self.active_engine = "Fast-Path (Multi-Command)"
            logger.info(f"⚡ [INTENT] Multi-command resolved: {len(sub_results)} sub-commands")
            return multi_result

        return await self._extract_single(user_text, context)

    async def _extract_single(self, user_text: str, context=None) -> IntentResult:
        context = context if context is not None else self.context_manager
        # ── 2. ASR Normalization ──
        norm = self.normalizer.normalize(user_text)
        if norm.corrections:
            logger.info(f"🔧 [NORMALIZE] normalized=\"{norm.text}\" (applied: {norm.corrections})")

        # ── 3. Fast-Path Pattern Matcher ──
        fast_result = self.fast_path.extract(norm)

        # ── 4. Context Resolution (Multi-turn) ──
        if fast_result:
            resolved_result = context.resolve(fast_result, user_text)
        else:
            resolved_result = None

        # Nếu Fast-Path đạt HIGH CONFIDENCE (≥ 0.95) và không bị mơ hồ -> Bypass LLM!
        if resolved_result and resolved_result.confidence >= 0.95 and not resolved_result.needs_clarification:
            self.active_engine = "Fast-Path (Instant)"
            final_result = self.validator.validate(resolved_result)
            context.update(final_result)
            logger.info(
                f"⚡ [INTENT] source={final_result.source} intent={final_result.intent} "
                f"device={final_result.target.device_type} room={final_result.target.room} "
                f"val={final_result.value} conf={final_result.confidence:.2f}"
            )
            return final_result

        # Nếu câu có dấu hiệu phủ định -> Trả về kết quả phủ định ngay
        if resolved_result and resolved_result.negated:
            self.active_engine = "Fast-Reject (Negated)"
            return resolved_result

        # ── 5. Non-Command Rejection Filter (0.0001s) ──
        if not self._is_potential_command(norm.text):
            self.active_engine = "Fast-Reject (Non-Command)"
            logger.info(f"🚫 [Non-Command Reject] '{user_text}' is not a smart home command.")
            return IntentResult(
                intent="unknown",
                target=Target(),
                confidence=0.99,
                source="fast_reject",
                raw_text=user_text,
                needs_clarification=True,
                clarification_reason="non_smarthome_command",
                voice_reply="Chưa rõ khẩu lệnh. Bạn muốn điều khiển thiết bị nào?"
            )

        # Nếu Fast-Path có kết quả khả dĩ (MEDIUM confidence) nhưng chưa cần LLM
        if resolved_result and resolved_result.confidence >= 0.60 and not resolved_result.needs_clarification:
            self.active_engine = "Fast-Path (Medium-Confidence)"
            final_result = self.validator.validate(resolved_result)
            context.update(final_result)
            logger.info(
                f"⚡ [INTENT] source={final_result.source} intent={final_result.intent} "
                f"device={final_result.target.device_type} room={final_result.target.room} "
                f"val={final_result.value} conf={final_result.confidence:.2f}"
            )
            return final_result

        # ── 6. Hybrid LLM NLU (Chỉ kích hoạt khi AI_ENABLED = True và LLM_MODE != 'off') ──
        mode = getattr(config, "LLM_MODE", "off").lower()
        ai_enabled = getattr(config, "AI_ENABLED", False)

        if not ai_enabled or mode == "off":
            if resolved_result:
                self.active_engine = "Fast-Path (Voice Relay)"
                final_result = self.validator.validate(resolved_result)
                context.update(final_result)
                logger.info(
                    f"⚡ [INTENT-VOICE-RELAY] source={final_result.source} intent={final_result.intent} "
                    f"device={final_result.target.device_type} room={final_result.target.room} "
                    f"val={final_result.value} conf={final_result.confidence:.2f}"
                )
                return final_result
            return self._fallback_unknown(user_text)

        api_key = getattr(config, "GEMINI_API_KEY", "").strip()

        if httpx and mode in ("hybrid", "cloud") and api_key:
            res_llm = await self._extract_gemini(norm.text, api_key)
            if res_llm:
                self.active_engine = f"Gemini ({config.GEMINI_MODEL})"
                final_res = self._convert_llm_result(res_llm, user_text, norm.text, source="cloud_llm")
                final_res = context.resolve(final_res, user_text)
                final_res = self.validator.validate(final_res)
                context.update(final_res)
                return final_res
            if mode == "cloud":
                logger.error("Cloud-only mode: Gemini failed and local fallback is disabled")
                return self._fallback_unknown(user_text)

        if httpx:
            self.active_engine = "Qwen (Local Offline)"
            res_local = await self._extract_local(norm.text)
            if res_local:
                final_res = self._convert_llm_result(res_local, user_text, norm.text, source="local_llm")
                final_res = context.resolve(final_res, user_text)
                final_res = self.validator.validate(final_res)
                context.update(final_res)
                return final_res

        # Nếu tất cả thất bại nhưng trước đó có resolved_result từ Fast-Path
        if resolved_result:
            return self.validator.validate(resolved_result)

        return self._fallback_unknown(user_text)

    def _convert_llm_result(
        self, llm_dict: dict, raw_text: str, norm_text: str, source: str
    ) -> IntentResult:
        """Chuyển đổi dictionary thô từ LLM thành IntentResult v3."""
        cmd = llm_dict.get("command", {})
        act = cmd.get("action", "unknown")
        dev = cmd.get("device")
        loc = cmd.get("location")
        val = cmd.get("value")

        if act in ("bat", "mo", "turn_on", "on"):
            act = "turn_on"
        elif act in ("tat", "dong", "turn_off", "off"):
            act = "turn_off"
        elif act in ("set", "set_value", "chinh"):
            act = "set_temperature" if val is not None else "set_value"

        target = Target(device_type=dev, room=loc)
        return IntentResult(
            intent=act,
            target=target,
            value=val,
            unit="degree_celsius" if val else None,
            confidence=0.92,
            source=source,
            raw_text=raw_text,
            normalized_text=norm_text,
            voice_reply=llm_dict.get("voice_reply")
        )

    def _fallback_unknown(self, raw_text: str) -> IntentResult:
        return IntentResult(
            intent="unknown",
            target=Target(),
            confidence=0.0,
            source="fallback",
            raw_text=raw_text,
            needs_clarification=True,
            clarification_reason="unintelligible_command",
            voice_reply="Chưa rõ khẩu lệnh. Xin vui lòng thử lại."
        )

    def _build_minimal_prompt_for_pi4(self, user_text: str) -> str:
        """
        Tạo prompt tối giản (< 120 tokens) tối ưu hóa cho Qwen 2.5 trên CPU Pi 4 4GB.
        Không inject toàn bộ inventory hàng chục thiết bị vào prompt.
        """
        rooms = ", ".join(self.registry.allowed_rooms()[:6]) if self.registry else "phong_ngu, phong_khach, phong_bep"
        devs = ", ".join(self.registry.allowed_devices()[:6]) if self.registry else "light, fan, air_conditioner"
        return (
            f"Bạn là bộ trích xuất ý định nhà thông minh. Chỉ trả JSON duy nhất:\n"
            f'Schema: {{"command":{{"action":"turn_on|turn_off|set_value|unknown","device":"...|null","location":"...|null","value":null}}}}\n'
            f"Phòng hợp lệ: [{rooms}]\n"
            f"Thiết bị hợp lệ: [{devs}]\n"
            f"Lệnh người dùng: \"{user_text}\""
        )

    async def _extract_gemini(self, user_text: str, api_key: str) -> Optional[dict]:
        if not httpx:
            return None
        prompt = self._build_minimal_prompt_for_pi4(user_text)
        url = f"{config.GEMINI_URL}?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 100,
                "responseMimeType": "application/json"
            }
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=config.GEMINI_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return None
                content = parts[0].get("text", "").strip()
                logger.info(f"⚡ [Gemini Flash] raw: {content}")
                return self._parse_json(content)
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")
            return None

    async def _extract_local(self, user_text: str) -> Optional[dict]:
        if not httpx:
            return None
        prompt = self._build_minimal_prompt_for_pi4(user_text)
        payload = {
            "model": "qwen",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.url, json=payload, timeout=config.LLAMA_TIMEOUT)
                resp.raise_for_status()
                choices = resp.json().get("choices", [])
                if not choices:
                    return None
                content = choices[0].get("message", {}).get("content", "").strip()
                logger.info(f"🏠 [Local Qwen] raw: {content[:200]}")
                return self._parse_json(content)
        except Exception as e:
            logger.warning(f"Local Qwen call failed: {e}")
            return None

    def _parse_json(self, text: str) -> Optional[dict]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end])
                except Exception:
                    pass
        return None

    def validate_intent(self, intent: Any) -> bool:
        """Kiểm tra tính hợp lệ của intent (cho main.py)."""
        if not intent:
            return False
        if isinstance(intent, IntentResult):
            return True
        if isinstance(intent, dict):
            cmd = intent.get("command")
            if isinstance(cmd, dict) and "action" in cmd:
                return True
        return False
