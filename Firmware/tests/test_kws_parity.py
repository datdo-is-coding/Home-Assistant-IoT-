"""Parity checks for the shared Vietnamese KWS assets used by SubBox."""
import ctypes
import json
import re
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
ACTIONBOX_V2_SRC = HERE.parent / "firmware_esp/ActionBox_V2/src"
SUBBOX_SRC = HERE.parent / "firmware_esp/SubBox/src"
COMMON_KWS = HERE.parent / "firmware_esp/common/kws"
KWS_DATA = HERE / "fixtures/kws/data"
KWS_DATASET = HERE / "fixtures/kws/dataset"

SAMPLE_RATE = 16000
FRAME_LEN = 320
FRAME_STEP = 160
NUM_FRAMES = 99
NUM_FFT = 512
NUM_FILTERS = 32
NUM_CEPSTRAL = 13
NORM_MEAN = -9.295776
NORM_STD = 35.392517


def hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def mel_to_hz(mel):
    return 700.0 * (10 ** (mel / 2595.0) - 1.0)


def reference_mfcc(signal):
    """Mirror the training extractor, including its zero-only float64 epsilon."""
    signal = np.asarray(signal, dtype=np.float32)
    if signal.size < SAMPLE_RATE:
        signal = np.pad(signal, (0, SAMPLE_RATE - signal.size))
    signal = signal[:SAMPLE_RATE]

    emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])
    window = np.hamming(FRAME_LEN).astype(np.float32)
    frames = np.stack([
        emphasized[i * FRAME_STEP:i * FRAME_STEP + FRAME_LEN]
        for i in range(NUM_FRAMES)
    ])

    low_mel, high_mel = hz_to_mel(300.0), hz_to_mel(8000.0)
    mel_points = np.linspace(low_mel, high_mel, NUM_FILTERS + 2)
    bins = np.floor((NUM_FFT + 1) * mel_to_hz(mel_points) / SAMPLE_RATE).astype(int)
    filters = np.zeros((NUM_FILTERS, NUM_FFT // 2 + 1), dtype=np.float32)
    for m in range(1, NUM_FILTERS + 1):
        left, centre, right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(left, centre):
            filters[m - 1, k] = (k - left) / (centre - left)
        for k in range(centre, right):
            filters[m - 1, k] = (right - k) / (right - centre)

    spectrum = np.abs(np.fft.rfft(frames * window, NUM_FFT, axis=1)) ** 2 / NUM_FFT
    energies = spectrum @ filters.T
    energies = np.where(energies == 0, np.finfo(float).eps, energies)
    log_mel = np.log(energies)

    dct = np.zeros((NUM_CEPSTRAL, NUM_FILTERS), dtype=np.float32)
    for i in range(NUM_CEPSTRAL):
        factor = np.sqrt(1.0 / NUM_FILTERS) if i == 0 else np.sqrt(2.0 / NUM_FILTERS)
        for j in range(NUM_FILTERS):
            dct[i, j] = factor * np.cos(np.pi * i * (j + 0.5) / NUM_FILTERS)
    coeffs = log_mel @ dct.T

    lifter = 1.0 + (22.0 / 2.0) * np.sin(np.pi * np.arange(NUM_CEPSTRAL) / 22.0)
    coeffs = coeffs * lifter
    return ((coeffs - NORM_MEAN) / NORM_STD).astype(np.float32)


class TestKwsParity(unittest.TestCase):

    def test_labels_and_mfcc_config_parity(self):
        labels_json_path = KWS_DATA / "labels.json"
        self.assertTrue(labels_json_path.is_file(), f"Missing {labels_json_path}")
        with open(labels_json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        expected_classes = [
            "bật", "bếp", "khách", "ngủ", "noise",
            "phòng", "quạt", "tắt", "unknown", "đèn"
        ]
        self.assertEqual(meta["classes"], expected_classes)
        for idx, name in enumerate(expected_classes):
            self.assertEqual(meta["label_to_idx"][name], idx)
            self.assertEqual(meta["idx_to_label"][str(idx)], name)

        config_h_path = COMMON_KWS / "kws_config.h"
        self.assertTrue(config_h_path.is_file(), f"Missing {config_h_path}")
        config_text = config_h_path.read_text(encoding="utf-8")

        for definition in (
            "#define SAMPLE_RATE 16000",
            "#define AUDIO_WINDOW_MS 1000",
            "#define AUDIO_STEP_MS 250",
            "#define TOTAL_SAMPLES (SAMPLE_RATE * AUDIO_WINDOW_MS / 1000)",
            "#define STEP_SAMPLES (SAMPLE_RATE * AUDIO_STEP_MS / 1000)",
            "#define FRAME_LEN_SAMPLES 320",
            "#define FRAME_STEP_SAMPLES 160",
            "#define FFT_SIZE 512",
            "#define NUM_MEL_FILTERS 32",
            "#define NUM_MFCC_COEFFS 13",
            "#define NUM_FRAMES 99",
            "#define NORM_MEAN (-9.295776f)",
            "#define NORM_STD (35.392517f)",
            "#define NUM_CLASSES 10",
            "#define CONFIDENCE_THRESHOLD 0.40f",
            "#define COOLDOWN_MS 500",
        ):
            self.assertIn(definition, config_text)

        enum_matches = re.findall(r"CLASS_(\w+)\s*=\s*(\d+)", config_text)
        enum_dict = {name: int(idx) for name, idx in enum_matches}
        self.assertEqual(enum_dict, {
            "BAT": 0, "BEP": 1, "KHACH": 2, "NGU": 3, "NOISE": 4,
            "PHONG": 5, "QUAT": 6, "TAT": 7, "UNKNOWN": 8, "DEN": 9,
        })

    def test_active_build_has_no_actionbox_kws_engine(self):
        self.assertFalse((ACTIONBOX_V2_SRC / "audio/kws").exists(),
                         "ActionBox must not build the migrated KWS engine")
        for path in ACTIONBOX_V2_SRC.rglob("*"):
            if path.suffix not in (".c", ".cpp", ".h") or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("kws_engine", text, f"stale KWS reference in {path}")
            self.assertNotIn("kws_run_inference_quantized", text,
                             f"stale model reference in {path}")

        subbox_cmake = (SUBBOX_SRC / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertNotIn('"${CMAKE_CURRENT_SOURCE_DIR}/../../common/kws/kws_mfcc.cpp"', subbox_cmake)
        self.assertIn("common/kws", subbox_cmake)
        self.assertTrue((COMMON_KWS / "kws_mfcc.cpp").is_file())
        self.assertTrue((COMMON_KWS / "kws_model_quantized.h").is_file())

    def test_mfcc_matches_training_preprocessing(self):
        wav_path = KWS_DATASET / "bật/100.wav"
        if not wav_path.is_file():
            self.skipTest("KWS audio samples unavailable")
        with wave.open(str(wav_path), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), SAMPLE_RATE)
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw_path = root / "sample.raw"
            out_path = root / "mfcc.bin"
            runner = r'''
#include "kws_mfcc.h"
#include <cstdio>
#include <vector>
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    FILE* input = fopen(argv[1], "rb");
    if (!input) return 3;
    std::vector<int16_t> pcm(TOTAL_SAMPLES);
    if (fread(pcm.data(), sizeof(int16_t), pcm.size(), input) != pcm.size()) return 4;
    fclose(input);
    std::vector<float> audio(TOTAL_SAMPLES);
    for (int i = 0; i < TOTAL_SAMPLES; ++i) audio[i] = pcm[i] / 32768.0f;
    MFCCExtractor extractor;
    if (!extractor.init()) return 5;
    std::vector<float> mfcc(NUM_FRAMES * NUM_MFCC_COEFFS);
    extractor.extract(audio.data(), mfcc.data());
    FILE* output = fopen(argv[2], "wb");
    if (!output) return 6;
    fwrite(mfcc.data(), sizeof(float), mfcc.size(), output);
    fclose(output);
    return 0;
}
'''
            cpp = root / "runner.cpp"
            cpp.write_text(runner)
            binary = root / "runner"
            build = subprocess.run([
                "g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
                f"-I{COMMON_KWS}", str(cpp),
                str(COMMON_KWS / "kws_mfcc.cpp"), "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            cases = {
                'word': pcm,
                'silence': np.zeros(SAMPLE_RATE, dtype=np.int16),
                'quiet_pcm': np.random.default_rng(42).integers(-2, 3, SAMPLE_RATE, dtype=np.int16),
            }
            for label, samples in cases.items():
                with self.subTest(audio=label):
                    samples.tofile(str(raw_path))
                    run = subprocess.run([str(binary), str(raw_path), str(out_path)],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    actual = np.fromfile(str(out_path), dtype=np.float32).reshape(NUM_FRAMES, NUM_CEPSTRAL)
                    reference = reference_mfcc(samples.astype(np.float32) / 32768.0)
                    self.assertLess(float(np.max(np.abs(actual - reference))), 2e-3)
                    if label == 'silence':
                        self.assertLess(float(np.max(np.abs(actual[:, 0] - (-5.4982785)))), 2e-5)

    def test_quantized_inference_accuracy_on_test_vectors(self):
        x_test_path = KWS_DATA / "X_test.npy"
        y_test_path = KWS_DATA / "y_test.npy"
        self.assertTrue(x_test_path.is_file(), f"Missing {x_test_path}")
        self.assertTrue(y_test_path.is_file(), f"Missing {y_test_path}")

        X_test = np.load(str(x_test_path))
        y_test = np.load(str(y_test_path))

        with tempfile.TemporaryDirectory() as td:
            build_dir = Path(td)
            wrapper_cpp = """
#include "kws_config.h"
#include "kws_model_quantized.h"

extern "C" void run_inference(const float* mfcc_in, float* out_probs) {
    kws_run_inference_quantized(mfcc_in, out_probs);
}
"""
            (build_dir / "wrapper.cpp").write_text(wrapper_cpp)
            so_path = build_dir / "libkws_model.so"
            build = subprocess.run([
                "g++", "-O3", "-fPIC", "-shared", f"-I{COMMON_KWS}",
                str(build_dir / "wrapper.cpp"), "-o", str(so_path),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, f"Compilation failed: {build.stderr}")

            lib = ctypes.CDLL(str(so_path))
            lib.run_inference.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]

            X_test_norm = ((X_test - NORM_MEAN) / NORM_STD).astype(np.float32)
            correct = 0
            total = len(X_test_norm)
            per_class_total = [0] * 10
            per_class_correct = [0] * 10

            for i in range(total):
                mfcc_flat = X_test_norm[i].flatten()
                probs = (ctypes.c_float * 10)()
                lib.run_inference(mfcc_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), probs)
                pred = int(np.argmax(list(probs)))
                target = int(y_test[i])
                per_class_total[target] += 1
                if pred == target:
                    correct += 1
                    per_class_correct[target] += 1

            accuracy = (correct / total) * 100.0
            self.assertGreater(accuracy, 75.0, f"Accuracy {accuracy:.2f}% below 75% threshold")
            for c in range(10):
                if per_class_total[c] > 0:
                    class_accuracy = (per_class_correct[c] / per_class_total[c]) * 100.0
                    self.assertGreater(class_accuracy, 45.0,
                                       f"Class {c} accuracy {class_accuracy:.1f}% unexpectedly low")


if __name__ == "__main__":
    unittest.main()
