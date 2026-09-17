"""
Persona & Chat Engine — Lifelike AI Companion for DTV Smart Home
================================================================
Biến trợ lý nhà thông minh thành người bạn thân thiết:
  1. Trò chuyện, tâm sự, hỏi han, động viên ân cần.
  2. Kể chuyện cười, đố vui, hát những bài hát vui tươi bằng giọng EdgeTTS.
  3. Tích hợp Google Gemini Flash API cho câu trả lời thông minh, sâu sắc (0.4s).
  4. Kho dữ liệu cục bộ phong phú (Offline Persona) hoạt động hoàn hảo khi mất mạng.
"""

import re
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import config

logger = logging.getLogger("persona")
TZ_VN = timezone(timedelta(hours=7))


SONG_LIBRARY = [
    "🎶 Một con vịt xòe ra hai cái cánh, nó kêu rằng cáp cáp cáp cạp cạp cạp... Gặp hồ nước nó bì bà bì bõm, lúc lên bờ vẫy cái cánh cho khô! 🎵 Em hát vậy anh thấy có vui tai không ạ? 😊",
    "🎵 Tình tính tang tang tính tình... Cuộc đời vẫn đẹp sao, tình yêu vẫn đẹp sao! Chúc anh một ngày luôn tràn đầy niềm vui và may mắn nha! 🎶",
    "🎶 Chú voi con ở Bản Đôn, chưa có ngà nên còn trẻ con... Từ rừng già chú đến với người, rất ham ăn với lại ham chơi! 🎵 Em hát tặng anh đấy, nghe yêu đời hẳn ra đúng không nào!",
    "🎵 Ba thương con vì con giống mẹ, mẹ thương con vì con giống ba... Cả nhà ta cùng thương yêu nhau, xa là nhớ gần nhau là cười! 🎶",
    "🎶 Kìa con bướm vàng, kìa con bướm vàng, xòe đôi cánh, xòe đôi cánh... Bươm bướm bay đôi ba vòng, bươm bướm bay đôi ba vòng, em ngồi xem! 🎵 Anh thấy em có khiếu ca hát không nè?"
]

JOKE_LIBRARY = [
    "Dạ có câu chuyện này vui lắm anh nè: Một anh chàng hỏi bạn: Bí quyết nào giúp cậu luôn bình tĩnh và hạnh phúc vậy? Người bạn đáp: Đơn giản thôi, đừng bao giờ tranh cãi với những kẻ ngốc. Anh chàng cãi ngay: Tôi thấy vô lý hết sức! Người bạn mỉm cười: Ừ, cậu nói đúng rồi đấy! Hihi.",
    "Dạ có câu đố vui cho anh: Cái gì đi lên đi xuống suốt ngày mà không bao giờ tự di chuyển? ... Dạ chính là cái cầu thang đó anh! Em đố anh trả lời kịp em đó!",
    "Bác sĩ hỏi bệnh nhân: Dạo này anh còn nghe thấy những tiếng nói vô hình trong đầu không? Bệnh nhân mừng rỡ: Dạ hết rồi bác sĩ ơi, từ ngày em ly dị vợ là êm hẳn! Em đùa chút cho anh vui thôi nha!",
    "Một người hỏi anh IT: Làm sao để có người yêu xinh đẹp, ngoan ngoãn và không bao giờ cãi lời? Anh IT suy nghĩ một lúc rồi bảo: Cài lại hệ điều hành đi bạn! Hihi."
]

CARING_RESPONSES = [
    "Anh làm việc cả ngày mệt rồi đúng không ạ? Nhớ uống thêm nước và nghỉ ngơi một chút nhé, việc nhà cứ để em lo!",
    "Dù hôm nay có nhiều áp lực thế nào thì về đến nhà cũng phải thật thoải mái anh nha! Em luôn ở đây cùng anh mà.",
    "Hôm nay ngôi nhà của chúng ta rất bình yên và mọi thiết bị đều hoạt động hoàn hảo. Anh thư giãn nghe nhạc chút đi ạ!",
    "Thấy anh vui là em cũng vui lây luôn đó! Chúc anh một buổi tối thật an lành và ấm áp nha."
]


