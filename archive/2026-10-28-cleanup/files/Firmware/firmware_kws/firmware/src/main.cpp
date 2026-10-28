#include "kws_config.h"
#include "mfcc.h"
#include "audio_input.h"
#include <Arduino.h>

#if USE_QUANTIZED_MODEL
#include "kws_model_quantized.h"
#else
#include "kws_model.h"
#endif

static MFCCExtractor mfcc_extractor;

static float audio_buffer[TOTAL_SAMPLES];

static float mfcc_features[NUM_FRAMES * NUM_MFCC_COEFFS];

static unsigned long last_detection_time = 0;

static bool lamp_state = false;
static bool fan_state = false;

static int pending_action = -1;
static int pending_device = -1;
static unsigned long state_timeout = 0;

static void pulse_latching_relay(int set_pin, int reset_pin, bool turn_on) {
  if (turn_on) {
    digitalWrite(reset_pin, LOW);
    digitalWrite(set_pin, HIGH);
    delay(RELAY_LATCH_PULSE_MS);
    digitalWrite(set_pin, LOW);
  } else {
    digitalWrite(set_pin, LOW);
    digitalWrite(reset_pin, HIGH);
    delay(RELAY_LATCH_PULSE_MS);
    digitalWrite(reset_pin, LOW);
  }
}

void set_lamp_relay(bool turn_on) {
  lamp_state = turn_on;
  pulse_latching_relay(RELAY_1_SET_PIN, RELAY_1_RESET_PIN, turn_on);

  Serial.println("\n***************************************************");
  Serial.printf("💡 [RELAY 1 - ĐÈN (SET: IO%d, RESET: IO%d)] => %s\n",
                RELAY_1_SET_PIN, RELAY_1_RESET_PIN,
                lamp_state ? "ĐÃ BẬT (ON)" : "ĐÃ TẮT (OFF)");
  Serial.println("***************************************************\n");

  digitalWrite(LED_STATUS_PIN, HIGH);
  delay(150);
  digitalWrite(LED_STATUS_PIN, LOW);
}

void set_fan_relay(bool turn_on) {
  fan_state = turn_on;
  pulse_latching_relay(RELAY_2_SET_PIN, RELAY_2_RESET_PIN, turn_on);

  Serial.println("\n***************************************************");
  Serial.printf("🌀 [RELAY 2 - QUẠT (SET: IO%d, RESET: IO%d)] => %s\n",
                RELAY_2_SET_PIN, RELAY_2_RESET_PIN,
                fan_state ? "ĐÃ BẬT (ON)" : "ĐÃ TẮT (OFF)");
  Serial.println("***************************************************\n");

  digitalWrite(LED_STATUS_PIN, HIGH);
  delay(150);
  digitalWrite(LED_STATUS_PIN, LOW);
}

#define VAD_SLICE_MS         50
#define VAD_SLICE_SAMPLES    (SAMPLE_RATE * VAD_SLICE_MS / 1000)
#define VAD_PREROLL_SLICES   2
#define VAD_MIN_SPEECH_SAMP  (SAMPLE_RATE * 150 / 1000)
#define VAD_MAX_SPEECH_SAMP  (SAMPLE_RATE * 800 / 1000)
#define VAD_SILENCE_SLICES   2

enum VADState {
  VAD_IDLE,
  VAD_SPEAKING
};

static VADState vad_state = VAD_IDLE;
static float preroll_buf[VAD_PREROLL_SLICES * VAD_SLICE_SAMPLES];
static float slice_buf[VAD_SLICE_SAMPLES];
static int recorded_samples = 0;
static int silence_slice_count = 0;

