#include "voice_capture.h"
#include "board_pins.h"
#include "actionbox_protocol.h"
#include "espnow_transport.h"
#include "led_driver.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <atomic>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"

#include "esp_wn_iface.h"
#include "esp_wn_models.h"
#include "model_path.h"

static const char *TAG = "VOICE_CAP";

#define AUDIO_SAMPLE_RATE          16000
#define AUDIO_BITS_PER_SAMPLE      16
#define AUDIO_DMA_FRAME_SAMPLES    240
#define CHUNK_SAMPLES              (ESPNOW_AUDIO_MAX_PCM_BYTES / sizeof(int16_t))

#define VAD_PREROLL_CHUNKS         14
#define VAD_SILENCE_END_CHUNKS     106
#define VAD_MIN_SPEECH_CHUNKS      14
#define VAD_MAX_STREAM_CHUNKS      666
#define VAD_COOLDOWN_CHUNKS        266
#define WAKE_TAIL_SKIP_CHUNKS      26

static std::atomic<int64_t> s_wake_session_us{0};
static std::atomic<bool> s_followup_requested{false};
static bool s_followup_stream = false;
#define WN_MODEL_PARTITION         "model"

static const esp_wn_iface_t *s_wn = NULL;
static model_iface_data_t   *s_wn_data = NULL;
static int                   s_wn_chunk = 0;

static i2s_chan_handle_t s_rx_handle = NULL;
static std::atomic<bool> s_session_active{false};
static std::atomic<int64_t> s_session_deadline{0};
static std::atomic<bool> s_word_streaming{false};
static std::atomic<bool> s_is_streaming{false};
static uint8_t           s_trigger_source = 0;

static int16_t s_preroll_chunks[VAD_PREROLL_CHUNKS][CHUNK_SAMPLES];
static size_t  s_preroll_count = 0;
static size_t  s_preroll_head = 0;

static uint8_t  s_audio_seq = 0;
static uint16_t s_stream_chunks = 0;
static uint32_t s_stream_bytes = 0;
static uint32_t s_word_speech_chunks = 0;
static uint32_t s_word_silence_chunks = 0;
static uint32_t s_word_total_chunks = 0;
static uint32_t s_cooldown_frames = 0;
static uint32_t s_wake_tail_frames = 0;

static float s_latest_rms = 0.0f;
static bool  s_latest_speech = false;

static int32_t s_dc_offset = 0;

static inline int16_t remove_dc(int16_t in) {
    s_dc_offset += ((int32_t)in - (s_dc_offset >> 7));
    int32_t ac = (int32_t)in - (s_dc_offset >> 7);
    if (ac > 32767) ac = 32767;
    if (ac < -32768) ac = -32768;
    return (int16_t)ac;
}

typedef struct {
    float b0, b1, b2;
    float a1, a2;
    float x1, x2;
    float y1, y2;
} biquad_t;

static inline void biquad_init(biquad_t *f, float b0, float b1, float b2, float a1, float a2) {
    f->b0 = b0; f->b1 = b1; f->b2 = b2;
    f->a1 = a1; f->a2 = a2;
    f->x1 = 0.0f; f->x2 = 0.0f; f->y1 = 0.0f; f->y2 = 0.0f;
}

static inline float biquad_step(biquad_t *f, float in) {
    float out = f->b0 * in + f->b1 * f->x1 + f->b2 * f->x2 - f->a1 * f->y1 - f->a2 * f->y2;
    f->x2 = f->x1;
    f->x1 = in;
    f->y2 = f->y1;
    f->y1 = out;
    return out;
}

static biquad_t s_hpf1, s_hpf2;
static biquad_t s_lpf1, s_lpf2;

static float s_ambient_rms = 0.005f;
static float s_gate_threshold = 0.010f;
static float s_gate_env = 0.0f;
static float s_gate_gain = 0.0f;

static esp_err_t init_i2s_mic(void);
static void init_wakenet(void);
static void voice_capture_task(void *pvParameters);

