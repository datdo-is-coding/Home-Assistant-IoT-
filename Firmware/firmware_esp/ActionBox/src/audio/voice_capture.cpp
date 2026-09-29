/**
 * @file voice_capture.cpp
 * @brief Voice Capture, WakeNet ("Hi ESP") & VAD Streaming Engine Implementation
 *
 * Audio pipeline:
 *   INMP441 I2S Mic → DC Removal → ESP-SR AFE (AGC + NS + WakeNet)
 *   → Wake Word "Hi ESP" Detected → Stream 16kHz 16-bit PCM via ESP-NOW to SubBox
 *   → Neural VAD / Max Duration → Audio End Packet
 *
 * Fallback (no model):
 *   INMP441 → Bandpass Filter → Energy VAD → Stream to SubBox
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

/* ESP-SR headers */
#include "esp_afe_sr_models.h"
#include "esp_afe_sr_iface.h"
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
#define VAD_MIN_SPEECH_CHUNKS      25      /* Minimum speech chunks (~187ms) before silence timeout armed */
#define VAD_COOLDOWN_CHUNKS        266     /* 266 chunks * 7.5ms = 2.0s cooldown deadzone after streaming */

/* ─── Energy VAD Fallback Constants (used when WakeNet unavailable) ──── */
#define FALLBACK_VAD_ENERGY_THRESH 2000000LL  /* Onset energy threshold for fallback mode */
#define FALLBACK_VAD_SILENCE_ENERGY 500000LL  /* Silence energy threshold for fallback mode */
#define FALLBACK_VAD_ONSET_CHUNKS  5          /* 5 chunks * 7.5ms = 37.5ms sustained speech */

/* ─── Driver State ────────────────────────────────────────────────────── */
static i2s_chan_handle_t s_rx_handle = NULL;
static volatile bool s_is_streaming = false;
static bool s_wakenet_active = false;     /* True if ESP-SR AFE+WakeNet initialized OK */

static uint8_t  s_audio_seq = 0;
static uint16_t s_stream_chunks = 0;
static uint32_t s_stream_bytes = 0;
static uint32_t s_stream_frames = 0;
static uint32_t s_silence_frames = 0;
static uint32_t s_cooldown_frames = 0;

static float s_latest_rms = 0.0f;
static bool  s_latest_speech = false;

/* ─── ESP-SR AFE State ────────────────────────────────────────────────── */
static const esp_afe_sr_iface_t *s_afe_iface = &ESP_AFE_SR_HANDLE;
static esp_afe_sr_data_t *s_afe_data = NULL;

/* ─── DC Removal Filter ──────────────────────────────────────────────── */
static int32_t s_dc_offset = 0;

static inline int16_t remove_dc(int16_t in) {
    s_dc_offset += ((int32_t)in - (s_dc_offset >> 7));
    int32_t ac = (int32_t)in - (s_dc_offset >> 7);
    if (ac > 32767) ac = 32767;
    if (ac < -32768) ac = -32768;
    return (int16_t)ac;
}

/* ─── Biquad Filter (used only in fallback mode) ─────────────────────── */
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
static void audio_feed_task(void *pvParameters);
static void audio_detect_task(void *pvParameters);
static void voice_capture_fallback_task(void *pvParameters);

/* ========================================================================= */
/*                         PUBLIC API IMPLEMENTATION                         */
/* ========================================================================= */

