"""
Intent Engine — LLM-based Vietnamese voice command extraction.
Uses Qwen2.5-1.5B-Instruct via llama-server OpenAI-compatible /v1/chat/completions API.
"""

import json
import logging
from typing import Optional

import httpx

import config

logger = logging.getLogger("intent")


class IntentEngine:
    """Extract structured JSON intent from Vietnamese voice commands."""
    
    def __init__(self):
        self.url = config.LLAMA_URL
        self.system_prompt = config.SYSTEM_PROMPT
    
    async def extract(self, user_text: str) -> Optional[dict]:
        payload = {
            "model": "qwen",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_text}
            ],
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.url, json=payload,
                    timeout=config.LLAMA_TIMEOUT,
                )
                resp.raise_for_status()
                
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    logger.warning("No choices returned from LLM")
                    return None
                    
                content = choices[0].get("message", {}).get("content", "").strip()
                logger.info(f"LLM raw output: {content[:200]}")
                
                result = self._parse_json(content)
                if result:
                    logger.info(f"Intent extracted: {json.dumps(result, ensure_ascii=False)}")
                    return result
                else:
                    logger.warning(f"Failed to parse LLM output as JSON: {content[:100]}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error("LLM request timed out")
            return None
        except Exception as e:
            logger.error(f"Intent extraction error: {e}")
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
        except json.JSONDecodeError:
            pass
        
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
        
        return None
    
    def validate_intent(self, intent: dict) -> bool:
        if not isinstance(intent, dict):
            return False
        command = intent.get("command")
        if not isinstance(command, dict):
            return False
        required = ["action", "device", "location"]
        return all(command.get(k) is not None for k in required)
