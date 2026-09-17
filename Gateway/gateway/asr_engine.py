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
from typing import Optional, Tuple
import numpy as np

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


# ── Smart Home Hotwords (boost ASR accuracy for IoT commands) ───────
SMARTHOME_HOTWORDS = [
    # Actions
    "BẬT", "TẮT", "MỞ", "ĐÓNG", "CÀI", "ĐẶT", "CHỈNH",
    # Devices
    "ĐÈN", "QUẠT", "ĐIỀU HÒA", "MÁY LẠNH", "RÈM", "BƠM",
    "ĐÈN NGỦ", "ĐÈN TRẦN", "QUẠT TRẦN", "BÌNH NÓNG LẠNH",
    "CỬA CUỐN", "GIÀN PHƠI", "MÁY HÚT MÙI",
    # Rooms
    "PHÒNG KHÁCH", "PHÒNG NGỦ", "PHÒNG BẾP", "PHÒNG TẮM",
    "PHÒNG LÀM VIỆC", "BAN CÔNG", "SÂN VƯỜN", "SÂN THƯỢNG",
    "HÀNH LANG", "PHÒNG THỜ", "PHÒNG VỆ SINH", "GARA",
    # Common phrases
    "BẬT ĐÈN", "TẮT ĐÈN", "BẬT QUẠT", "TẮT QUẠT",
    "BẬT ĐIỀU HÒA", "TẮT ĐIỀU HÒA", "MỞ RÈM", "ĐÓNG RÈM",
    # Numbers (for temperature)
    "ĐỘ", "MƯỜI SÁU", "MƯỜI BẢY", "MƯỜI TÁM", "HAI MƯƠI",
    "HAI LĂM", "HAI SÁU", "HAI BẢY", "HAI TÁM", "BA MƯƠI",
]

# ── Vietnamese ASR phonetic post-corrections ────────────────────────
# Common Zipformer/Whisper misrecognitions for Vietnamese smart home commands
ASR_PHONETIC_CORRECTIONS = [
    # "bật quạt" family
    (r"\bbất quá\b", "bật quạt"),
    (r"\bbật quá\b", "bật quạt"),
    (r"\bbật quà\b", "bật quạt"),
    (r"\bbật quát\b", "bật quạt"),
    (r"\bmở quá\b", "mở quạt"),
    (r"\btắt quá\b", "tắt quạt"),
    (r"\btắt quà\b", "tắt quạt"),
    # "bật đèn" family
    (r"\bbật điên\b", "bật đèn"),
    (r"\btắt điên\b", "tắt đèn"),
    (r"\bbật đền\b", "bật đèn"),
    (r"\btắt đền\b", "tắt đèn"),
    (r"\bbật đêm\b", "bật đèn"),
    (r"\btắt đêm\b", "tắt đèn"),
    (r"\bbạt đèn\b", "bật đèn"),
    (r"\bbạt đền\b", "bật đèn"),
    # "bạn bè" -> "bật đèn" (very common ASR confusion)
    (r"\bbạn bè\b", "bật đèn"),
    (r"\bbạn bè phòng\b", "bật đèn phòng"),
    # "phòng khách" family
    (r"\bphong khách\b", "phòng khách"),
    (r"\bphòng khach\b", "phòng khách"),
    (r"\bphong khach\b", "phòng khách"),
    (r"\bphong khac\b", "phòng khách"),
    # "phòng ngủ" family
    (r"\bphong ngu\b", "phòng ngủ"),
    (r"\bphòng ngu\b", "phòng ngủ"),
    (r"\bphong ngue\b", "phòng ngủ"),
    (r"\bphòng ngue\b", "phòng ngủ"),
    # "phòng bếp" family
    (r"\bphong bep\b", "phòng bếp"),
    (r"\bphòng bep\b", "phòng bếp"),
    # Device synonyms
    (r"\bquạt điện\b", "quạt"),
    (r"\bbóng đèn\b", "đèn"),
    (r"\bmáy lạnh\b", "điều hòa"),
    (r"\bmáy điều hòa\b", "điều hòa"),
    # Common garbage / noise words the ASR hallucinates
    (r"\b(ừm|ơ|à|ờ|hmm|uh)\b", ""),
]