esp_err_t voice_capture_init(void) {
    ESP_LOGI(TAG, "Initializing voice capture (INMP441 + WakeNet + ESP-NOW)...");

    esp_err_t err = init_i2s_mic();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize I2S microphone: %s", esp_err_to_name(err));
        return err;
    }

    init_wakenet();

    biquad_init(&s_hpf1, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_hpf2, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_lpf1, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);
    biquad_init(&s_lpf2, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);

    s_ambient_rms = 0.005f;
    s_gate_threshold = 0.010f;
    s_gate_env = 0.0f;
    s_gate_gain = 0.0f;
    s_session_active.store(false);
    s_session_deadline.store(0);
    s_word_streaming.store(false);
    s_is_streaming.store(false);
    s_preroll_count = 0;
    s_preroll_head = 0;
    memset(s_preroll_chunks, 0, sizeof(s_preroll_chunks));

    if (xTaskCreatePinnedToCore(voice_capture_task, "voice_capture", 8 * 1024, NULL, 6, NULL, 1) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGW(TAG, "═══════════════════════════════════════════════════════════");
    ESP_LOGW(TAG, "  Wake word: %s", s_wn_data ? "\"Hi ESP\" (WakeNet9)" : "DISABLED (model not found)");
    ESP_LOGW(TAG, "  Push-to-talk: Hold button for 1.2s for manual trigger");
    ESP_LOGW(TAG, "═══════════════════════════════════════════════════════════");
    return ESP_OK;
}

bool voice_capture_is_streaming(void) {
    return s_session_active.load() || s_is_streaming.load();
}

bool voice_capture_request_followup(void) {
    const int64_t started = s_wake_session_us.load();
    if (!started || esp_timer_get_time() - started > 60000000LL) return false;
    s_session_deadline.store(esp_timer_get_time() + 5000000LL);
    if (s_session_active.load()) {
        return true;
    }
    s_followup_requested.store(true);
    return true;
}

void voice_capture_start_streaming(uint8_t trigger_source) {
    static std::atomic<bool> s_starting{false};
    if (s_session_active.load() || s_starting.exchange(true)) {
        s_session_deadline.store(esp_timer_get_time() + 5000000LL);
        return;
    }
    s_followup_stream = trigger_source == WAKE_TRIGGER_FOLLOWUP;
    if (!s_followup_stream) s_wake_session_us.store(esp_timer_get_time());

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "🎙️ [VOICE CAPTURE] Command listening session started! Trigger: %s (Source: %u)",
             trigger_source == WAKE_TRIGGER_HIESP ? "Wake word 'Hi ESP'" :
             trigger_source == WAKE_TRIGGER_BUTTON ? "Button / Manual" : "Follow-up",
             trigger_source);
    ESP_LOGI(TAG, "===============================================================");

    s_trigger_source = trigger_source;
    s_wake_tail_frames = (trigger_source == WAKE_TRIGGER_HIESP) ? WAKE_TAIL_SKIP_CHUNKS : 0;
    s_word_streaming.store(false);
    s_preroll_count = 0;
    s_preroll_head = 0;
    s_session_deadline.store(esp_timer_get_time() + 5000000LL);
    led_set_pattern(2, LED_PATTERN_ON);
    s_session_active.store(true);
    // Announce wake before VAD so the user can hear when to speak.
    if (!s_followup_stream) {
        const ActionBoxAudioWakePacket wake = {
            MSG_TYPE_AUDIO_WAKE, trigger_source,
            static_cast<uint32_t>(esp_timer_get_time() / 1000)
        };
        for (int retry = 0; retry < 2; ++retry) {
            espnow_transport_send(reinterpret_cast<const uint8_t*>(&wake), sizeof(wake));
            if (retry == 0) vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
    s_starting.store(false);
}

void voice_capture_stop_streaming(void) {
    if (!s_session_active.load() && !s_word_streaming.load()) return;

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "🛑 [VOICE CAPTURE] Streaming stopped (Chunks: %u, Bytes: %lu)",
             s_stream_chunks, (unsigned long)s_stream_bytes);
    ESP_LOGI(TAG, "===============================================================");

    if (s_word_streaming.load()) {
        ActionBoxAudioEndPacket end_pkt = {};
        end_pkt.msg_type = MSG_TYPE_AUDIO_END;
        end_pkt.seq = s_audio_seq;
        end_pkt.total_chunks = s_stream_chunks;
        end_pkt.total_pcm_bytes = s_stream_bytes;

        for (int retry = 0; retry < 3; ++retry) {
            espnow_transport_send((const uint8_t *)&end_pkt, sizeof(end_pkt));
            if (retry + 1 < 3) vTaskDelay(pdMS_TO_TICKS(10));
        }
    }

    s_word_streaming.store(false);
    s_session_active.store(false);
    s_is_streaming.store(false);
    led_set_pattern(2, LED_PATTERN_OFF);
    s_cooldown_frames = VAD_COOLDOWN_CHUNKS;
}