void handle_detected_keyword(int class_id, float confidence) {
  if (class_id < 0 || class_id >= NUM_CLASSES) return;

  if (class_id == CLASS_NOISE || class_id == CLASS_UNKNOWN) {
    return;
  }

  const char *label = KWS_LABELS[class_id];
  Serial.printf("🎯 [NHẬN DIỆN] Từ khóa: '%s' (Độ tin cậy: %.1f%%)\n",
                label, confidence * 100.0f);

  if ((pending_action != -1 || pending_device != -1) && millis() > state_timeout) {
    Serial.println("  ⚠️ [TIMEOUT] Quá 5 giây chờ lệnh tiếp theo, hủy chuỗi lệnh!");
    pending_action = -1;
    pending_device = -1;
  }

  if (class_id == CLASS_BAT || class_id == CLASS_TAT) {
    pending_action = class_id;

    if (pending_device == CLASS_DEN) {
      bool turn_on = (pending_action == CLASS_BAT);
      set_lamp_relay(turn_on);
      pending_action = -1;
      pending_device = -1;
      return;
    } else if (pending_device == CLASS_QUAT) {
      bool turn_on = (pending_action == CLASS_BAT);
      set_fan_relay(turn_on);
      pending_action = -1;
      pending_device = -1;
      return;
    }

    state_timeout = millis() + 5000;
    Serial.printf("  👉 [BƯỚC 1: HÀNH ĐỘNG] '%s' => Đang chờ nói tên thiết bị ('đèn' hoặc 'quạt')...\n",
                  label);
  }

  else if (class_id == CLASS_DEN || class_id == CLASS_QUAT) {
    pending_device = class_id;

    if (pending_action == CLASS_BAT || pending_action == CLASS_TAT) {
      bool turn_on = (pending_action == CLASS_BAT);
      if (pending_device == CLASS_DEN) {
        set_lamp_relay(turn_on);
      } else {
        set_fan_relay(turn_on);
      }
      pending_action = -1;
      pending_device = -1;
      return;
    }

    state_timeout = millis() + 5000;
    Serial.printf("  👉 [BƯỚC 1: THIẾT BỊ] '%s' => Đang chờ nói hành động ('bật' hoặc 'tắt')...\n",
                  label);
  }

  else if (class_id == CLASS_KHACH || class_id == CLASS_BEP || class_id == CLASS_NGU) {
    Serial.printf("  🏠 [KHU VỰC] Phòng %s.\n", label);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=======================================================");
  Serial.println("  ESP32-S3 KEYWORD SPOTTING (KWS) - VOICE RELAY CONTROL");
  Serial.println("=======================================================");
#if USE_QUANTIZED_MODEL
  Serial.printf(">> CẤU HÌNH MÔ HÌNH: [INT8 QUANTIZED] (3,776 bytes weights - Tiết kiệm 75%% Flash)\n");
#else
  Serial.printf(">> CẤU HÌNH MÔ HÌNH: [FLOAT32 GỐC] (15,104 bytes weights - ESP32-S3 FPU Hardware)\n");
#endif

  // Cấu hình các chân Relay Latching ActionBox V2 (Dual-Coil)
  pinMode(RELAY_1_SET_PIN, OUTPUT);
  pinMode(RELAY_1_RESET_PIN, OUTPUT);
  pinMode(RELAY_2_SET_PIN, OUTPUT);
  pinMode(RELAY_2_RESET_PIN, OUTPUT);
  pinMode(RELAY_3_SET_PIN, OUTPUT);
  pinMode(RELAY_3_RESET_PIN, OUTPUT);

  // Đảm bảo ban đầu các chân kích cuộn hút đều ở mức LOW
  digitalWrite(RELAY_1_SET_PIN, LOW);
  digitalWrite(RELAY_1_RESET_PIN, LOW);
  digitalWrite(RELAY_2_SET_PIN, LOW);
  digitalWrite(RELAY_2_RESET_PIN, LOW);
  digitalWrite(RELAY_3_SET_PIN, LOW);
  digitalWrite(RELAY_3_RESET_PIN, LOW);

  // Ban đầu kích xung RESET để đảm bảo trạng thái an toàn (TẮT) sau khởi động
  pulse_latching_relay(RELAY_1_SET_PIN, RELAY_1_RESET_PIN, false);
  pulse_latching_relay(RELAY_2_SET_PIN, RELAY_2_RESET_PIN, false);
  pulse_latching_relay(RELAY_3_SET_PIN, RELAY_3_RESET_PIN, false);

  // Tắt phần cứng amplifier MAX98357 (IO38 -> LOW) để tránh sôi loa và tiết kiệm điện
  pinMode(SPEAKER_SD_PIN, OUTPUT);
  digitalWrite(SPEAKER_SD_PIN, LOW);

  // Cấu hình LED chỉ báo trạng thái (ActionBox V2: LED 2 / Voice LED - IO2)
  pinMode(LED_STATUS_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, LOW);

  Serial.println("\n[CẤU HÌNH PHẦN CỨNG THEO ACTIONBOX V2]");
  Serial.printf("  🎙️ Mic INMP441 : BCLK=IO%d, WS=IO%d, DIN=IO%d\n",
                MIC_I2S_GPIO_BCLK, MIC_I2S_GPIO_WS, MIC_I2S_GPIO_DIN);
  Serial.printf("  🔇 Speaker SD   : IO%d (Disabled/LOW)\n", SPEAKER_SD_PIN);
  Serial.printf("  💡 Relay 1 (ĐÈN): SET=IO%d, RESET=IO%d (Xung %dms)\n",
                RELAY_1_SET_PIN, RELAY_1_RESET_PIN, RELAY_LATCH_PULSE_MS);
  Serial.printf("  🌀 Relay 2 (QUẠT): SET=IO%d, RESET=IO%d (Xung %dms)\n",
                RELAY_2_SET_PIN, RELAY_2_RESET_PIN, RELAY_LATCH_PULSE_MS);
  Serial.printf("  🔌 Relay 3      : SET=IO%d, RESET=IO%d (Xung %dms)\n",
                RELAY_3_SET_PIN, RELAY_3_RESET_PIN, RELAY_LATCH_PULSE_MS);
  Serial.printf("  🔴 LED Voice    : IO%d\n", LED_STATUS_PIN);

  memset(audio_buffer, 0, sizeof(audio_buffer));
  memset(preroll_buf, 0, sizeof(preroll_buf));

  if (!mfcc_extractor.init()) {
    Serial.println("[ERROR] Lỗi khởi tạo MFCC extractor!");
    while (1)
      delay(100);
  }
  Serial.println("[OK] Khối trích xuất MFCC sẵn sàng.");

  if (audio_input_init() != ESP_OK) {
    Serial.println("[ERROR] Lỗi khởi tạo micro, dừng hệ thống!");
    while (1)
      delay(100);
  }

  Serial.println("\n[SẴN SÀNG LẮNG NGHE LỆNH GIỌNG NÓI - VAD TÁCH ÂM TIẾT]");
  Serial.printf("👉 Nói liền mạch: 'BẬT' ... 'ĐÈN'  => Đóng Relay 1 (Xung SET IO%d)\n", RELAY_1_SET_PIN);
  Serial.printf("👉 Nói liền mạch: 'TẮT' ... 'ĐÈN'  => Ngắt Relay 1 (Xung RESET IO%d)\n", RELAY_1_RESET_PIN);
  Serial.printf("👉 Nói liền mạch: 'BẬT' ... 'QUẠT' => Đóng Relay 2 (Xung SET IO%d)\n", RELAY_2_SET_PIN);
  Serial.printf("👉 Nói liền mạch: 'TẮT' ... 'QUẠT' => Ngắt Relay 2 (Xung RESET IO%d)\n\n", RELAY_2_RESET_PIN);
}

void loop() {

  float slice_rms = 0.0f;
  audio_input_read_clean(slice_buf, VAD_SLICE_SAMPLES, &slice_rms);

  float ambient = audio_input_get_ambient_rms();
  float speech_thresh = ambient * 2.2f + 0.006f;
  float silence_thresh = ambient * 1.3f + 0.002f;

  static unsigned long last_listen_report = 0;

  if (vad_state == VAD_IDLE) {

    memmove(&preroll_buf[0], &preroll_buf[VAD_SLICE_SAMPLES], VAD_SLICE_SAMPLES * sizeof(float));
    memcpy(&preroll_buf[VAD_SLICE_SAMPLES], slice_buf, VAD_SLICE_SAMPLES * sizeof(float));

    if (millis() - last_listen_report >= 2000) {
      last_listen_report = millis();
      Serial.printf("[ESP32-S3] 🎙️ Đang lắng nghe... (RMS: %.4f | Ồn nền: %.4f)\n", slice_rms, ambient);
    }

    if (slice_rms >= speech_thresh) {
      vad_state = VAD_SPEAKING;
      recorded_samples = 0;
      silence_slice_count = 0;

      memcpy(&audio_buffer[0], preroll_buf, sizeof(preroll_buf));
      recorded_samples += VAD_PREROLL_SLICES * VAD_SLICE_SAMPLES;

      memcpy(&audio_buffer[recorded_samples], slice_buf, VAD_SLICE_SAMPLES * sizeof(float));
      recorded_samples += VAD_SLICE_SAMPLES;

      Serial.printf("\n⚡ [BẮT ĐẦU TỪ] RMS: %.4f (Ngưỡng nói: %.4f)\n", slice_rms, speech_thresh);
    }
  } else if (vad_state == VAD_SPEAKING) {

    if (recorded_samples + VAD_SLICE_SAMPLES <= VAD_MAX_SPEECH_SAMP) {
      memcpy(&audio_buffer[recorded_samples], slice_buf, VAD_SLICE_SAMPLES * sizeof(float));
      recorded_samples += VAD_SLICE_SAMPLES;
    }

    if (slice_rms < silence_thresh) {
      silence_slice_count++;
    } else {
      silence_slice_count = 0;
    }

    bool is_word_ended = (silence_slice_count >= VAD_SILENCE_SLICES) ||
                         (recorded_samples >= VAD_MAX_SPEECH_SAMP);

    if (is_word_ended) {
      int duration_ms = (recorded_samples * 1000) / SAMPLE_RATE;
      Serial.printf("🛑 [KẾT THÚC TỪ] Thời lượng: %d ms (%d mẫu)\n", duration_ms, recorded_samples);

      if (recorded_samples >= VAD_MIN_SPEECH_SAMP) {

        int pad_total = TOTAL_SAMPLES - recorded_samples;
        int pad_front = pad_total / 2;

        memmove(&audio_buffer[pad_front], &audio_buffer[0], recorded_samples * sizeof(float));
        memset(&audio_buffer[0], 0, pad_front * sizeof(float));
        memset(&audio_buffer[pad_front + recorded_samples], 0, (TOTAL_SAMPLES - pad_front - recorded_samples) * sizeof(float));

        mfcc_extractor.extract(audio_buffer, mfcc_features);

        unsigned long t_start = millis();
        float probs[NUM_CLASSES];
#if USE_QUANTIZED_MODEL
        kws_run_inference_quantized(mfcc_features, probs);
#else
        kws_run_inference(mfcc_features, probs);
#endif
        unsigned long infer_duration = millis() - t_start;

        int top_class = 0;
        float top_prob = probs[0];
        for (int i = 1; i < NUM_CLASSES; i++) {
          if (probs[i] > top_prob) {
            top_prob = probs[i];
            top_class = i;
          }
        }

        int second_class = (top_class == 0) ? 1 : 0;
        for (int i = 0; i < NUM_CLASSES; i++) {
          if (i != top_class && probs[i] > probs[second_class]) {
            second_class = i;
          }
        }

        Serial.println("---------------------------------------------------");
        Serial.printf("🎯 [KẾT QUẢ TÁCH ÂM TIẾT] (%d ms âm | Suy luận: %lu ms)\n", duration_ms, infer_duration);
        Serial.printf("   👉 Dự đoán: '%s' | Độ tin cậy: %.1f%%\n", KWS_LABELS[top_class], top_prob * 100.0f);
        Serial.printf("   👉 Xếp thứ 2: '%s' | Độ tin cậy: %.1f%%\n", KWS_LABELS[second_class], probs[second_class] * 100.0f);
        Serial.println("---------------------------------------------------");

        if (top_prob >= CONFIDENCE_THRESHOLD) {
          handle_detected_keyword(top_class, top_prob);
        } else {
          Serial.printf("   ⚠️ [BỎ QUA] Độ tin cậy (%.1f%%) < Ngưỡng kích hoạt (%.0f%%)\n\n",
                        top_prob * 100.0f, CONFIDENCE_THRESHOLD * 100.0f);
        }
      } else {
        Serial.printf("   ⚠️ [BỎ QUA] Âm quá ngắn (< 150ms), bỏ qua tạp âm ngắn!\n\n");
      }

      vad_state = VAD_IDLE;
      memset(preroll_buf, 0, sizeof(preroll_buf));
      last_listen_report = millis();
    }
  }

  if (Serial.available()) {
    String test_cmd = Serial.readStringUntil('\n');
    test_cmd.trim();
    if (test_cmd == "bat den" || test_cmd == "1") {
      set_lamp_relay(true);
    } else if (test_cmd == "tat den" || test_cmd == "2") {
      set_lamp_relay(false);
    } else if (test_cmd == "bat quat" || test_cmd == "3") {
      set_fan_relay(true);
    } else if (test_cmd == "tat quat" || test_cmd == "4") {
      set_fan_relay(false);
    } else if (test_cmd == "bat") {
      handle_detected_keyword(CLASS_BAT, 0.95f);
    } else if (test_cmd == "tat") {
      handle_detected_keyword(CLASS_TAT, 0.95f);
    } else if (test_cmd == "den") {
      handle_detected_keyword(CLASS_DEN, 0.95f);
    } else if (test_cmd == "quat") {
      handle_detected_keyword(CLASS_QUAT, 0.95f);
    }
  }
}