class ASREngine:
    """Vietnamese speech-to-text using Sherpa-ONNX Zipformer.

    v2 features:
    - Hotwords boosting via modified_beam_search (falls back to greedy_search if unsupported)
    - Confidence scoring for low-quality transcription detection
    - Vietnamese phonetic post-correction for smart home commands
    """

    # Confidence thresholds
    CONFIDENCE_HIGH = 0.75      # Good recognition
    CONFIDENCE_MEDIUM = 0.50    # Acceptable but may have errors
    CONFIDENCE_LOW = 0.30       # Likely misheard, should clarify

    def __init__(self):
        self.recognizer = None
        self.sample_rate = config.ASR_SAMPLE_RATE
        self._initialized = False
        self._hotwords_path = None
        self._using_beam_search = False

    def _generate_hotwords_file(self) -> Optional[str]:
        """Generate hotwords.txt for Sherpa-ONNX modified_beam_search boosting."""
        hotwords_dir = config.ASR_MODEL_DIR
        hotwords_path = os.path.join(hotwords_dir, "hotwords.txt")
        try:
            with open(hotwords_path, "w", encoding="utf-8") as f:
                for word in SMARTHOME_HOTWORDS:
                    f.write(word.strip() + "\n")
            logger.info(f"Generated hotwords.txt with {len(SMARTHOME_HOTWORDS)} entries at {hotwords_path}")
            return hotwords_path
        except Exception as e:
            logger.warning(f"Failed to generate hotwords.txt: {e}")
            return None

    def initialize(self) -> bool:
        _ensure_sherpa()
        model_dir = config.ASR_MODEL_DIR

        tokens_path = self._find_file(model_dir, "tokens.txt")
        encoder_path = self._find_file(model_dir, "encoder")
        decoder_path = self._find_file(model_dir, "decoder")
        joiner_path = self._find_file(model_dir, "joiner")

        if not (tokens_path and encoder_path and decoder_path and joiner_path):
            logger.error(f"Missing transducer model files in {model_dir}")
            return False

        # Generate hotwords file
        self._hotwords_path = self._generate_hotwords_file()

        # Try modified_beam_search with hotwords first (better accuracy)
        if self._hotwords_path:
            try:
                logger.info(f"Loading ASR with modified_beam_search + hotwords boosting")
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=encoder_path,
                    decoder=decoder_path,
                    joiner=joiner_path,
                    tokens=tokens_path,
                    hotwords_file=self._hotwords_path,
                    hotwords_score=2.0,
                    num_threads=config.ASR_NUM_THREADS,
                    sample_rate=self.sample_rate,
                    feature_dim=80,
                    decoding_method="modified_beam_search",
                    max_active_paths=4,
                )
                self._using_beam_search = True
                self._initialized = True
                logger.info("✅ ASR initialized: modified_beam_search + hotwords (best accuracy)")
                return True
            except Exception as e:
                logger.warning(f"modified_beam_search failed ({e}), falling back to greedy_search")

        # Fallback: greedy_search (faster but no hotwords boosting)
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

    def transcribe(self, pcm_samples, sample_rate: int = None) -> str:
        """Transcribe audio and return corrected text."""
        text, _ = self.transcribe_with_confidence(pcm_samples, sample_rate)
        return text

    def transcribe_with_confidence(self, pcm_samples, sample_rate: int = None) -> Tuple[str, float]:
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

            # Check audio quality (very short or silent audio = low confidence)
            duration_s = len(pcm_samples) / sr
            rms = float(np.sqrt(np.mean(pcm_samples ** 2))) if len(pcm_samples) > 0 else 0.0

            if duration_s < 0.3 or rms < 0.005:
                logger.warning(f"Audio too short ({duration_s:.2f}s) or too quiet (RMS={rms:.4f})")
                return "", 0.0

            stream = self.recognizer.create_stream()
            stream.accept_waveform(sr, pcm_samples)
            self.recognizer.decode_stream(stream)

            raw_text = stream.result.text.strip()
            elapsed = time.time() - t0
            logger.info(f"ASR raw ({elapsed:.2f}s): '{raw_text}'")

            if not raw_text:
                return "", 0.0

            # Post-correct common Vietnamese ASR errors
            corrected = self._phonetic_correct(raw_text)
            if corrected != raw_text:
                logger.info(f"ASR corrected: '{raw_text}' → '{corrected}'")

            # Compute confidence score
            confidence = self._estimate_confidence(corrected, raw_text, duration_s, rms)
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
        # Clean up multiple spaces
        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _estimate_confidence(self, corrected_text: str, raw_text: str, duration_s: float, rms: float) -> float:
        """
        Estimate transcription confidence using multiple heuristics:
        1. Audio quality (duration, energy)
        2. Text coherence (known keywords match)
        3. Correction distance (how much we had to fix)
        4. Text length vs audio duration ratio
        """
        score = 0.5  # Base score

        # 1. Audio quality boost
        if rms > 0.05:
            score += 0.1   # Good volume
        elif rms < 0.01:
            score -= 0.15  # Very quiet

        if 0.5 <= duration_s <= 8.0:
            score += 0.05  # Normal duration
        elif duration_s > 10.0:
            score -= 0.1   # Too long (noise?)

        # 2. Smart home keyword presence boost
        smarthome_keywords = {
            "bật", "tắt", "mở", "đóng", "cài", "đặt", "chỉnh",
            "đèn", "quạt", "điều hòa", "rèm", "bơm", "máy lạnh",
            "phòng khách", "phòng ngủ", "phòng bếp", "phòng tắm",
            "ban công", "sân vườn", "hành lang",
        }
        text_lower = corrected_text.lower()
        keyword_hits = sum(1 for kw in smarthome_keywords if kw in text_lower)
        if keyword_hits >= 2:
            score += 0.25  # Strong match
        elif keyword_hits == 1:
            score += 0.10  # Partial match
        else:
            score -= 0.15  # No smart home keywords at all

        # 3. Correction penalty (had to fix a lot = less confident)
        if corrected_text.lower() != raw_text.lower():
            # Count how many corrections were applied
            diff_chars = sum(1 for a, b in zip(corrected_text.lower(), raw_text.lower()) if a != b)
            diff_ratio = diff_chars / max(len(raw_text), 1)
            if diff_ratio > 0.3:
                score -= 0.15  # Heavy correction needed
            elif diff_ratio > 0.1:
                score -= 0.05  # Some correction needed

        # 4. Suspicious patterns (common garbage outputs)
        garbage_patterns = [
            r"^[^a-zA-ZÀ-ỹ]+$",        # No letters at all
            r"^(.)\1{3,}",               # Repeated characters
            r"^\s*$",                     # Empty/whitespace
        ]
        for gp in garbage_patterns:
            if re.match(gp, corrected_text):
                score -= 0.3

        # 5. Text too short for the audio duration
        words = len(corrected_text.split())
        if duration_s > 2.0 and words <= 1:
            score -= 0.1  # Long audio but very few words

        # Clamp
        return max(0.0, min(1.0, score))

    def _find_file(self, base_dir: str, pattern: str) -> Optional[str]:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if pattern in f:
                    return os.path.join(root, f)
        return None
