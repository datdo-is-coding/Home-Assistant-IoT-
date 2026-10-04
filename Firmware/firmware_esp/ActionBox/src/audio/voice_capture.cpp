/**
 * @file voice_capture.cpp
 * @brief PCM microphone capture and transport; voice recognition runs on Pi4
 *
 * INMP441 -> DC removal -> WakeNet "Hi ESP" -> bandpassed PCM -> SubBox -> Pi4.
 * No local ASR/commands. Long-press button also triggers capture.
 */

#include "voice_capture.h"
#include "board_pins.h"
#include "actionbox_protocol.h"
#include "espnow_transport.h"
#include "led_driver.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

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

/* ─── Audio Configuration Constants ───────────────────────────────────── */
#define AUDIO_SAMPLE_RATE          16000
#define AUDIO_BITS_PER_SAMPLE      16
#define AUDIO_DMA_FRAME_SAMPLES    240
#define CHUNK_SAMPLES              (ESPNOW_AUDIO_MAX_PCM_BYTES / sizeof(int16_t)) /* 120 samples = 7.5ms */

/* ─── Streaming / VAD Timing Constants ───────────────────────────────── */
#define VAD_SILENCE_END_CHUNKS     106     /* 106 chunks * 7.5ms = ~800ms silence to conclude utterance */
#define VAD_MAX_STREAM_CHUNKS      666     /* 666 chunks * 7.5ms = ~5.0s maximum stream duration */
#define VAD_MIN_SPEECH_CHUNKS      25      /* Speech chunks (~187ms) required before silence timeout armed */
#define VAD_NO_SPEECH_CHUNKS       400     /* 400 chunks * 7.5ms = 3.0s: give up if no command after wake */
#define VAD_COOLDOWN_CHUNKS        266     /* 266 chunks * 7.5ms = 2.0s cooldown deadzone after streaming */
#define CAPTURE_VAD_SILENCE_ENERGY 500000LL  /* Below this mean-square energy a chunk counts as silence */

/* ─── WakeNet ─────────────────────────────────────────────────────────── */
#define WAKE_TRIGGER_HIESP         0       /* AUDIO_START.wake_word_index for "Hi ESP" */
#define WN_MODEL_PARTITION         "model"

static const esp_wn_iface_t *s_wn = NULL;
static model_iface_data_t   *s_wn_data = NULL;
static int                   s_wn_chunk = 0;   /* samples per detect() call (512 for wn9) */

/* ─── Driver State ────────────────────────────────────────────────────── */
static i2s_chan_handle_t s_rx_handle = NULL;
static volatile bool s_is_streaming = false;

static uint8_t  s_audio_seq = 0;
static uint16_t s_stream_chunks = 0;
static uint32_t s_stream_bytes = 0;
static uint32_t s_stream_frames = 0;
static uint32_t s_silence_frames = 0;
static uint32_t s_speech_frames = 0;
static uint32_t s_cooldown_frames = 0;

static float s_latest_rms = 0.0f;
static bool  s_latest_speech = false;

/* ─── DC Removal Filter ──────────────────────────────────────────────── */
static int32_t s_dc_offset = 0;

static inline int16_t remove_dc(int16_t in) {
    s_dc_offset += ((int32_t)in - (s_dc_offset >> 7));
    int32_t ac = (int32_t)in - (s_dc_offset >> 7);
    if (ac > 32767) ac = 32767;
    if (ac < -32768) ac = -32768;
    return (int16_t)ac;
}

/* ─── Biquad Filter (used only in PCM capture mode) ─────────────────────── */
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

/* ─── Forward Declarations ───────────────────────────────────────────── */
static esp_err_t init_i2s_mic(void);
static void init_wakenet(void);
static void voice_capture_task(void *pvParameters);

/* ========================================================================= */
/*                         PUBLIC API IMPLEMENTATION                         */
/* ========================================================================= */