void voice_capture_set_vad_threshold(int64_t energy_threshold) {

    (void)energy_threshold;
}

void voice_capture_get_diagnostics(float *out_rms, bool *out_is_speech) {
    if (out_rms) *out_rms = s_latest_rms;
    if (out_is_speech) *out_is_speech = s_latest_speech;
}

static void init_wakenet(void) {
    srmodel_list_t *models = esp_srmodel_init(WN_MODEL_PARTITION);
    char *wn_name = models ? esp_srmodel_filter(models, ESP_WN_PREFIX, "hiesp") : NULL;
    if (!wn_name) {
        ESP_LOGE(TAG, "WakeNet 'hiesp' not found in '%s' partition (flash srmodels.bin)", WN_MODEL_PARTITION);
        return;
    }

    s_wn = esp_wn_handle_from_name(wn_name);
    s_wn_data = s_wn ? s_wn->create(wn_name, DET_MODE_90) : NULL;
    if (!s_wn_data) {
        ESP_LOGE(TAG, "WakeNet create failed for %s", wn_name);
        return;
    }
    s_wn_chunk = s_wn->get_samp_chunksize(s_wn_data);
    ESP_LOGI(TAG, "WakeNet loaded: %s (chunk=%d samples @ %d Hz)",
             wn_name, s_wn_chunk, s_wn->get_samp_rate(s_wn_data));
}

static esp_err_t init_i2s_mic(void) {
    ESP_LOGI(TAG, "Configuring I2S0 Master RX for INMP441...");

    i2s_chan_config_t chan_cfg = {
        .id = BOARD_MIC_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = AUDIO_DMA_FRAME_SAMPLES,
        .auto_clear = true,
    };
    esp_err_t ret = i2s_new_channel(&chan_cfg, NULL, &s_rx_handle);
    if (ret != ESP_OK) return ret;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = BOARD_PIN_MIC_BCLK,
            .ws   = BOARD_PIN_MIC_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = BOARD_PIN_MIC_DIN,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    ret = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (ret != ESP_OK) return ret;

    gpio_set_pull_mode(BOARD_PIN_MIC_DIN, GPIO_PULLDOWN_ONLY);

    return i2s_channel_enable(s_rx_handle);
}

