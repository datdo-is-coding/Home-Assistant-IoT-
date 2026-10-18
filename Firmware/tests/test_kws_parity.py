"""
Unit and integration tests for KWS DSP/MFCC & Quantized Inference ported to ActionBox V2.
Verifies MFCC parameters, class index mapping against labels.json, INT8 inference
accuracy on X_test.npy, and that observation mode strictly blocks relay actuation.
"""
from pathlib import Path
import ctypes
import json
import re
import subprocess
import tempfile
import unittest
import wave
import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
ACTIONBOX_V2_SRC = HERE.parent / "firmware_esp/ActionBox_V2/src"
SUBBOX_SRC = HERE.parent / "firmware_esp/SubBox/src"
KWS_DATA = HERE.parent / "firmware_kws/data"
KWS_DATASET = HERE.parent / "firmware_kws/dataset"

class TestKwsParity(unittest.TestCase):

    def test_labels_and_mfcc_config_parity(self):
        """Verify labels.json exactly matches kws_config.h and protocol definitions."""
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

        config_h_path = ACTIONBOX_V2_SRC / "audio/kws/kws_config.h"
        self.assertTrue(config_h_path.is_file(), f"Missing {config_h_path}")
        config_text = config_h_path.read_text(encoding="utf-8")

        self.assertIn("#define SAMPLE_RATE 16000", config_text)
        self.assertIn("#define AUDIO_WINDOW_MS 1000", config_text)
        self.assertIn("#define AUDIO_STEP_MS 250", config_text)
        self.assertIn("#define TOTAL_SAMPLES (SAMPLE_RATE * AUDIO_WINDOW_MS / 1000)", config_text)
        self.assertIn("#define STEP_SAMPLES (SAMPLE_RATE * AUDIO_STEP_MS / 1000)", config_text)
        self.assertIn("#define FRAME_LEN_SAMPLES 320", config_text)
        self.assertIn("#define FRAME_STEP_SAMPLES 160", config_text)
        self.assertIn("#define FFT_SIZE 512", config_text)
        self.assertIn("#define NUM_MEL_FILTERS 32", config_text)
        self.assertIn("#define NUM_MFCC_COEFFS 13", config_text)
        self.assertIn("#define NUM_FRAMES 99", config_text)
        self.assertIn("#define NORM_MEAN (-9.295776f)", config_text)
        self.assertIn("#define NORM_STD (35.392517f)", config_text)
        self.assertIn("#define NUM_CLASSES 10", config_text)
        self.assertIn("#define CONFIDENCE_THRESHOLD 0.40f", config_text)
        self.assertIn("#define COOLDOWN_MS 500", config_text)

        enum_matches = re.findall(r"CLASS_(\w+)\s*=\s*(\d+)", config_text)
        enum_dict = {name: int(idx) for name, idx in enum_matches}
        self.assertEqual(enum_dict.get("BAT"), 0)
        self.assertEqual(enum_dict.get("BEP"), 1)
        self.assertEqual(enum_dict.get("KHACH"), 2)
        self.assertEqual(enum_dict.get("NGU"), 3)
        self.assertEqual(enum_dict.get("NOISE"), 4)
        self.assertEqual(enum_dict.get("PHONG"), 5)
        self.assertEqual(enum_dict.get("QUAT"), 6)
        self.assertEqual(enum_dict.get("TAT"), 7)
        self.assertEqual(enum_dict.get("UNKNOWN"), 8)
        self.assertEqual(enum_dict.get("DEN"), 9)

        protocol_h_path = ACTIONBOX_V2_SRC / "protocol/actionbox_protocol.h"
        proto_text = protocol_h_path.read_text(encoding="utf-8")
        self.assertRegex(proto_text, r"#define\s+MSG_TYPE_KEYWORD_EVENT\s+0x25")
        self.assertIn("ActionBoxKeywordEventPacket", proto_text)
        self.assertIn("uint8_t  msg_type;", proto_text)
        self.assertIn("uint8_t  seq;", proto_text)
        self.assertIn("uint8_t  keyword_id;", proto_text)
        self.assertIn("uint8_t  confidence_pct;", proto_text)
        self.assertIn("uint32_t session_id;", proto_text)
        self.assertIn("uint32_t rel_time_ms;", proto_text)

    def test_quantized_inference_accuracy_on_test_vectors(self):
        """Compile and evaluate kws_model_quantized.h against X_test.npy and y_test.npy."""
        x_test_path = KWS_DATA / "X_test.npy"
        y_test_path = KWS_DATA / "y_test.npy"
        self.assertTrue(x_test_path.is_file(), f"Missing {x_test_path}")
        self.assertTrue(y_test_path.is_file(), f"Missing {y_test_path}")

        X_test = np.load(str(x_test_path))
        y_test = np.load(str(y_test_path))

        with tempfile.TemporaryDirectory() as td:
            build_dir = Path(td)
            wrapper_cpp = """
#include "audio/kws/kws_config.h"
#include "audio/kws/kws_model_quantized.h"

extern "C" void run_inference(const float* mfcc_in, float* out_probs) {
    kws_run_inference_quantized(mfcc_in, out_probs);
}
"""
            (build_dir / "wrapper.cpp").write_text(wrapper_cpp)
            so_path = build_dir / "libkws_model.so"
            cmd = [
                "g++", "-O3", "-fPIC", "-shared",
                f"-I{ACTIONBOX_V2_SRC}",
                str(build_dir / "wrapper.cpp"),
                "-o", str(so_path)
            ]
            build = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, f"Compilation failed: {build.stderr}")

            lib = ctypes.CDLL(str(so_path))
            lib.run_inference.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]

            mean = -9.295776
            std = 35.392517
            X_test_norm = (X_test - mean) / std

            correct = 0
            total = len(X_test)
            per_class_total = [0] * 10
            per_class_correct = [0] * 10

            for i in range(total):
                mfcc_flat = X_test_norm[i].flatten().astype(np.float32)
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
                    c_acc = (per_class_correct[c] / per_class_total[c]) * 100.0
                    self.assertGreater(c_acc, 45.0, f"Class {c} accuracy {c_acc:.1f}% unexpectedly low")

    def test_observation_mode_blocks_relay_actuation(self):
        """Test KWS engine in observation mode: detects keywords, sends packets, strictly blocks relay actuation."""
        wav_path = KWS_DATASET / "bật/100.wav"
        self.assertTrue(wav_path.is_file(), f"Missing sample wav {wav_path}")

        with wave.open(str(wav_path), "rb") as wf:
            n_frames = wf.getnframes()
            pcm_keyword = np.frombuffer(wf.readframes(n_frames), dtype=np.int16)
        if len(pcm_keyword) < 16000:
            pcm_keyword = np.pad(pcm_keyword, (0, 16000 - len(pcm_keyword)), mode="constant")
        else:
            pcm_keyword = pcm_keyword[:16000]

        pcm_silence = np.zeros(16000, dtype=np.int16)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for header in ("esp_err.h", "esp_log.h", "esp_timer.h", "esp_attr.h",
                           "sdkconfig.h", "freertos/FreeRTOS.h", "freertos/task.h",
                           "freertos/semphr.h", "driver/gpio.h", "driver/uart.h",
                           "nvs.h", "nvs_flash.h", "esp_mac.h", "esp_random.h", "esp_task_wdt.h"):
                p = root / header
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('#include "host_idf.h"\n')

            (root / "driver/gpio.h").write_text("#pragma once\n#include \"host_idf.h\"\n" +
                "\n".join(f"constexpr int GPIO_NUM_{i} = {i};" for i in range(49)))

            pcm_kw_path = root / "keyword.raw"
            pcm_silence_path = root / "silence.raw"
            pcm_keyword.tofile(str(pcm_kw_path))
            pcm_silence.tofile(str(pcm_silence_path))

            runner_cpp = f"""
#include "host_idf.h"
#include "audio/kws/kws_engine.h"
#include "audio/kws/kws_config.h"
#include "protocol/actionbox_protocol.h"
#include "drivers/relay/relay_driver.h"
#include <cstdio>
#include <cassert>
#include <vector>

static std::vector<ActionBoxKeywordEventPacket> g_sent_packets;

extern "C" bool safety_sensor_ready(uint8_t) {{ return true; }}
esp_err_t gpio_config(const gpio_config_t*) {{ return ESP_OK; }}
esp_err_t gpio_set_level(int, uint32_t) {{ return ESP_OK; }}

extern "C" esp_err_t espnow_transport_send(const uint8_t *payload, size_t len) {{
    if (len == sizeof(ActionBoxKeywordEventPacket)) {{
        ActionBoxKeywordEventPacket pkt;
        memcpy(&pkt, payload, len);
        g_sent_packets.push_back(pkt);
    }}
    return ESP_OK;
}}

int main() {{
    // 1. Initial State: Relay driver initialized, relays OFF
    assert(relay_driver_init() == ESP_OK);
    assert(relay_get_state(1) == RELAY_STATE_OFF);
    assert(relay_get_state(2) == RELAY_STATE_OFF);

    // 2. KWS Engine Initialization: observation mode default TRUE
    assert(kws_engine_init() == ESP_OK);
    assert(kws_engine_is_observation_mode() == true);

    // 3. Feed keyword audio (bật)
    FILE* fp = fopen("{pcm_kw_path}", "rb");
    assert(fp != nullptr);
    int16_t pcm[16000];
    assert(fread(pcm, sizeof(int16_t), 16000, fp) == 16000);
    fclose(fp);

    kws_engine_feed_samples(pcm, 16000);

    int cls = -1;
    float conf = 0.0f;
    bool detected = kws_engine_step(&cls, &conf);

    printf("Step 1 (Keyword): detected=%d, cls=%d (%s), conf=%.3f, packets=%zu\\n",
           detected, cls, (cls >= 0 && cls < 10) ? KWS_LABELS[cls] : "none", conf, g_sent_packets.size());

    // Must detect keyword 'bật' (id=0) with confidence >= 0.40
    assert(detected == true);
    assert(cls == 0);
    assert(conf >= 0.40f);
    assert(g_sent_packets.size() == 1);
    assert(g_sent_packets[0].msg_type == MSG_TYPE_KEYWORD_EVENT);
    assert(g_sent_packets[0].keyword_id == 0);
    assert(g_sent_packets[0].confidence_pct >= 40);

    // CRITICAL: Relays MUST remain strictly OFF in Observation Mode!
    assert(relay_get_state(1) == RELAY_STATE_OFF);
    assert(relay_get_state(2) == RELAY_STATE_OFF);

    // 4. Test Cooldown: immediate second step must be suppressed by 500ms cooldown
    kws_engine_feed_samples(pcm, 4000);
    bool step2 = kws_engine_step(&cls, &conf);
    printf("Step 2 (Cooldown test): detected=%d, packets=%zu\\n", step2, g_sent_packets.size());
    assert(step2 == false);
    assert(g_sent_packets.size() == 1); // No duplicate packet

    // Relays still strictly OFF
    assert(relay_get_state(1) == RELAY_STATE_OFF);
    assert(relay_get_state(2) == RELAY_STATE_OFF);

    // 5. Feed silence/noise
    FILE* f_silence = fopen("{pcm_silence_path}", "rb");
    assert(f_silence != nullptr);
    assert(fread(pcm, sizeof(int16_t), 16000, f_silence) == 16000);
    fclose(f_silence);

    vTaskDelay(600); // Wait past cooldown
    kws_engine_feed_samples(pcm, 16000);
    bool step_silence = kws_engine_step(&cls, &conf);
    printf("Step 3 (Silence/Noise): detected=%d, cls=%d (%s), conf=%.3f, packets=%zu\\n",
           step_silence, cls, (cls >= 0 && cls < 10) ? KWS_LABELS[cls] : "none", conf, g_sent_packets.size());
    // Silence/noise must NOT trigger packet or relay
    assert(step_silence == false);
    assert(cls == 4 || cls == 8); // Noise or Unknown
    assert(g_sent_packets.size() == 1); // No new packet sent

    assert(relay_get_state(1) == RELAY_STATE_OFF);
    assert(relay_get_state(2) == RELAY_STATE_OFF);

    printf("ALL OBSERVATION MODE CHECKS PASSED: NO RELAY ACTUATION OCCURRED!\\n");
    return 0;
}}
"""
            (root / "runner.cpp").write_text(runner_cpp)
            includes = [ACTIONBOX_V2_SRC, *[p for p in ACTIONBOX_V2_SRC.rglob("*") if p.is_dir()], root, HERE / "actionbox_host"]
            sources = [
                ACTIONBOX_V2_SRC / "audio/kws/kws_mfcc.cpp",
                ACTIONBOX_V2_SRC / "audio/kws/kws_engine.cpp",
                ACTIONBOX_V2_SRC / "drivers/relay/relay_driver.cpp",
                ACTIONBOX_V2_SRC / "drivers/led/led_driver.cpp",
            ]
            command = ["g++", "-std=c++17", "-pthread", "-g", "-o", str(root / "runner")]
            command += [f"-I{p}" for p in includes]
            command += [str(s) for s in sources]
            command += [str(root / "runner.cpp")]

            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, f"Host runner build failed: {build.stderr}")

            run = subprocess.run([str(root / "runner")], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, f"Host runner execution failed: {run.stderr}\n{run.stdout}")
            self.assertIn("ALL OBSERVATION MODE CHECKS PASSED", run.stdout)

    def test_subbox_keyword_event_handling(self):
        """Verify SubBox ESP-NOW receiver processes and parses ActionBox keyword events."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for header in ("esp_err.h", "esp_log.h", "esp_timer.h", "esp_attr.h",
                           "sdkconfig.h", "freertos/FreeRTOS.h", "freertos/task.h",
                           "freertos/semphr.h", "nvs.h", "nvs_flash.h", "esp_mac.h", "esp_random.h"):
                p = root / header
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('#include "host_idf.h"\n')

            subbox_test_cpp = """
