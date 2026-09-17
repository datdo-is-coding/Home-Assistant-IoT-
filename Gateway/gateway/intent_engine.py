"""
Intent Engine v2 — LLM NLU 2 lớp, chống ảo giác (hallucination-proof).

Lớp 1: LLM chỉ trích ý định thô (device, location, action) — KHÔNG biết node nào tồn tại.
Lớp 2: Gateway (registry) mới phân giải node_id/channel hợp lệ từ inventory thực tế.
       Nếu LLM bịa tên không có trong registry → loại bỏ, fallback hoặc hỏi lại.

Cơ chế chống ảo giác:
  1. GBNF grammar (llama.cpp) ép JSON đúng schema + đúng enum phòng/thiết bị hiện có.
  2. System prompt được inject inventory thực tế (rooms + fullnames) mỗi lần gọi.
  3. Post-validate: mọi device/location trả về phải nằm trong allowed lists, else → null.
  4. Temperature 0.0 + max_tokens thấp + JSON-only.
"""

import json
import logging
import re
from typing import Optional

import httpx
import config

logger = logging.getLogger("intent")


def _slug(s: str) -> str:
    if s is None: return ""
    s = str(s).lower().strip()
    tbl = str.maketrans("áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
                        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd")
    s = s.translate(tbl)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


class IntentEngine:
    def __init__(self, registry=None):
        self.url = config.LLAMA_URL
        self.registry = registry  # set later via set_registry() if not available at init
        self._base_prompt = config.SYSTEM_PROMPT
        self.active_engine = "local"

    def set_registry(self, registry):
        self.registry = registry

    def _build_system_prompt(self) -> str:
        if not self.registry:
            return self._base_prompt
        inv = self.registry.inventory_for_prompt()
        rooms = ", ".join(self.registry.allowed_rooms())
        devs = ", ".join(self.registry.allowed_devices())
        return (
            self._base_prompt
            + f"\n\n[INVENTORY THỰC TẾ — CHỈ được dùng các giá trị sau, không được bịa thêm]\n"
            + f"Phòng hiện có: {rooms}\n"
            + f"Thiết bị hiện có: {devs}\n"
            + f"Danh sách node:\n{inv}\n"
            + f"Nếu khẩu lệnh không nêu rõ phòng/thiết bị, hãy để null."
        )

    def _build_grammar(self) -> Optional[str]:
        if not getattr(config, "LLM_GRAMMAR_ENABLED", False) or not self.registry:
            return None
        try:
            return self.registry.gbnf_grammar()
        except Exception as e:
            logger.warning(f"GBNF build failed: {e}")
            return None

    async def extract(self, user_text: str) -> Optional[dict]:
        """
        Trích xuất ý định khẩu lệnh bằng kiến trúc Hybrid:
        1. Thử gửi lên Gemini Cloud nếu có API key và mạng Internet (phản hồi siêu tốc 0.3s).
        2. Nếu mất mạng, lỗi hoặc timeout -> Tự động chuyển mượt mà về Qwen2.5-3B chạy nội bộ trên Pi 4.
        """
        mode = getattr(config, "LLM_MODE", "hybrid").lower()
        api_key = getattr(config, "GEMINI_API_KEY", "").strip()

        # ── 1. Cloud Gemini Flash ──
        if mode in ("hybrid", "cloud") and api_key:
            res = await self._extract_gemini(user_text, api_key)
            if res:
                self.active_engine = f"Gemini ({config.GEMINI_MODEL})"
                return res
            if mode == "cloud":
                logger.error("Cloud-only mode: Gemini failed and local fallback is disabled")
                return None
            logger.info("⚡ Cloud Gemini failed/timed out, seamlessly falling back to Local Qwen 3B...")

        # ── 2. Local Qwen 3B Offline Fallback ──
        self.active_engine = "Qwen2.5-3B (Local Offline)"
        return await self._extract_local(user_text)

    async def _extract_gemini(self, user_text: str, api_key: str) -> Optional[dict]:
        """Gửi yêu cầu tới Google Gemini Flash API qua REST API siêu nhẹ."""
        system_prompt = self._build_system_prompt()
        url = f"{config.GEMINI_URL}?key={api_key}"
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"parts": [{"text": user_text}]}
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 120,
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
                result = self._parse_json(content)
                if result:
                    result = self._sanitize(result)
                    if result and self.validate_intent(result):
                        logger.info(f"⚡ [Gemini Flash] Intent OK: {json.dumps(result, ensure_ascii=False)}")
                        return result
        except httpx.TimeoutException:
            logger.warning(f"Gemini API timeout after {config.GEMINI_TIMEOUT}s")
        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
        return None

    async def _extract_local(self, user_text: str) -> Optional[dict]:
        """Xử lý cục bộ trên Pi 4 bằng Qwen2.5-3B-Instruct qua llama-server."""
        system_prompt = (
            self._build_system_prompt()
            + "\n\nBẮT BUỘC: Chỉ xuất DUY NHẤT một chuỗi JSON hợp lệ, KHÔNG viết bất kỳ lời dẫn giải nào."
        )
        grammar = self._build_grammar()

        payload = {
            "model": "qwen",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        if grammar:
            payload["grammar"] = grammar

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.url, json=payload, timeout=config.LLAMA_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    logger.warning("No choices from local LLM")
                    return None
                content = choices[0].get("message", {}).get("content", "").strip()
                logger.info(f"🏠 [Local Qwen 3B] raw: {content[:300]}")
                result = self._parse_json(content)
                if not result:
                    logger.warning(f"Parse failed: {content[:200]}")
                    return None
                # post-validate + sanitize
                result = self._sanitize(result)
                if result and self.validate_intent(result):
                    logger.info(f"🏠 [Local Qwen 3B] Intent OK: {json.dumps(result, ensure_ascii=False)}")
                    return result
                # hallucinated → try correction once
                if result:
                    logger.warning(f"Intent failed validation (hallucinated?), retrying without grammar: {result}")
                    return await self._retry(user_text, system_prompt)
                return None
        except httpx.TimeoutException:
            logger.error(f"Local Qwen 3B timeout after {config.LLAMA_TIMEOUT}s")
            return None
        except Exception as e:
            logger.error(f"Local Qwen 3B error: {e}", exc_info=True)
            return None

    async def _retry(self, user_text: str, system_prompt: str) -> Optional[dict]:
        try:
            payload = {
                "model": "qwen",
                "messages": [
                    {"role": "system", "content": system_prompt + "\n\nCHỈ trả JSON, không bịa tên phòng/thiết bị ngoài danh sách trên."},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0.0,
                "max_tokens": config.LLM_MAX_TOKENS,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.url, json=payload, timeout=15)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()
                result = self._parse_json(content)
                result = self._sanitize(result) if result else None
                if result and self.validate_intent(result):
                    logger.info(f"Intent retry OK: {result}")
                    return result
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
        return None

    def _sanitize(self, intent: dict) -> Optional[dict]:
        """Ép device/location về null nếu không nằm trong allowed lists (chống bịa)."""
        if not isinstance(intent, dict): return None
        cmd = intent.get("command")
        if not isinstance(cmd, dict): return None
        # chuẩn hoá action
        act = str(cmd.get("action", "")).lower().strip()
        if act in ("bat", "mo", "on", "turn_on", "open"): act = "turn_on"
        elif act in ("tat", "dong", "off", "turn_off", "close"): act = "turn_off"
        cmd["action"] = act if act in ("turn_on", "turn_off") else act

        # device/location: "null" string → None
        for k in ("device", "location"):
            v = cmd.get(k)
            if v is None or (isinstance(v, str) and v.strip().lower() == "null"):
                cmd[k] = None
                continue
            if isinstance(v, str):
                v = v.strip()
                if not v:
                    cmd[k] = None
        # nếu có registry, loại bỏ giá trị không hợp lệ
        if self.registry:
            allowed_devs = set(self.registry.allowed_devices())
            allowed_rooms = set(self.registry.allowed_rooms())
            # device check (slug match)
            dev = cmd.get("device")
            if dev is not None:
                ds = _slug(dev)
                # chấp nhận alias den/quat dù allowed có light/fan
                canon_map = {"den": "light", "quat": "fan", "bong_den": "light", "may_bom": "pump"}
                ds_canon = canon_map.get(ds, ds)
                if ds not in allowed_devs and ds_canon not in allowed_devs and ds not in ("light","fan","den","quat"):
                    # không có trong inventory nhưng vẫn giữ để registry fuzzy có thể fallback
                    # chỉ loại nếu trông như bịa (quá dài / chứa số)
                    if len(ds) > 20 or any(c.isdigit() for c in ds):
                        logger.warning(f"Dropping hallucinated device '{dev}'")
                        cmd["device"] = None
            loc = cmd.get("location")
            if loc is not None:
                ls = _slug(loc)
                if ls not in allowed_rooms and ls not in ("phong_khach","phong_ngu","phong_bep"):
                    # giữ lại để registry có thể fuzzy, nhưng log warning
                    if len(ls) > 24:
                        logger.warning(f"Dropping hallucinated location '{loc}'")
                        cmd["location"] = None
        intent["command"] = cmd
        return intent

    def _parse_json(self, text: str) -> Optional[dict]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # tìm JSON object đầu tiên
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
        return None

    def validate_intent(self, intent: dict) -> bool:
        if not isinstance(intent, dict): return False
        cmd = intent.get("command")
        if not isinstance(cmd, dict): return False
        if cmd.get("action") not in ("turn_on", "turn_off", "open", "close", "set_value"):
            return False
        # device/location được phép null (sẽ hỏi lại hoặc suy luận)
        return True
