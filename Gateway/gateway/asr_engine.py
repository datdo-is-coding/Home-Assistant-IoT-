"""
ASR Engine — Sherpa-ONNX Vietnamese speech recognition.
Converts PCM audio to Vietnamese text using Zipformer Transducer.

v2: Hotwords boosting (modified_beam_search) + Confidence scoring
    + Vietnamese phonetic post-correction for smarthome commands.
"""

import logging
import os
import re
import time
import unicodedata
from typing import Optional, Tuple
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

import config

logger = logging.getLogger("asr")

sherpa_onnx = None

def _ensure_sherpa():
    global sherpa_onnx
    if sherpa_onnx is None:
        try:
            import sherpa_onnx as _sherpa
            sherpa_onnx = _sherpa
            logger.info("sherpa_onnx imported successfully")
        except ImportError:
            logger.error("sherpa_onnx not installed")
            raise

SMARTHOME_HOTWORDS = [

    "BẬT", "TẮT", "MỞ", "ĐÓNG", "CÀI", "ĐẶT", "CHỈNH",

    "ĐÈN", "QUẠT", "ĐIỀU HÒA", "MÁY LẠNH", "RÈM", "BƠM",
    "ĐÈN NGỦ", "ĐÈN TRẦN", "QUẠT TRẦN", "BÌNH NÓNG LẠNH",
    "CỬA CUỐN", "GIÀN PHƠI", "MÁY HÚT MÙI",

    "PHÒNG KHÁCH", "PHÒNG NGỦ", "PHÒNG BẾP", "PHÒNG TẮM",
    "PHÒNG LÀM VIỆC", "BAN CÔNG", "SÂN VƯỜN", "SÂN THƯỢNG",
    "HÀNH LANG", "PHÒNG THỜ", "PHÒNG VỆ SINH", "GARA",

    "BẬT ĐÈN", "TẮT ĐÈN", "BẬT QUẠT", "TẮT QUẠT",
    "BẬT ĐIỀU HÒA", "TẮT ĐIỀU HÒA", "MỞ RÈM", "ĐÓNG RÈM",

    "ĐỘ", "MƯỜI SÁU", "MƯỜI BẢY", "MƯỜI TÁM", "HAI MƯƠI",
    "HAI LĂM", "HAI SÁU", "HAI BẢY", "HAI TÁM", "BA MƯƠI",
]

ASR_PHONETIC_CORRECTIONS = [

    (r"\bbật quá\b", "bật quạt"),
    (r"\bbật quà\b", "bật quạt"),
    (r"\bbật quát\b", "bật quạt"),
    (r"\bmở quá\b", "mở quạt"),
    (r"\btắt quá\b", "tắt quạt"),
    (r"\btắt quà\b", "tắt quạt"),

    (r"\bbật điên\b", "bật đèn"),
    (r"\btắt điên\b", "tắt đèn"),
    (r"\bbật đền\b", "bật đèn"),
    (r"\btắt đền\b", "tắt đèn"),
    (r"\bbật đêm\b", "bật đèn"),
    (r"\btắt đêm\b", "tắt đèn"),
    (r"\bbạt đèn\b", "bật đèn"),
    (r"\bbạt đền\b", "bật đèn"),


    (r"\bphong khách\b", "phòng khách"),
    (r"\bphòng khach\b", "phòng khách"),
    (r"\bphong khach\b", "phòng khách"),
    (r"\bphong khac\b", "phòng khách"),

    (r"\bphong ngu\b", "phòng ngủ"),
    (r"\bphòng ngu\b", "phòng ngủ"),
    (r"\bphong ngue\b", "phòng ngủ"),
    (r"\bphòng ngue\b", "phòng ngủ"),

    (r"\bphong bep\b", "phòng bếp"),
    (r"\bphòng bep\b", "phòng bếp"),

    (r"\bhòng ngủ\b", "phòng ngủ"),
    (r"\bphòng ngũ\b", "phòng ngủ"),
    (r"\bbật qua\b", "bật quạt"),
    (r"\bbắt quạt\b", "bật quạt"),
    (r"\btắt qua\b", "tắt quạt"),
    (r"\btác quạt\b", "tắt quạt"),

    (r"\bquạt điện\b", "quạt"),
    (r"\bbóng đèn\b", "đèn"),
    (r"\bmáy lạnh\b", "điều hòa"),
    (r"\bmáy điều hòa\b", "điều hòa"),
    (r"\bổ cắm\b", "ổ cắm"),

    (r"\b(ừm|ơ|à|ờ|hmm|uh)\b", ""),
]