esp_err_t voice_capture_init(void) {
    ESP_LOGI(TAG, "Initializing Voice Capture Subsystem (INMP441 + WakeNet + ESP-NOW)...");

    /* 1. Initialize I2S peripheral for INMP441 */
    esp_err_t err = init_i2s_mic();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize I2S microphone: %s", esp_err_to_name(err));
        return err;
    }

    /* 2. Attempt to load WakeNet model from "model" partition */
    ESP_LOGI(TAG, "Loading speech models from 'model' partition (0x610000)...");
    srmodel_list_t *models = esp_srmodel_init("model");

    if (!models || models->num <= 0) {
        ESP_LOGW(TAG, "No speech models found in 'model' partition (num=%d). Falling back to energy VAD.",
                 models ? models->num : -1);
        goto fallback_mode;
    }

    ESP_LOGI(TAG, "Loaded %d speech model(s) from flash:", models->num);
    for (int i = 0; i < models->num; i++) {
        ESP_LOGI(TAG, "  [%d] Model: '%s'", i, models->model_name[i]);
    }

    /* Find "hiesp" WakeNet model */
    {
        char *wn_name = esp_srmodel_filter(models, ESP_WN_PREFIX, "hiesp");
        if (!wn_name) {
            wn_name = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
        }
        if (!wn_name) {
            ESP_LOGW(TAG, "No WakeNet model found among loaded models. Falling back to energy VAD.");
            goto fallback_mode;
        }
        ESP_LOGI(TAG, "Selected WakeNet model: '%s'", wn_name);

        /* 3. Configure ESP-SR Audio Front-End (AFE) for 1-MIC without PSRAM */
        afe_config_t afe_config = AFE_CONFIG_DEFAULT();
        afe_config.aec_init = false;        /* No echo cancellation (speaker disabled) */
        afe_config.se_init = false;         /* Disable neural NS to save SRAM (no PSRAM) */
        afe_config.vad_init = true;         /* Enable VAD */
        afe_config.wakenet_init = true;     /* Enable WakeNet */
        afe_config.wakenet_model_name = wn_name;
        afe_config.wakenet_mode = DET_MODE_90;  /* 1-MIC detection mode */
        afe_config.afe_mode = SR_MODE_LOW_COST;
        afe_config.memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_PSRAM;   /* Use embedded 8MB PSRAM */
        afe_config.afe_ringbuf_size = 10;   /* Smaller ringbuf to save memory */
        afe_config.afe_linear_gain = 1.0f;

        afe_config.pcm_config.total_ch_num = 1;
        afe_config.pcm_config.mic_num = 1;
        afe_config.pcm_config.ref_num = 0;
        afe_config.pcm_config.sample_rate = AUDIO_SAMPLE_RATE;

        ESP_LOGI(TAG, "AFE config: 1-MIC, SR_MODE_LOW_COST, INTERNAL SRAM, aec=OFF, se=OFF, vad=ON, wakenet=ON");
        ESP_LOGI(TAG, "Heap BEFORE AFE create: Free=%u KB, Largest=%u KB",
                 (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
                 (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL) / 1024));

        s_afe_data = s_afe_iface->create_from_config(&afe_config);
        if (!s_afe_data) {
            ESP_LOGE(TAG, "Failed to create ESP-SR AFE! Insufficient SRAM. Falling back to energy VAD.");
            goto fallback_mode;
        }

        ESP_LOGI(TAG, "Heap AFTER AFE create: Free=%u KB, Largest=%u KB",
                 (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
                 (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL) / 1024));

        s_wakenet_active = true;

        /* 4. Launch Feed + Detect tasks */
        xTaskCreatePinnedToCore(audio_feed_task,   "afe_feed",   8 * 1024, NULL, 5, NULL, 0);
        xTaskCreatePinnedToCore(audio_detect_task, "afe_detect", 8 * 1024, NULL, 6, NULL, 1);

        ESP_LOGI(TAG, "═══════════════════════════════════════════════════════════");
        ESP_LOGI(TAG, "  WakeNet ACTIVE: Listening for 'Hi ESP' wake word...");
        ESP_LOGI(TAG, "  Push-to-talk: Hold button for 1.2s for manual trigger");
        ESP_LOGI(TAG, "═══════════════════════════════════════════════════════════");
    }
    return ESP_OK;

fallback_mode:
    /* Initialize bandpass filter for fallback energy VAD */
    biquad_init(&s_hpf1, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_hpf2, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_lpf1, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);
    biquad_init(&s_lpf2, 0.2271180f,  0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);

    xTaskCreatePinnedToCore(voice_capture_fallback_task, "voice_capture", 6 * 1024, NULL, 6, NULL, 1);

    ESP_LOGW(TAG, "═══════════════════════════════════════════════════════════");
    ESP_LOGW(TAG, "  WakeNet UNAVAILABLE: Using energy-based VAD fallback");
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
             trigger_source == 0 ? "WakeNet 'Hi ESP'" :
             trigger_source == 1 ? "VAD Speech Onset" : "Button / Manual",
             trigger_source);
    ESP_LOGI(TAG, "===============================================================");

    s_audio_seq = 0;
    s_stream_chunks = 0;
    s_stream_bytes = 0;
    s_stream_frames = 0;
    s_silence_frames = 0;
    s_is_streaming = true;

    /* Turn ON Voice Activity LED (LED2 / GPIO 47) */
    led_set_pattern(2, LED_PATTERN_ON);

    /* Send MSG_TYPE_AUDIO_START over ESP-NOW to SubBox */
    ActionBoxAudioStartPacket start_pkt = {};
    start_pkt.msg_type = MSG_TYPE_AUDIO_START;
    start_pkt.seq = s_audio_seq;
    start_pkt.sample_rate = AUDIO_SAMPLE_RATE;
    start_pkt.bits_per_sample = AUDIO_BITS_PER_SAMPLE;
    start_pkt.channels = 1;
    start_pkt.wake_word_index = trigger_source;
    start_pkt.codec = CODEC_RAW_PCM;
    start_pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

    espnow_transport_send((const uint8_t *)&start_pkt, sizeof(start_pkt));
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

    /* Send MSG_TYPE_AUDIO_END over ESP-NOW to SubBox */
    ActionBoxAudioEndPacket end_pkt = {};
    end_pkt.msg_type = MSG_TYPE_AUDIO_END;
    end_pkt.seq = s_audio_seq;
    end_pkt.total_chunks = s_stream_chunks;
    end_pkt.total_pcm_bytes = s_stream_bytes;

    espnow_transport_send((const uint8_t *)&end_pkt, sizeof(end_pkt));
}