esp_err_t voice_capture_init(void) {
    ESP_LOGI(TAG, "Initializing voice capture (INMP441 + WakeNet + ESP-NOW)...");

    /* 1. Initialize I2S peripheral for INMP441 */
    esp_err_t err = init_i2s_mic();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize I2S microphone: %s", esp_err_to_name(err));
        return err;
    }

    /* 2. Load WakeNet from the "model" partition (non-fatal: push-to-talk still works) */
    init_wakenet();

    /* Bandpass filter for streamed PCM + silence detection */
    biquad_init(&s_hpf1, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_hpf2, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_lpf1, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);
    biquad_init(&s_lpf2, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);

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
    return s_is_streaming;
}

void voice_capture_start_streaming(uint8_t trigger_source) {
    if (s_is_streaming) return;

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "🎙️ [VOICE CAPTURE] Streaming started! Trigger: %s (Source: %u)",
             trigger_source == WAKE_TRIGGER_HIESP ? "Wake word 'Hi ESP'" : "Button / Manual",
             trigger_source);
    ESP_LOGI(TAG, "===============================================================");

    s_audio_seq = 0;
    s_stream_chunks = 0;
    s_stream_bytes = 0;
    s_stream_frames = 0;
    s_silence_frames = 0;
    s_speech_frames = 0;
    s_is_streaming = true;

    /* Turn ON Voice Activity LED (LED2 / GPIO 47) */
    led_set_pattern(2, LED_PATTERN_ON);

    /* Send MSG_TYPE_AUDIO_START over ESP-NOW to SubBox (burst for reliability) */
    ActionBoxAudioStartPacket start_pkt = {};
    start_pkt.msg_type = MSG_TYPE_AUDIO_START;
    start_pkt.seq = s_audio_seq;
    start_pkt.sample_rate = AUDIO_SAMPLE_RATE;
    start_pkt.bits_per_sample = AUDIO_BITS_PER_SAMPLE;
    start_pkt.channels = 1;
    start_pkt.wake_word_index = trigger_source;
    start_pkt.codec = CODEC_RAW_PCM;
    start_pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

    for (int retry = 0; retry < 2; ++retry) {
        espnow_transport_send((const uint8_t *)&start_pkt, sizeof(start_pkt));
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

void voice_capture_stop_streaming(void) {
    if (!s_is_streaming) return;

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "🛑 [VOICE CAPTURE] Streaming stopped (Chunks: %u, Bytes: %lu)",
             s_stream_chunks, (unsigned long)s_stream_bytes);
    ESP_LOGI(TAG, "===============================================================");

    s_is_streaming = false;

    /* Enforce 2.0s cooldown guard */
    s_cooldown_frames = VAD_COOLDOWN_CHUNKS;

    /* Turn OFF Voice Activity LED (LED2 / GPIO 47) */
    led_set_pattern(2, LED_PATTERN_OFF);

    /* Send MSG_TYPE_AUDIO_END over ESP-NOW to SubBox (burst 3x for reliability) */
    ActionBoxAudioEndPacket end_pkt = {};
    end_pkt.msg_type = MSG_TYPE_AUDIO_END;
    end_pkt.seq = s_audio_seq;
    end_pkt.total_chunks = s_stream_chunks;
    end_pkt.total_pcm_bytes = s_stream_bytes;

    for (int retry = 0; retry < 3; ++retry) {
        espnow_transport_send((const uint8_t *)&end_pkt, sizeof(end_pkt));
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

void voice_capture_set_vad_threshold(int64_t energy_threshold) {
    /* Triggering is done by WakeNet; silence uses CAPTURE_VAD_SILENCE_ENERGY. */
    (void)energy_threshold;
}

void voice_capture_get_diagnostics(float *out_rms, bool *out_is_speech) {
    if (out_rms) *out_rms = s_latest_rms;
    if (out_is_speech) *out_is_speech = s_latest_speech;
}

/* ========================================================================= */
/*                         INTERNAL IMPLEMENTATIONS                          */
/* ========================================================================= */

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

    /* Pull down DIN to prevent floating noise during slot transitions */
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

        /* Convert -> DC removal -> (WakeNet) -> bandpass filter */
        for (int i = 0; i < mono_samples; i++) {
            int32_t left_raw  = raw_buf[i * 2];
            int32_t right_raw = raw_buf[i * 2 + 1];
            int16_t l16 = (int16_t)(left_raw >> 14);
            int16_t r16 = (int16_t)(right_raw >> 14);
            int16_t raw_s = (abs(left_raw) >= abs(right_raw)) ? l16 : r16;

            int16_t dc_free = remove_dc(raw_s);

            /* WakeNet wants unfiltered 16 kHz mono; skip while streaming to save CPU */
            if (wn_buf && !s_is_streaming) {
                wn_buf[wn_idx++] = dc_free;
                if (wn_idx >= s_wn_chunk) {
                    wn_idx = 0;
                    if (s_wn->detect(s_wn_data, wn_buf) == WAKENET_DETECTED && s_cooldown_frames == 0) {
                        ESP_LOGI(TAG, "Wake word 'Hi ESP' detected!");
                        voice_capture_start_streaming(WAKE_TRIGGER_HIESP);
                    }
                }
            }

            float s = (float)dc_free;
            float filtered = biquad_step(&s_hpf1, s);
            filtered = biquad_step(&s_hpf2, filtered);
            filtered = biquad_step(&s_lpf1, filtered);
            filtered = biquad_step(&s_lpf2, filtered);

            if (filtered > 32767.0f)  filtered = 32767.0f;
            if (filtered < -32768.0f) filtered = -32768.0f;
            clean_buf[i] = (int16_t)filtered;
        }

        /* Process into chunks */
        for (int i = 0; i < mono_samples; i++) {
            chunk_buf[chunk_idx++] = clean_buf[i];

            if (chunk_idx >= CHUNK_SAMPLES) {
                int64_t sum_sq = 0;
                for (int k = 0; k < CHUNK_SAMPLES; k++) {
                    int32_t val = chunk_buf[k];
                    sum_sq += (int64_t)val * val;
                }
                int64_t energy = sum_sq / CHUNK_SAMPLES;
                s_latest_rms = sqrtf((float)energy);

                if (++diagnostic_counter % 400 == 0) {
                    ESP_LOGI(TAG, "Capture VAD: Stream=%d | RMS=%.0f | Energy=%lld | Cooldown=%lu",
                             s_is_streaming, s_latest_rms, (long long)energy, (unsigned long)s_cooldown_frames);
                }

                s_latest_speech = (energy >= CAPTURE_VAD_SILENCE_ENERGY);

                if (!s_is_streaming) {
                    if (s_cooldown_frames > 0) s_cooldown_frames--;
                } else {
                    /* Streaming — send chunk + check silence */
                    ActionBoxAudioChunkPacket chunk_pkt = {};
                    chunk_pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
                    chunk_pkt.seq = ++s_audio_seq;
                    chunk_pkt.pcm_len = sizeof(chunk_buf);
                    memcpy(chunk_pkt.pcm_data, chunk_buf, sizeof(chunk_buf));
                    espnow_transport_send((const uint8_t *)&chunk_pkt, 4 + sizeof(chunk_buf));
                    s_stream_chunks++;
                    s_stream_bytes += sizeof(chunk_buf);
                    s_stream_frames++;

                    if (s_latest_speech) {
                        s_speech_frames++;
                        s_silence_frames = 0;
                    } else {
                        s_silence_frames++;
                    }

                    /* After the wake word the user may pause; arm silence end only once the command is heard */
                    bool silence_end = (s_speech_frames >= VAD_MIN_SPEECH_CHUNKS) &&
                                       (s_silence_frames >= VAD_SILENCE_END_CHUNKS);
                    bool no_speech = (s_speech_frames < VAD_MIN_SPEECH_CHUNKS) &&
                                     (s_stream_frames >= VAD_NO_SPEECH_CHUNKS);
                    bool max_dur = (s_stream_frames >= VAD_MAX_STREAM_CHUNKS);

                    if (silence_end || no_speech || max_dur) {
                        ESP_LOGI(TAG, "Capture end: %s (%.2fs, %u chunks)",
                                 silence_end ? "Silence" : (no_speech ? "NoSpeech" : "MaxDuration"),
                                 (float)s_stream_frames * 0.0075f, s_stream_chunks);
                        voice_capture_stop_streaming();
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