class PersonaEngine:
    """Xử lý hội thoại tự nhiên, hát, kể chuyện cười và tương tác nhân cách hóa."""

    def __init__(self):
        self.name = getattr(config, "PERSONA_NAME", "Lumi")
        self.gemini_url = getattr(config, "GEMINI_URL", "")
        self.gemini_api_key = getattr(config, "GEMINI_API_KEY", "")

    @property
    def has_api_key(self) -> bool:
        k = getattr(config, "GEMINI_API_KEY", "") or self.gemini_api_key
        return bool(k and k.strip())

    @property
    def api_key(self) -> str:
        return getattr(config, "GEMINI_API_KEY", "") or self.gemini_api_key

    @api_key.setter
    def api_key(self, val: str):
        self.gemini_api_key = val


    def is_conversational(self, user_text: str) -> bool:
        """Kiểm tra xem câu nói có phải là câu trò chuyện, yêu cầu hát, đố vui hay tâm sự không."""
        if not user_text:
            return False
        t = user_text.lower().strip()

        chat_patterns = [
            # Yêu cầu hát
            r"\b(hát|ca một bài|ngân nga|hát hò|hát bài|hát cho|hát đi|karaoke)\b",
            # Kể chuyện cười / hài
            r"\b(kể chuyện cười|kể chuyện vui|nói câu gì vui|hài hước|đố vui|câu đố)\b",
            # Hỏi danh tính / bản thân
            r"\b(em là ai|bạn là ai|em tên gì|bạn tên gì|bạn tên là gì|tên bạn là gì|tên của em|ai tạo ra em|em mấy tuổi|em sinh năm)\b",
            # Chào hỏi / cảm xúc / tâm sự
            r"\b(chào em|xin chào|em ơi|hôm nay mệt quá|buồn quá|mệt mỏi|chán quá|em ngoan|cảm ơn em|yêu em)\b",
            # Hỏi giờ / ngày / thời tiết
            r"\b(mấy giờ|bây giờ là mấy giờ|hôm nay thứ mấy|hôm nay ngày mấy|ngày bao nhiêu|thời tiết|trời hôm nay)\b",
            # Khen ngợi
            r"\b(giỏi quá|thông minh quá|được đấy|hay quá|tuyệt vời)\b",
        ]
        return any(re.search(pat, t) for pat in chat_patterns)

    async def reply(self, user_text: str) -> str:
        """Sinh câu trả lời thông minh qua Gemini Flash hoặc Persona Engine cục bộ."""
        api_key = getattr(config, "GEMINI_API_KEY", "").strip()

        # 1. Thử gọi Cloud Gemini Flash nếu có API Key (trí tuệ không giới hạn)
        if api_key:
            try:
                gemini_reply = await self._call_gemini(user_text, api_key)
                if gemini_reply:
                    return gemini_reply
            except Exception as e:
                logger.warning(f"Gemini persona call failed: {e}")

        # 2. Xử lý cục bộ bằng thư viện Persona & Hát Offline
        return self._offline_reply(user_text)

    async def _call_gemini(self, user_text: str, api_key: str) -> Optional[str]:
        """Gọi Google Gemini Flash API cho câu trả lời tự nhiên, ngọt ngào, luyến láy."""
        system_prompt = (
            f"Bạn là {self.name}, một nữ trợ lý AI nhà thông minh cực kỳ ngọt ngào, dịu dàng, ấm áp và luyến láy dễ thương.\n"
            f"Quy tắc xưng hô & phong cách:\n"
            f"- BẮT BUỘC luôn xưng 'em' và gọi người dùng là 'anh'. Tuyệt đối không bao giờ dùng 'tôi', 'bạn' hay 'mình'.\n"
            f"- Giọng điệu nữ tính, nũng nịu, ngọt ngào, ấm áp như người bạn gái hoặc em gái nhỏ chăm sóc chu đáo cho anh.\n"
            f"- Sử dụng các từ đệm và trợ từ tình thái tiếng Việt dịu dàng: 'nè~', 'nha anh~', 'nhé anh', 'dạ anh ơi~', 'ạ~'.\n"
            f"- Thêm dấu phẩy sau các từ cảm thán để ngắt nhịp thở nhẹ nhàng trước khi nói tiếp.\n"
            f"- Nếu người dùng bảo hát: Viết lời hát có vần điệu tươi vui, kèm emoji âm nhạc 🎶 🎵.\n"
            f"- Trả lời ngắn gọn từ 1 đến 3 câu tiếng Việt tự nhiên có dấu, không dùng định dạng markdown."
        )

        url = f"{config.GEMINI_URL}?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 100,
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=3.5)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    txt = parts[0].get("text", "").strip()
                    # Loại bỏ ký tự markdown nếu có
                    txt = re.sub(r"[*#_`]", "", txt).strip()
                    logger.info(f"✨ [Gemini Persona] Reply: {txt}")
                    return txt
        return None

    def _offline_reply(self, user_text: str) -> str:
        """Sinh câu trả lời offline thông minh, ngọt ngào, dịu dàng, gọi anh xưng em."""
        t = user_text.lower().strip()
        now = datetime.now(TZ_VN)

        # 1. Yêu cầu hát
        if any(w in t for w in ("hát", "ca một bài", "ngân nga", "hát hò", "karaoke")):
            return random.choice(SONG_LIBRARY)

        # 2. Yêu cầu kể chuyện cười / đố vui
        if any(w in t for w in ("chuyện cười", "chuyện vui", "hài hước", "đố vui", "câu đố")):
            return random.choice(JOKE_LIBRARY)

        # 3. Hỏi giờ giấc
        if any(w in t for w in ("mấy giờ", "bây giờ là mấy giờ")):
            return f"Dạ anh ơi, bây giờ là {now.hour} giờ {now.minute:02d} phút rồi nè~ Anh nhớ giữ gìn sức khỏe nha!"

        # 4. Hỏi ngày tháng
        if any(w in t for w in ("thứ mấy", "ngày mấy", "ngày bao nhiêu")):
            days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
            day_name = days[now.weekday()]
            return f"Dạ hôm nay là {day_name}, ngày {now.day} tháng {now.month} nè anh. Chúc anh một ngày tràn đầy năng lượng nha~"

        # 5. Hỏi danh tính
        if any(w in t for w in ("em là ai", "bạn là ai", "em tên gì", "bạn tên gì", "bạn tên là gì", "tên bạn là gì", "tên của em")):
            return f"Dạ em là {self.name}, trợ lý nhỏ của anh đây ạ! Em luôn ở đây để giúp anh điều khiển nhà cửa, tâm sự và hát cho anh nghe mỗi ngày nè~"

        if "ai tạo ra em" in t:
            return "Dạ em được sinh ra từ tình yêu công nghệ để luôn đồng hành và chăm sóc cho ngôi nhà của anh đó ạ!"

        # 6. Khen ngợi
        if any(w in t for w in ("giỏi quá", "thông minh quá", "tuyệt vời", "được đấy", "hay quá")):
            replies = [
                "Hihi, em cảm ơn anh yêu nha! Được anh khen là em vui cả ngày luôn á! Em sẽ luôn ngoan ngoãn phục vụ anh thật tốt nè~",
                "Dạ em cảm ơn anh nhiều! Có anh động viên là em có thêm bao nhiêu năng lượng luôn nè~",
                "Hihi em vui quá đi mất! Cảm ơn anh đã tin tưởng và yêu quý em nha!"
            ]
            return random.choice(replies)

        # 7. Tâm sự / than mệt mỏi
        if any(w in t for w in ("mệt quá", "buồn quá", "chán quá", "áp lực")):
            return random.choice(CARING_RESPONSES)

        # 8. Lời cảm ơn
        if "cảm ơn" in t:
            return "Dạ không có chi đâu anh ơi~ Giúp được anh là niềm hạnh phúc lớn nhất của em mà!"

        # 9. Lời chào chung
        if any(w in t for w in ("chào em", "xin chào", "hello", "chào")):
            hour = now.hour
            if 5 <= hour < 12:
                time_greet = "Dạ em chào buổi sáng anh yêu nè~ Chúc anh một ngày mới tràn ngập niềm vui và may mắn nha!"
            elif 12 <= hour < 18:
                time_greet = "Dạ em chào buổi chiều anh ạ! Hôm nay công việc của anh có thuận lợi không nè?"
            else:
                time_greet = "Dạ em chào buổi tối anh yêu! Anh đã ăn cơm nước gì chưa, nhớ nghỉ ngơi sớm nha anh!"
            return time_greet

        # Mặc định thân thiện
        return "Dạ, em nghe anh nè~ Em có thể giúp gì cho anh, hay anh muốn em hát tặng anh một câu không nào?"