void voice_capture_set_vad_threshold(int64_t energy_threshold) {
    /* No-op when WakeNet is active; threshold only applies to fallback mode */
    (void)energy_threshold;
}

void voice_capture_get_diagnostics(float *out_rms, bool *out_is_speech) {
    if (out_rms) *out_rms = s_latest_rms;
    if (out_is_speech) *out_is_speech = s_latest_speech;
}

/* ========================================================================= */
/*                         INTERNAL IMPLEMENTATIONS                          */
/* ========================================================================= */

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

/* ─── Stream a chunk of PCM audio to SubBox via ESP-NOW ──────────────── */
static void stream_chunk_to_subbox(const int16_t *samples, int num_samples) {
    if (!s_is_streaming) return;

    /* Buffer to accumulate 120-sample ESP-NOW chunks */
    static int16_t chunk_buf[CHUNK_SAMPLES];
    static int chunk_idx = 0;

    for (int i = 0; i < num_samples; i++) {
        chunk_buf[chunk_idx++] = samples[i];

        if (chunk_idx >= CHUNK_SAMPLES) {
            /* Full chunk ready — send over ESP-NOW */
            ActionBoxAudioChunkPacket chunk_pkt = {};
            chunk_pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
            chunk_pkt.seq = ++s_audio_seq;
            chunk_pkt.pcm_len = sizeof(chunk_buf);
            memcpy(chunk_pkt.pcm_data, chunk_buf, sizeof(chunk_buf));

            espnow_transport_send((const uint8_t *)&chunk_pkt, 4 + sizeof(chunk_buf));

            s_stream_chunks++;
            s_stream_bytes += sizeof(chunk_buf);
            s_stream_frames++;

            /* Energy-based silence detection for stream end */
            int64_t sum_sq = 0;
            for (int k = 0; k < CHUNK_SAMPLES; k++) {
                int32_t val = chunk_buf[k];
                sum_sq += (int64_t)val * val;
            }
            int64_t energy = sum_sq / CHUNK_SAMPLES;
            s_latest_rms = sqrtf((float)energy);

            if (energy < FALLBACK_VAD_SILENCE_ENERGY) {
                s_silence_frames++;
            } else {
                s_silence_frames = 0;
            }

            chunk_idx = 0;

            /* Check end conditions */
            bool silence_detected = (s_stream_frames >= VAD_MIN_SPEECH_CHUNKS) &&
                                   (s_silence_frames >= VAD_SILENCE_END_CHUNKS);
            bool max_duration_reached = (s_stream_frames >= VAD_MAX_STREAM_CHUNKS);

            if (silence_detected || max_duration_reached) {
                ESP_LOGI(TAG, "End of speech: %s (Duration: %.2fs, Chunks: %u, Silence: %u)",
                         silence_detected ? "800ms Silence Detected" : "5.0s Max Duration",
                         (float)s_stream_frames * 0.0075f,
                         s_stream_chunks,
                         (unsigned)s_silence_frames);

                voice_capture_stop_streaming();
                chunk_idx = 0;
                break;
            }
        }
    }
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*                    WakeNet Mode: Feed + Detect Tasks                      */
/* ═══════════════════════════════════════════════════════════════════════════ */

/**
 * @brief Audio Feed Task — reads I2S, converts to 16-bit mono, feeds into ESP-SR AFE
 * Runs on Core 0, Priority 5
 */
static void audio_feed_task(void *pvParameters) {
    int audio_chunksize = s_afe_iface->get_feed_chunksize(s_afe_data);
    int nch = s_afe_iface->get_channel_num(s_afe_data);
    int total_ch = s_afe_iface->get_total_channel_num(s_afe_data);
    int feed_size = audio_chunksize * total_ch;

    ESP_LOGI(TAG, "AFE Feed task started (chunksize=%d, channels=%d, total_ch=%d, feed_size=%d)",
             audio_chunksize, nch, total_ch, feed_size);

    /* Allocate buffers in internal SRAM (no PSRAM) */
    int raw_buff_size = audio_chunksize * 2 * sizeof(int32_t);  /* stereo 32-bit */
    int32_t *raw_buff = (int32_t *)malloc(raw_buff_size);
    int16_t *i2s_buff = (int16_t *)malloc(feed_size * sizeof(int16_t));

    if (!raw_buff || !i2s_buff) {
        ESP_LOGE(TAG, "AFE feed: buffer allocation failed!");
        if (raw_buff) free(raw_buff);
        if (i2s_buff) free(i2s_buff);
        vTaskDelete(NULL);
        return;
    }

    /* Wait for mic DC bias and PLL to settle */
    vTaskDelay(pdMS_TO_TICKS(500));

    while (1) {
        size_t bytes_read = 0;
        esp_err_t ret = i2s_channel_read(
            s_rx_handle,
            raw_buff,
            raw_buff_size,
            &bytes_read,
            pdMS_TO_TICKS(100)
        );

        if (ret != ESP_OK || bytes_read == 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        int samples_read = bytes_read / sizeof(int32_t);
        int mono_samples = samples_read / 2;
        if (mono_samples > audio_chunksize) mono_samples = audio_chunksize;

        /* Convert 32-bit I2S slot samples to 16-bit mono + DC removal */
        for (int i = 0; i < mono_samples; i++) {
            int32_t left_raw  = raw_buff[i * 2];
            int32_t right_raw = raw_buff[i * 2 + 1];

            int16_t l16 = (int16_t)(left_raw >> 14);
            int16_t r16 = (int16_t)(right_raw >> 14);

            /* Auto-select active channel (INMP441 outputs on one channel only) */
            int16_t raw_s = (abs(left_raw) >= abs(right_raw)) ? l16 : r16;
            i2s_buff[i] = remove_dc(raw_s);
        }

        /* Zero-pad if we got fewer samples than expected */
        for (int i = mono_samples; i < feed_size; i++) {
            i2s_buff[i] = 0;
        }

        /* Feed into AFE engine — this drives WakeNet detection internally */
        s_afe_iface->feed(s_afe_data, i2s_buff);
    }

    free(raw_buff);
    free(i2s_buff);
    vTaskDelete(NULL);
}

/**
 * @brief Audio Detect Task — fetches AFE results, handles wake word + streaming
 * Runs on Core 1, Priority 6 (higher than feed to prevent buffer overflow)
 */
static void audio_detect_task(void *pvParameters) {
    int afe_chunksize = s_afe_iface->get_fetch_chunksize(s_afe_data);
    ESP_LOGI(TAG, "AFE Detect task started (fetch chunksize=%d samples)", afe_chunksize);

    int neural_silence_count = 0;
    uint32_t diag_counter = 0;

    while (1) {
        afe_fetch_result_t *res = s_afe_iface->fetch(s_afe_data);
        if (!res || res->ret_value < 0) {
            continue;
        }

        /* Periodic diagnostic log (~every 3 seconds) */
        if (++diag_counter % 200 == 0) {
            ESP_LOGI(TAG, "WakeNet: Stream=%d | Vol=%.1fdB | VAD=%s | Wakeup=%d",
                     s_is_streaming, res->data_volume,
                     res->vad_state == AFE_VAD_SPEECH ? "SPEECH" : "SILENCE",
                     res->wakeup_state);
        }

        /* ── Wake Word Detection ── */
        if (res->wakeup_state == WAKENET_DETECTED) {
            ESP_LOGW(TAG, "════════════════════════════════════════════════════════");
            ESP_LOGW(TAG, "  >>> WAKE WORD DETECTED: 'Hi ESP' (index=%d) <<<",
                     res->wake_word_index);
            ESP_LOGW(TAG, "════════════════════════════════════════════════════════");

            /* Flush AFE buffer to discard pre-wake audio */
            s_afe_iface->reset_buffer(s_afe_data);

            voice_capture_start_streaming(0);  /* Trigger 0 = WakeNet */
            neural_silence_count = 0;
            continue;
        }

        /* ── Streaming Mode: send clean AFE audio + neural VAD silence detection ── */
        if (s_is_streaming) {
            if (res->data_size > 0 && res->data) {
                int filtered_samples = res->data_size / sizeof(int16_t);
                stream_chunk_to_subbox(res->data, filtered_samples);
            }

            /* Neural VAD from ESP-SR: detect silence to end recording */
            if (res->vad_state == AFE_VAD_SILENCE) {
                neural_silence_count++;
                /* End after ~375ms of neural silence (25 * 15ms AFE frame) */
                if (s_stream_frames > VAD_MIN_SPEECH_CHUNKS && neural_silence_count >= 25) {
                    ESP_LOGI(TAG, "Neural VAD: Silence detected by ESP-SR -> ending stream");
                    voice_capture_stop_streaming();
                    neural_silence_count = 0;
                }
            } else if (res->vad_state == AFE_VAD_SPEECH) {
                neural_silence_count = 0;
            }
        }
    }

    vTaskDelete(NULL);
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*              Fallback Mode: Energy VAD (when WakeNet unavailable)          */
/* ═══════════════════════════════════════════════════════════════════════════ */

static void voice_capture_fallback_task(void *pvParameters) {
    ESP_LOGI(TAG, "Voice Capture FALLBACK task started on Core 1 (energy VAD).");

    const size_t raw_buf_samples = AUDIO_DMA_FRAME_SAMPLES * 2;
    int32_t *raw_buf = (int32_t *)malloc(raw_buf_samples * sizeof(int32_t));
    int16_t *clean_buf = (int16_t *)malloc(AUDIO_DMA_FRAME_SAMPLES * sizeof(int16_t));
    int16_t chunk_buf[CHUNK_SAMPLES];
    int chunk_idx = 0;

    if (!raw_buf || !clean_buf) {
        ESP_LOGE(TAG, "Fallback: buffer allocation failed!");
        if (raw_buf) free(raw_buf);
        if (clean_buf) free(clean_buf);
        vTaskDelete(NULL);
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(300));

    int vad_consecutive_onsets = 0;
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

        /* Convert + bandpass filter */
        for (int i = 0; i < mono_samples; i++) {
            int32_t left_raw  = raw_buf[i * 2];
            int32_t right_raw = raw_buf[i * 2 + 1];
            int16_t l16 = (int16_t)(left_raw >> 14);
            int16_t r16 = (int16_t)(right_raw >> 14);
            int16_t raw_s = (abs(left_raw) >= abs(right_raw)) ? l16 : r16;

            float s = (float)remove_dc(raw_s);
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
                    ESP_LOGI(TAG, "Fallback VAD: Stream=%d | RMS=%.0f | Energy=%lld | Cooldown=%lu",
                             s_is_streaming, s_latest_rms, (long long)energy, (unsigned long)s_cooldown_frames);
                }

                if (!s_is_streaming) {
                    if (s_cooldown_frames > 0) {
                        s_cooldown_frames--;
                        vad_consecutive_onsets = 0;
                    } else {
                        if (energy >= FALLBACK_VAD_ENERGY_THRESH) {
                            vad_consecutive_onsets++;
                            if (vad_consecutive_onsets >= FALLBACK_VAD_ONSET_CHUNKS) {
                                vad_consecutive_onsets = 0;
                                ESP_LOGI(TAG, "Fallback: Speech onset! (RMS: %.1f, Energy: %lld)",
                                         s_latest_rms, (long long)energy);
                                voice_capture_start_streaming(1);

                                /* Send this initial chunk */
                                ActionBoxAudioChunkPacket chunk_pkt = {};
                                chunk_pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
                                chunk_pkt.seq = ++s_audio_seq;
                                chunk_pkt.pcm_len = sizeof(chunk_buf);
                                memcpy(chunk_pkt.pcm_data, chunk_buf, sizeof(chunk_buf));
                                espnow_transport_send((const uint8_t *)&chunk_pkt, 4 + sizeof(chunk_buf));
                                s_stream_chunks++;
                                s_stream_bytes += sizeof(chunk_buf);
                                s_stream_frames++;
                            }
                        } else {
                            if (vad_consecutive_onsets > 0) vad_consecutive_onsets--;
                        }
                    }
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

                    if (energy < FALLBACK_VAD_SILENCE_ENERGY) {
                        s_silence_frames++;
                    } else {
                        s_silence_frames = 0;
                    }

                    bool silence_end = (s_stream_frames >= VAD_MIN_SPEECH_CHUNKS) &&
                                      (s_silence_frames >= VAD_SILENCE_END_CHUNKS);
                    bool max_dur = (s_stream_frames >= VAD_MAX_STREAM_CHUNKS);

                    if (silence_end || max_dur) {
                        ESP_LOGI(TAG, "Fallback end: %s (%.2fs, %u chunks)",
                                 silence_end ? "Silence" : "MaxDuration",
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
    vTaskDelete(NULL);
}