static void voice_capture_task(void *pvParameters) {
    ESP_LOGI(TAG, "Voice Capture task started on Core 1 (WakeNet).");

    const size_t raw_buf_samples = AUDIO_DMA_FRAME_SAMPLES * 2;
    int32_t *raw_buf = (int32_t *)malloc(raw_buf_samples * sizeof(int32_t));
    int16_t *clean_buf = (int16_t *)malloc(AUDIO_DMA_FRAME_SAMPLES * sizeof(int16_t));
    int16_t *wn_buf = s_wn_data ? (int16_t *)malloc(s_wn_chunk * sizeof(int16_t)) : NULL;
    int16_t chunk_buf[CHUNK_SAMPLES];
    int chunk_idx = 0;
    int wn_idx = 0;

    if (!raw_buf || !clean_buf || (s_wn_data && !wn_buf)) {
        ESP_LOGE(TAG, "Capture: buffer allocation failed!");
        free(raw_buf);
        free(clean_buf);
        free(wn_buf);
        vTaskDelete(NULL);
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(300));

    uint32_t diagnostic_counter = 0;

    while (1) {
        if (s_followup_requested.exchange(false)) {
            s_cooldown_frames = 0;
            voice_capture_start_streaming(WAKE_TRIGGER_FOLLOWUP);
        }
        size_t bytes_read = 0;
        esp_err_t res = i2s_channel_read(
            s_rx_handle, raw_buf,
            raw_buf_samples * sizeof(int32_t),
            &bytes_read, pdMS_TO_TICKS(100)
        );

        if (res != ESP_OK || bytes_read == 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        int samples_read = bytes_read / sizeof(int32_t);
        int mono_samples = samples_read / 2;
        if (mono_samples > AUDIO_DMA_FRAME_SAMPLES) mono_samples = AUDIO_DMA_FRAME_SAMPLES;

        for (int i = 0; i < mono_samples; i++) {
            int32_t left_raw  = raw_buf[i * 2];
            int32_t right_raw = raw_buf[i * 2 + 1];
            auto to_i16 = [](int32_t raw) -> int16_t {
                int32_t val = raw >> 14;
                if (val > 32767) val = 32767;
                if (val < -32768) val = -32768;
                return (int16_t)val;
            };
            int16_t l16 = to_i16(left_raw);
            int16_t r16 = to_i16(right_raw);
            int16_t raw_s = (abs(left_raw) >= abs(right_raw)) ? l16 : r16;

            int16_t dc_free = remove_dc(raw_s);

            if (wn_buf && !s_session_active.load()) {
                wn_buf[wn_idx++] = dc_free;
                if (wn_idx >= s_wn_chunk) {
                    wn_idx = 0;
                    if (s_wn->detect(s_wn_data, wn_buf) == WAKENET_DETECTED && s_cooldown_frames == 0) {
                        ESP_LOGI(TAG, "Wake word 'Hi ESP' detected!");
                        voice_capture_start_streaming(WAKE_TRIGGER_HIESP);
                    }
                }
            }

            float in_sample = (float)dc_free / 32768.0f;
            float s = biquad_step(&s_hpf1, in_sample);
            s = biquad_step(&s_hpf2, s);
            s = biquad_step(&s_lpf1, s);
            s = biquad_step(&s_lpf2, s);

            float abs_s = fabsf(s);
            if (abs_s > s_gate_env) {
                s_gate_env += 0.04f * (abs_s - s_gate_env);
            } else {
                s_gate_env += 0.001f * (abs_s - s_gate_env);
            }

            float target_gain = 0.0f;
            if (s_gate_env > s_gate_threshold * 1.5f) {
                target_gain = 1.0f;
            } else if (s_gate_env > s_gate_threshold) {
                target_gain = (s_gate_env - s_gate_threshold) / (0.5f * s_gate_threshold);
            } else {
                target_gain = 0.0f;
            }
            s_gate_gain += 0.02f * (target_gain - s_gate_gain);

            float clean = s * s_gate_gain;
            if (clean > 1.0f)  clean = 1.0f;
            if (clean < -1.0f) clean = -1.0f;
            clean_buf[i] = (int16_t)(clean * 32767.0f);
        }

        // Command recognition runs on SubBox; synchronous KWS here overruns the DMA buffer.

        for (int i = 0; i < mono_samples; i++) {
            chunk_buf[chunk_idx++] = clean_buf[i];

            if (chunk_idx >= CHUNK_SAMPLES) {
                int64_t sum_sq = 0;
                for (int k = 0; k < CHUNK_SAMPLES; k++) {
                    int32_t val = chunk_buf[k];
                    sum_sq += (int64_t)val * val;
                }
                float chunk_energy = (float)sum_sq / (float)CHUNK_SAMPLES;
                float chunk_rms_val = sqrtf(chunk_energy) / 32768.0f;
                s_latest_rms = chunk_rms_val;

                float speech_thresh = s_ambient_rms * 2.2f + 0.006f;
                float silence_thresh = s_ambient_rms * 1.3f + 0.002f;

                s_latest_speech = (chunk_rms_val >= speech_thresh);

                if (++diagnostic_counter % 400 == 0) {
                    ESP_LOGI(TAG, "Capture VAD: Session=%d | WordStream=%d | RMS=%.4f | Ambient=%.4f | SpeechThresh=%.4f",
                             s_session_active.load() ? 1 : 0, s_word_streaming.load() ? 1 : 0,
                             s_latest_rms, s_ambient_rms, speech_thresh);
                }

                if (!s_session_active.load()) {
                    if (chunk_rms_val < 0.05f) {
                        s_ambient_rms = 0.995f * s_ambient_rms + 0.005f * chunk_rms_val;
                        s_gate_threshold = s_ambient_rms * 1.8f;
                        if (s_gate_threshold < 0.003f) s_gate_threshold = 0.003f;
                        if (s_gate_threshold > 0.035f) s_gate_threshold = 0.035f;
                    }
                    if (s_cooldown_frames > 0) s_cooldown_frames--;
                } else {
                    if (s_wake_tail_frames > 0) {
                        --s_wake_tail_frames;
                        chunk_idx = 0;
                        continue;
                    }

                    if (!s_word_streaming.load()) {
                        if (esp_timer_get_time() > s_session_deadline.load()) {
                            ESP_LOGI(TAG, "⏰ [SESSION TIMEOUT] Hết thời gian chờ lệnh giọng nói");
                            s_session_active.store(false);
                            s_is_streaming.store(false);
                            led_set_pattern(2, LED_PATTERN_OFF);
                            s_cooldown_frames = VAD_COOLDOWN_CHUNKS;
                            chunk_idx = 0;
                            continue;
                        }

                        memcpy(s_preroll_chunks[s_preroll_head], chunk_buf, sizeof(chunk_buf));
                        s_preroll_head = (s_preroll_head + 1) % VAD_PREROLL_CHUNKS;
                        if (s_preroll_count < VAD_PREROLL_CHUNKS) {
                            s_preroll_count++;
                        }

                        if (chunk_rms_val < silence_thresh) {
                            s_ambient_rms = 0.995f * s_ambient_rms + 0.005f * chunk_rms_val;
                            s_gate_threshold = s_ambient_rms * 1.8f;
                            if (s_gate_threshold < 0.003f) s_gate_threshold = 0.003f;
                            if (s_gate_threshold > 0.035f) s_gate_threshold = 0.035f;
                            speech_thresh = s_ambient_rms * 2.2f + 0.006f;
                            silence_thresh = s_ambient_rms * 1.3f + 0.002f;
                        }

                        // CƠ CHẾ SO SÁNH:
                        if (chunk_rms_val >= speech_thresh) {
                            s_word_streaming.store(true);
                            s_is_streaming.store(true);
                            s_word_speech_chunks = 1;
                            s_word_silence_chunks = 0;
                            s_word_total_chunks = 0;
                            s_stream_chunks = 0;
                            s_stream_bytes = 0;
                            s_audio_seq = 0;

                            ESP_LOGI(TAG, "⚡ [BẮT ĐẦU CẮT TỪ] RMS: %.4f >= Ngưỡng nói: %.4f (Ồn nền: %.4f)",
                                     chunk_rms_val, speech_thresh, s_ambient_rms);

                            ActionBoxAudioStartPacket start_pkt = {};
                            start_pkt.msg_type = MSG_TYPE_AUDIO_START;
                            start_pkt.seq = s_audio_seq;
                            start_pkt.sample_rate = AUDIO_SAMPLE_RATE;
                            start_pkt.bits_per_sample = AUDIO_BITS_PER_SAMPLE;
                            start_pkt.channels = 1;
                            start_pkt.wake_word_index = s_trigger_source;
                            start_pkt.codec = CODEC_RAW_PCM;
                            start_pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

                            for (int retry = 0; retry < 2; ++retry) {
                                espnow_transport_send((const uint8_t *)&start_pkt, sizeof(start_pkt));
                                if (retry + 1 < 2) vTaskDelay(pdMS_TO_TICKS(10));
                            }

                            size_t start_idx = (s_preroll_head + VAD_PREROLL_CHUNKS - s_preroll_count) % VAD_PREROLL_CHUNKS;
                            for (size_t k = 0; k < s_preroll_count; k++) {
                                size_t idx = (start_idx + k) % VAD_PREROLL_CHUNKS;
                                ActionBoxAudioChunkPacket chunk_pkt = {};
                                chunk_pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
                                chunk_pkt.seq = ++s_audio_seq;
                                chunk_pkt.pcm_len = sizeof(chunk_buf);
                                memcpy(chunk_pkt.pcm_data, s_preroll_chunks[idx], sizeof(chunk_buf));
                                espnow_transport_send((const uint8_t *)&chunk_pkt, 4 + sizeof(chunk_buf));
                                s_stream_chunks++;
                                s_stream_bytes += sizeof(chunk_buf);
                                s_word_total_chunks++;
                            }
                        }
                    } else {
                        // While s_word_streaming:
                        ActionBoxAudioChunkPacket chunk_pkt = {};
                        chunk_pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
                        chunk_pkt.seq = ++s_audio_seq;
                        chunk_pkt.pcm_len = sizeof(chunk_buf);
                        memcpy(chunk_pkt.pcm_data, chunk_buf, sizeof(chunk_buf));
                        espnow_transport_send((const uint8_t *)&chunk_pkt, 4 + sizeof(chunk_buf));
                        s_stream_chunks++;
                        s_stream_bytes += sizeof(chunk_buf);
                        s_word_total_chunks++;

                        if (chunk_rms_val >= silence_thresh) {
                            s_word_speech_chunks++;
                            s_word_silence_chunks = 0;
                        } else {
                            s_word_silence_chunks++;
                        }

                        bool silence_ended = (s_word_speech_chunks >= VAD_MIN_SPEECH_CHUNKS &&
                                              s_word_silence_chunks >= VAD_SILENCE_END_CHUNKS);
                        bool max_dur_ended = (s_word_total_chunks >= VAD_MAX_STREAM_CHUNKS);

                        if (silence_ended || max_dur_ended) {
                            ESP_LOGI(TAG, "🛑 [UTTERANCE END] %s: Thời lượng %lu ms (%u chunks)",
                                     silence_ended ? "Khoảng lặng kết thúc" : "Đạt độ dài tối đa",
                                     (unsigned long)((s_word_total_chunks * 120 * 1000) / AUDIO_SAMPLE_RATE),
                                     s_stream_chunks);

                            ActionBoxAudioEndPacket end_pkt = {};
                            end_pkt.msg_type = MSG_TYPE_AUDIO_END;
                            end_pkt.seq = s_audio_seq;
                            end_pkt.total_chunks = s_stream_chunks;
                            end_pkt.total_pcm_bytes = s_stream_bytes;

                            for (int retry = 0; retry < 3; ++retry) {
                                espnow_transport_send((const uint8_t *)&end_pkt, sizeof(end_pkt));
                                if (retry + 1 < 3) vTaskDelay(pdMS_TO_TICKS(10));
                            }

                            s_word_streaming.store(false);
                            s_is_streaming.store(false);
                            s_preroll_count = 0;
                            s_preroll_head = 0;
                            s_session_active.store(false);
                            s_session_deadline.store(0);
                            s_cooldown_frames = VAD_COOLDOWN_CHUNKS;
                            led_set_pattern(2, LED_PATTERN_OFF);
                        }
                    }
                }

                chunk_idx = 0;
            }
        }
    }

    free(raw_buf);
    free(clean_buf);
    free(wn_buf);
    vTaskDelete(NULL);
}