class ASREngine:
    """Vietnamese speech-to-text using Sherpa-ONNX Zipformer.

    v2 features:
    - Hotwords boosting via modified_beam_search (falls back to greedy_search if unsupported)
    - Confidence scoring for low-quality transcription detection
    - Vietnamese phonetic post-correction for smart home commands
    """

    CONFIDENCE_HIGH = 0.75
    CONFIDENCE_MEDIUM = 0.50
    CONFIDENCE_LOW = 0.30

    def __init__(self):
        self.recognizer = None
        self.sample_rate = config.ASR_SAMPLE_RATE
        self._initialized = False
        self._hotwords_path = None
        self._using_beam_search = False
        self._registry = None
        self._active_hotwords = list(SMARTHOME_HOTWORDS)

    def _extract_registry_hotwords(self, registry=None) -> list:
        """Extract room, device names, and custom aliases dynamically from Device Registry."""
        words = set()
        if registry and hasattr(registry, "get_all_nodes"):
            try:
                nodes = registry.get_all_nodes()
                for nid, ninfo in nodes.items():
                    if not isinstance(ninfo, dict):
                        continue
                    room = ninfo.get("room") or ""
                    if room and room != "unknown":
                        clean_room = room.replace("_", " ").upper()
                        words.add(clean_room)

                    for ch_key in ("ch1_name", "ch2_name", "ch3_name", "rl1", "rl2", "rl3", "name", "description"):
                        val = ninfo.get(ch_key)
                        if isinstance(val, str) and val.strip():
                            clean = re.sub(r"[^\w\sÀ-ỹ]", " ", val).strip().upper()
                            if len(clean) >= 2:
                                words.add(clean)

                    for a in ninfo.get("aliases", []):
                        if isinstance(a, str) and a.strip():
                            clean = re.sub(r"[^\w\sÀ-ỹ]", " ", a.replace("_", " ")).strip().upper()
                            if len(clean) >= 2:
                                words.add(clean)

                    channels = ninfo.get("channels", {})
                    if isinstance(channels, dict):
                        for ch_id, ch in channels.items():
                            if isinstance(ch, dict):
                                for field in ("name", "fullname", "device_type"):
                                    fval = ch.get(field)
                                    if isinstance(fval, str) and fval.strip():
                                        clean = re.sub(r"[^\w\sÀ-ỹ]", " ", fval.replace("_", " ")).strip().upper()
                                        if len(clean) >= 2:
                                            words.add(clean)
                                for a in ch.get("aliases", []):
                                    if isinstance(a, str) and a.strip():
                                        clean = re.sub(r"[^\w\sÀ-ỹ]", " ", a.replace("_", " ")).strip().upper()
                                        if len(clean) >= 2:
                                            words.add(clean)
            except Exception as e:
                logger.warning(f"Error extracting registry hotwords: {e}")
        return sorted(list(words))

    def _generate_hotwords_file(self, registry=None) -> Optional[str]:
        """Generate hotwords.txt for Sherpa-ONNX modified_beam_search boosting."""
        hotwords_dir = config.ASR_MODEL_DIR
        hotwords_path = os.path.join(hotwords_dir, "hotwords.txt")
        try:
            words = list(SMARTHOME_HOTWORDS)
            dyn_words = self._extract_registry_hotwords(registry)
            for dw in dyn_words:
                if dw not in words:
                    words.append(dw)

            self._active_hotwords = list(words)
            with open(hotwords_path, "w", encoding="utf-8") as f:
                for word in words:
                    if word.strip():
                        f.write(word.strip() + "\n")
            logger.info(f"Generated hotwords.txt with {len(words)} entries ({len(dyn_words)} dynamic from registry) at {hotwords_path}")
            return hotwords_path
        except Exception as e:
            logger.warning(f"Failed to generate hotwords.txt: {e}")
            return None

    def initialize(self, registry=None) -> bool:
        self._registry = registry
        _ensure_sherpa()
        model_dir = config.ASR_MODEL_DIR

        tokens_path = self._find_file(model_dir, "tokens.txt")
        encoder_path = self._find_file(model_dir, "encoder")
        decoder_path = self._find_file(model_dir, "decoder")
        joiner_path = self._find_file(model_dir, "joiner")

        if not (tokens_path and encoder_path and decoder_path and joiner_path):
            logger.error(f"Missing transducer model files in {model_dir}")
            return False

        self._hotwords_path = self._generate_hotwords_file(registry)

        bpe_vocab_path = self._find_file(model_dir, "bpe.vocab")

        if self._hotwords_path:
            try:
                logger.info(f"Loading ASR with modified_beam_search + hotwords boosting")
                kwargs = {
                    "encoder": encoder_path,
                    "decoder": decoder_path,
                    "joiner": joiner_path,
                    "tokens": tokens_path,
                    "hotwords_file": self._hotwords_path,
                    "hotwords_score": 3.5,
                    "num_threads": config.ASR_NUM_THREADS,
                    "sample_rate": self.sample_rate,
                    "feature_dim": 80,
                    "decoding_method": "modified_beam_search",
                    "max_active_paths": 4,
                }
                if bpe_vocab_path and os.path.exists(bpe_vocab_path):
                    kwargs["modeling_unit"] = "bpe"
                    kwargs["bpe_vocab"] = bpe_vocab_path
                    logger.info(f"Using BPE vocabulary for hotwords: {bpe_vocab_path}")

                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)
                self._using_beam_search = True
                self._initialized = True
                logger.info("✅ ASR initialized: modified_beam_search + hotwords (best accuracy)")
                return True
            except Exception as e:
                logger.warning(f"modified_beam_search failed ({e}), falling back to greedy_search")

        try:
            logger.info(f"Loading ASR with greedy_search (fallback)")
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=encoder_path,
                decoder=decoder_path,
                joiner=joiner_path,
                tokens=tokens_path,
                num_threads=config.ASR_NUM_THREADS,
                sample_rate=self.sample_rate,
                feature_dim=80,
                decoding_method="greedy_search",
            )
            self._using_beam_search = False
            self._initialized = True
            logger.info("✅ ASR initialized: greedy_search (fallback, no hotwords)")
            return True
        except Exception as e:
            logger.error(f"ASR initialization failed: {e}")
            return False

    def reload_hotwords(self, registry=None) -> bool:
        """Dynamically reload hotwords when new devices/rooms are registered or aliases updated."""
        logger.info("🔄 Reloading ASR hotwords from registry...")
        ok = self.initialize(registry)
        logger.info(f"[VOCAB][STT] vocabulary updated (total active hotwords={len(self._active_hotwords)})")
        return ok

    def has_hotword(self, word: str) -> bool:
        """Check if a word/alias is present in active STT hotwords list."""
        if not word:
            return False
        clean = re.sub(r"[^\w\sÀ-ỹ]", " ", word.replace("_", " ")).strip().upper()
        return clean in self._active_hotwords or clean.lower() in [w.lower() for w in self._active_hotwords]

    def dump_active_vocabulary(self, registry=None) -> dict:
        """Diagnostic dump of active STT recognition vocabulary and hotwords."""
        if not self._active_hotwords:
            dyn = self._extract_registry_hotwords(registry)
            all_w = list(SMARTHOME_HOTWORDS)
            for w in dyn:
                if w not in all_w:
                    all_w.append(w)
            self._active_hotwords = all_w
        return {
            "initialized": self._initialized,
            "using_beam_search": self._using_beam_search,
            "hotwords_count": len(self._active_hotwords),
            "hotwords": list(self._active_hotwords),
        }

    def transcribe(self, pcm_samples, sample_rate: int = None) -> str:
        """Transcribe audio and return corrected text."""
        text, _ = self.transcribe_with_confidence(pcm_samples, sample_rate)
        return text

    def transcribe_scoped(self,pcm_samples,sample_rate,vocabulary):
        return self.transcribe_with_confidence(pcm_samples,sample_rate,vocabulary=vocabulary)

    @staticmethod
    def _known_command(text,vocabulary):
        def normalized(value):
            value=unicodedata.normalize('NFD',value.casefold().replace('đ','d'))
            return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())
        match=re.fullmatch(r'(bat|tat|turn on|turn off) (.+)',normalized(text))
        names={normalized(v) for v in vocabulary}
        if match:return match[2] in names
        from core_v1.infrared.voice import climate_intent
        intent=climate_intent(text)
        return bool(intent and intent[0] in names and ('temperature' not in intent[1] or 16<=intent[1]['temperature']<=30))

    def transcribe_with_confidence(self, pcm_samples, sample_rate: int = None, *, vocabulary=None) -> Tuple[str, float]:
        """
        Transcribe audio and return (corrected_text, confidence_score).
        confidence_score: 0.0 (garbage) to 1.0 (perfect recognition).
        Downstream can use this to decide whether to ask for clarification.
        """
        if not self._initialized or not self.recognizer:
            logger.error("ASR not initialized")
            return "", 0.0

        sr = sample_rate or self.sample_rate
        try:
            t0 = time.time()

            if isinstance(pcm_samples, (bytes, bytearray)):
                pcm_samples = np.frombuffer(pcm_samples, dtype=np.int16).astype(np.float32) / 32768.0
            elif not isinstance(pcm_samples, np.ndarray):
                pcm_samples = np.array(pcm_samples, dtype=np.float32)

            duration_s = len(pcm_samples) / sr
            rms = float(np.sqrt(np.mean(pcm_samples ** 2))) if len(pcm_samples) > 0 else 0.0

            if duration_s < 0.3 or rms < 0.005:
                logger.warning(f"Audio too short ({duration_s:.2f}s) or too quiet (RMS={rms:.4f})")
                return "", 0.0

            if self._using_beam_search and (self._registry or vocabulary is not None):
                dynamic=self._extract_registry_hotwords(self._registry) if vocabulary is None else vocabulary
                self._active_hotwords = sorted(set(SMARTHOME_HOTWORDS) | {v.upper() for v in dynamic})
                stream = self.recognizer.create_stream(hotwords="/".join(self._active_hotwords))
            else:
                stream = self.recognizer.create_stream()
            stream.accept_waveform(sr, pcm_samples)
            self.recognizer.decode_stream(stream)

            raw_text = stream.result.text.strip()
            elapsed = time.time() - t0
            logger.info(f"ASR raw ({elapsed:.2f}s): '{raw_text}'")

            if not raw_text:
                return "", 0.0

            corrected = raw_text.lower() if self._known_command(raw_text,vocabulary or ()) else self._phonetic_correct(raw_text)
            if corrected != raw_text:
                logger.info(f"ASR corrected: '{raw_text}' → '{corrected}'")

            confidence = self._estimate_confidence(corrected, raw_text, duration_s, rms, vocabulary=vocabulary or ())
            logger.info(f"ASR result: '{corrected}' (confidence={confidence:.2f}, beam={'Y' if self._using_beam_search else 'N'})")

            return corrected, confidence

        except Exception as e:
            logger.error(f"ASR transcription error: {e}")
            return "", 0.0

    def _phonetic_correct(self, text: str) -> str:
        """Apply Vietnamese phonetic corrections for smart home ASR errors."""
        result = text.lower().strip()
        for pattern, replacement in ASR_PHONETIC_CORRECTIONS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _estimate_confidence(self, corrected_text: str, raw_text: str, duration_s: float, rms: float, *, vocabulary=()) -> float:
        """
        Estimate transcription confidence using multiple heuristics:
        1. Audio quality (duration, energy)
        2. Text coherence (known keywords match)
        3. Correction distance (how much we had to fix)
        4. Text length vs audio duration ratio
        """
        score = 0.5

        if rms > 0.05:
            score += 0.1
        elif rms < 0.01:
            score -= 0.15

        if 0.5 <= duration_s <= 8.0:
            score += 0.05
        elif duration_s > 10.0:
            score -= 0.1

        smarthome_keywords = {
            "bật", "tắt", "mở", "đóng", "cài", "đặt", "chỉnh",
            "đèn", "quạt", "điều hòa", "rèm", "bơm", "máy lạnh",
            "phòng khách", "phòng ngủ", "phòng bếp", "phòng tắm",
            "ban công", "sân vườn", "hành lang",
        }
        text_lower = corrected_text.lower()
        keyword_hits = sum(1 for kw in smarthome_keywords if kw in text_lower)
        if keyword_hits >= 2 or self._known_command(corrected_text,vocabulary):
            score += 0.25
        elif keyword_hits == 1:
            score += 0.10
        else:
            score -= 0.15

        if corrected_text.lower() != raw_text.lower():

            diff_chars = sum(1 for a, b in zip(corrected_text.lower(), raw_text.lower()) if a != b)
            diff_ratio = diff_chars / max(len(raw_text), 1)
            if diff_ratio > 0.3:
                score -= 0.15
            elif diff_ratio > 0.1:
                score -= 0.05

        garbage_patterns = [
            r"^[^a-zA-ZÀ-ỹ]+$",
            r"^(.)\1{3,}",
            r"^\s*$",
        ]
        for gp in garbage_patterns:
            if re.match(gp, corrected_text):
                score -= 0.3

        words = len(corrected_text.split())
        if duration_s > 2.0 and words <= 1:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _find_file(self, base_dir: str, pattern: str) -> Optional[str]:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if pattern in f:
                    return os.path.join(root, f)
        return None
