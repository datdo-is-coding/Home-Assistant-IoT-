"""
ASR Engine — Sherpa-ONNX Vietnamese speech recognition.
Converts PCM audio to Vietnamese text using Zipformer Transducer.
"""

import logging
import os
from typing import Optional
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


class ASREngine:
    """Vietnamese speech-to-text using Sherpa-ONNX Zipformer."""
    
    def __init__(self):
        self.recognizer = None
        self.sample_rate = config.ASR_SAMPLE_RATE
        self._initialized = False
    
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
        
        try:
            logger.info(f"Loading Zipformer Transducer ASR model from {model_dir}")
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
            self._initialized = True
            logger.info("✅ Sherpa-ONNX Vietnamese ASR engine initialized")
            return True
        except Exception as e:
            logger.error(f"ASR initialization failed: {e}")
            return False
    
    def transcribe(self, pcm_samples, sample_rate: int = None) -> str:
        if not self._initialized or not self.recognizer:
            logger.error("ASR not initialized")
            return ""
        
        sr = sample_rate or self.sample_rate
        try:
            if isinstance(pcm_samples, (bytes, bytearray)):
                pcm_samples = np.frombuffer(pcm_samples, dtype=np.int16).astype(np.float32) / 32768.0
            elif not isinstance(pcm_samples, np.ndarray):
                pcm_samples = np.array(pcm_samples, dtype=np.float32)
                
            stream = self.recognizer.create_stream()
            stream.accept_waveform(sr, pcm_samples)
            self.recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            logger.info(f"ASR result: '{text}'")
            return text
        except Exception as e:
            logger.error(f"ASR transcription error: {e}")
            return ""
    
    def _find_file(self, base_dir: str, pattern: str) -> Optional[str]:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if pattern in f:
                    return os.path.join(root, f)
        return None