#include "host_idf.h"
#include "audio/audio_transport/audio_packet.h"
#include "network/espnow_receiver.h"
#include <cstdio>
#include <cassert>

int main() {
    // Construct keyword event packet for 'quạt' (id=6), confidence 88%
    ActionBoxKeywordEventPacket pkt{};
    pkt.msg_type = MSG_TYPE_KEYWORD_EVENT; // 0x25
    pkt.seq = 12;
    pkt.keyword_id = 6;
    pkt.confidence_pct = 88;
    pkt.session_id = 12345;
    pkt.rel_time_ms = 5000;

    assert(pkt.msg_type == 0x25);
    assert(sizeof(ActionBoxKeywordEventPacket) == 12);

    // Call SubBox reception handler
    subbox_espnow_handle_keyword_event(reinterpret_cast<const uint8_t*>(&pkt), sizeof(pkt));

    printf("SubBox KWS reception test passed successfully.\\n");
    return 0;
}
"""
            (root / "subbox_test.cpp").write_text(subbox_test_cpp)
            includes = [SUBBOX_SRC, *[p for p in SUBBOX_SRC.rglob("*") if p.is_dir()], root, HERE / "actionbox_host"]
            sources = [
                SUBBOX_SRC / "network/espnow_receiver.cpp",
            ]
            command = ["g++", "-std=c++17", "-pthread", "-g", "-o", str(root / "subbox_runner")]
            command += [f"-I{p}" for p in includes]
            command += [str(s) for s in sources]
            command += [str(root / "subbox_test.cpp")]

            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, f"SubBox runner build failed: {build.stderr}")

            run = subprocess.run([str(root / "subbox_runner")], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, f"SubBox runner failed: {run.stderr}\n{run.stdout}")
            self.assertIn("SubBox KWS reception test passed", run.stdout)

if __name__ == "__main__":
    unittest.main()
