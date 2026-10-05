/*
 * Voice Capture — Implementation
 * DTV Smart Home — T1 Actuator Node (ESP32-S3)
 *
 * Audio pipeline:
 *   INMP441 I2S Mic → ESP-SR AFE → WakeNet ("Hi ESP")
 *   → Wake Word Detected → Stream 16kHz 16-bit PCM Chunks via ESP-NOW to T2
 *   → Energy VAD / Max Duration → Audio End Packet
 */

#include "voice_capture.h"
#include "espnow_slave.h"
#include "t1_config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"

#if HAS_WAKENET
#include "esp_afe_sr_models.h"
#include "esp_afe_sr_iface.h"
#include "esp_nsn_models.h"
#include "model_path.h"
#endif

#if HAS_ADPCM
#include "adpcm.h"
static adpcm_state_t s_adpcm_enc_state;
#endif

static const char *TAG = "T1_VOICE";

/* ─── State ──────────────────────────────────────────────────────────── */

static i2s_chan_handle_t s_rx_handle = NULL;
static volatile bool s_is_streaming = false;

#if HAS_WAKENET
static const esp_afe_sr_iface_t *s_afe_handle = &ESP_AFE_SR_HANDLE;
static esp_afe_sr_data_t *s_afe_data = NULL;
#endif

/* ─── Streaming Counters ─────────────────────────────────────────────── */

static volatile uint16_t s_stream_chunks = 0;
static volatile uint32_t s_stream_bytes = 0;
static volatile uint32_t s_stream_frames = 0;
static volatile uint32_t s_silence_frames = 0;

/* Buffer for accumulating samples into ESPNOW_AUDIO_MAX_PCM_BYTES (240 bytes = 120 samples) */
#define CHUNK_SAMPLES (ESPNOW_AUDIO_MAX_PCM_BYTES / sizeof(int16_t))
static int16_t s_chunk_buf[CHUNK_SAMPLES];
static int s_chunk_buf_idx = 0;
#if HAS_ADPCM
static uint8_t s_adpcm_buf[CHUNK_SAMPLES / 2]; /* 120 samples -> 60 bytes ADPCM */
#endif

/* ─── Forward Declarations ───────────────────────────────────────────── */

static esp_err_t init_i2s_mic(void);
static void audio_feed_task(void *arg);
#if HAS_WAKENET
static void audio_detect_task(void *arg);
#endif

/* ─── Public API ─────────────────────────────────────────────────────── */

bool voice_capture_is_streaming(void)
{
    return s_is_streaming;
}

void voice_capture_start_streaming(uint8_t trigger_source)
{
    if (s_is_streaming) return;

    ESP_LOGI(TAG, "🎙️ Voice streaming started (trigger=%d, ADPCM=%d)", trigger_source, HAS_ADPCM);
    s_stream_chunks = 0;
    s_stream_bytes = 0;
    s_stream_frames = 0;
    s_silence_frames = 0;
    s_chunk_buf_idx = 0;
#if HAS_ADPCM
    adpcm_init_state(&s_adpcm_enc_state);
#endif
    s_is_streaming = true;

    gpio_set_level(LED2_GPIO, 1); /* Voice LED ON */
    espnow_slave_send_audio_start(trigger_source);
}

void voice_capture_stop_streaming(void)
{
    if (!s_is_streaming) return;

    ESP_LOGI(TAG, "🛑 Voice streaming stopped (chunks=%u, bytes=%u)", s_stream_chunks, (unsigned)s_stream_bytes);
    s_is_streaming = false;
    gpio_set_level(LED2_GPIO, 0); /* Voice LED OFF */
    espnow_slave_send_audio_end(s_stream_chunks, s_stream_bytes);
}

esp_err_t voice_capture_init(void)
{
#if !HAS_MIC
    ESP_LOGI(TAG, "Microphone feature disabled in config.");
    return ESP_OK;
#endif

    ESP_LOGI(TAG, "Initializing Voice Capture Subsystem on ESP32-S3...");

    /* 1. Init I2S peripheral for INMP441 */
    esp_err_t err = init_i2s_mic();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize I2S microphone: %s", esp_err_to_name(err));
        return err;
    }

#if HAS_WAKENET
    /* 2. Load Speech Recognition Models from "model" partition */
    srmodel_list_t *models = esp_srmodel_init("model");
    if (!models || models->num <= 0) {
        ESP_LOGW(TAG, "Speech models not found in 'model' partition (num=%d)", models ? models->num : -1);
        ESP_LOGW(TAG, "WakeNet wake-word bypassed. Device will operate in relay-only/manual mode.");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Loaded %d speech model(s) from flash:", models->num);
    for (int i = 0; i < models->num; i++) {
        ESP_LOGI(TAG, "  [%d] Model: '%s'", i, models->model_name[i]);
    }

    char *wn_name = esp_srmodel_filter(models, ESP_WN_PREFIX, "hiesp");
    if (!wn_name) {
        wn_name = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
    }
    if (!wn_name) {
        ESP_LOGE(TAG, "No WakeNet model found in speech partition!");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "Selected WakeNet model: '%s'", wn_name);

    /* 3. Configure ESP-SR Audio Front-End (AFE) for 1-MIC without PSRAM */
    afe_config_t afe_config = AFE_CONFIG_DEFAULT();
    afe_config.aec_init = false; /* Single mic without reference */
    afe_config.se_init = false; /* Disable heavy neural NS on non-PSRAM chip to reserve SRAM for WakeNet */
    afe_config.vad_init = true; /* VAD */
    afe_config.wakenet_init = true;
    afe_config.wakenet_model_name = wn_name;
    afe_config.wakenet_mode = DET_MODE_90; /* 1-MIC detection mode */
    afe_config.afe_mode = SR_MODE_LOW_COST;
    afe_config.memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_INTERNAL; /* Allocate in internal SRAM */
    afe_config.afe_ringbuf_size = 10;
    ESP_LOGI(TAG, "AFE configured for 1-MIC (Internal SRAM allocation, ringbuf=10)");

    afe_config.pcm_config.total_ch_num = 1;
    afe_config.pcm_config.mic_num = 1;
    afe_config.pcm_config.ref_num = 0;

    ESP_LOGI(TAG, "Heap before AFE create: Free=%u KB, Largest Block=%u KB",
             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
             (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL) / 1024));

    s_afe_data = s_afe_handle->create_from_config(&afe_config);
    if (!s_afe_data) {
        ESP_LOGE(TAG, "Failed to create ESP-SR AFE handle!");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Heap after AFE create: Free=%u KB, Largest Block=%u KB",
             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
             (unsigned)(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL) / 1024));

    /* 4. Launch Tasks: Feed (Core 0, Priority 5), Detect (Core 1, Priority 6 - higher to prevent overflow) */
    xTaskCreatePinnedToCore(audio_feed_task, "t1_audio_feed", 8 * 1024, s_afe_data, 5, NULL, 0);
    xTaskCreatePinnedToCore(audio_detect_task, "t1_audio_det", 8 * 1024, s_afe_data, 6, NULL, 1);

    ESP_LOGI(TAG, "WakeNet pipeline active. Listening for '%s'...", wn_name);
#else
    /* Non-WakeNet fallback: just feed task if mic is enabled */
    xTaskCreate(audio_feed_task, "t1_audio_feed", 4 * 1024, NULL, 5, NULL);
#endif

    return ESP_OK;
}

/* ─── Internal: I2S Initialization ───────────────────────────────────── */

static esp_err_t init_i2s_mic(void)
{
    ESP_LOGI(TAG, "Setting up INMP441 I2S (BCLK:%d, WS:%d, DIN:%d)...",
             MIC_I2S_GPIO_BCLK, MIC_I2S_GPIO_WS, MIC_I2S_GPIO_DIN);

    i2s_chan_config_t chan_cfg = {
        .id = MIC_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    esp_err_t ret = i2s_new_channel(&chan_cfg, NULL, &s_rx_handle);
    if (ret != ESP_OK) return ret;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = MIC_I2S_GPIO_BCLK,
            .ws   = MIC_I2S_GPIO_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = MIC_I2S_GPIO_DIN,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    ret = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (ret != ESP_OK) return ret;

    /* Pull down DIN pin so it doesn't float when no mic is connected or during tri-state slots */
    gpio_set_pull_mode(MIC_I2S_GPIO_DIN, GPIO_PULLDOWN_ONLY);

    return i2s_channel_enable(s_rx_handle);
}

/* ─── DC Removal Filter ──────────────────────────────────────────────── */

static int32_t s_dc_offset = 0;

static inline int16_t remove_dc(int16_t in)
{
    s_dc_offset += ((int32_t)in - (s_dc_offset >> 7));
    int32_t ac = (int32_t)in - (s_dc_offset >> 7);
    if (ac > 32767) ac = 32767;
    if (ac < -32768) ac = -32768;
    return (int16_t)ac;
}

/* ─── Internal: Process Audio Chunk & Stream via ESP-NOW ─────────────── */

static void process_and_stream_samples(const int16_t *samples, int num_samples)
{
    if (!s_is_streaming) {
        s_chunk_buf_idx = 0;
        return;
    }

    for (int i = 0; i < num_samples; i++) {
        s_chunk_buf[s_chunk_buf_idx++] = samples[i];

        if (s_chunk_buf_idx >= CHUNK_SAMPLES) {
            /* Full chunk ready (120 samples = 7.5ms @16kHz) */
#if HAS_ADPCM
            int enc_bytes = adpcm_encode(s_chunk_buf, CHUNK_SAMPLES, s_adpcm_buf, &s_adpcm_enc_state);
            espnow_slave_send_audio_chunk(s_adpcm_buf, enc_bytes);
            s_stream_bytes += enc_bytes;
#else
            uint16_t chunk_bytes = CHUNK_SAMPLES * sizeof(int16_t);
            espnow_slave_send_audio_chunk((const uint8_t *)s_chunk_buf, chunk_bytes);
            s_stream_bytes += chunk_bytes;
#endif

            s_stream_chunks++;
            s_stream_frames++;

            /* Energy-based VAD calculation */
            int64_t sum_sq = 0;
            for (int k = 0; k < CHUNK_SAMPLES; k++) {
                int32_t val = s_chunk_buf[k];
                sum_sq += val * val;
            }
            int64_t energy = sum_sq / CHUNK_SAMPLES;

            if (energy < VAD_SILENCE_ENERGY) {
                s_silence_frames++;
            } else {
                s_silence_frames = 0;
            }

            s_chunk_buf_idx = 0;

            /* Check silence timeout (e.g. 600ms silence after initial speech onset) */
            bool silence_timeout = (s_stream_frames > VAD_IGNORE_FRAMES) &&
                                  (s_silence_frames >= VAD_SILENCE_FRAMES);
            bool max_len_reached = (s_stream_frames >= MAX_STREAM_FRAMES);

            if (silence_timeout || max_len_reached) {
                ESP_LOGI(TAG, "Voice stream ending: %s (chunks=%u, bytes=%u, frames=%u)",
                         silence_timeout ? "Silence detected" : "Max duration reached",
                         s_stream_chunks, (unsigned)s_stream_bytes, (unsigned)s_stream_frames);

                voice_capture_stop_streaming();
                break;
            }
        }
    }
}

/* ─── Task: Audio Feed ───────────────────────────────────────────────── */

static void audio_feed_task(void *arg)
{
#if HAS_WAKENET
    esp_afe_sr_data_t *afe_data = (esp_afe_sr_data_t *)arg;
    int audio_chunksize = s_afe_handle->get_feed_chunksize(afe_data);
    int nch = s_afe_handle->get_channel_num(afe_data);
    int feed_size = audio_chunksize * nch * sizeof(int16_t);
#else
    int audio_chunksize = 240;
    int feed_size = audio_chunksize * sizeof(int16_t);
#endif

    int raw_buff_size = audio_chunksize * 2 * sizeof(int32_t);
    int32_t *raw_buff = (int32_t *)heap_caps_malloc(raw_buff_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!raw_buff) raw_buff = (int32_t *)malloc(raw_buff_size);

    int16_t *i2s_buff = (int16_t *)heap_caps_malloc(feed_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!i2s_buff) i2s_buff = (int16_t *)malloc(feed_size);

    if (!raw_buff || !i2s_buff) {
        ESP_LOGE(TAG, "Audio feed task buffer allocation failed!");
        vTaskDelete(NULL);
        return;
    }

    size_t bytes_read = 0;
    ESP_LOGI(TAG, "Audio feed task running (chunksize: %d)...", audio_chunksize);

    /* Allow I2S microphone hardware and DC-blocking filter to settle */
    vTaskDelay(pdMS_TO_TICKS(500));

    int vad_consecutive_triggers = 0;

    while (1) {
        esp_err_t ret = i2s_channel_read(s_rx_handle, raw_buff, raw_buff_size, &bytes_read, 100 / portTICK_PERIOD_MS);
        if (ret == ESP_OK && bytes_read > 0) {
            int samples_read = bytes_read / sizeof(int32_t);
            int mono_samples = samples_read / 2;
            if (mono_samples > audio_chunksize) mono_samples = audio_chunksize;

            /* Convert 32-bit I2S slot samples to 16-bit mono and remove DC */
            for (int i = 0; i < mono_samples; i++) {
                int32_t left_sample  = raw_buff[i * 2];
                int32_t right_sample = raw_buff[i * 2 + 1];

                int16_t l16 = (int16_t)(left_sample >> 14);
                int16_t r16 = (int16_t)(right_sample >> 14);

                /* Auto-select active channel */
                int16_t raw_s = (abs(left_sample) >= abs(right_sample)) ? l16 : r16;
                i2s_buff[i] = remove_dc(raw_s);
            }

#if !HAS_WAKENET
            /* Stream via ESP-NOW if active (fallback mode when WakeNet disabled) */
            if (s_is_streaming) {
                process_and_stream_samples(i2s_buff, mono_samples);
            } else {
                /* Autonomous Voice Activity Detection when not using WakeNet */
                int64_t sum_sq = 0;
                for (int i = 0; i < mono_samples; i++) {
                    int32_t s = i2s_buff[i];
                    sum_sq += s * s;
                }
                int64_t energy = sum_sq / mono_samples;

                static int debug_cnt = 0;
                if (++debug_cnt % 50 == 0) {
                    ESP_LOGI(TAG, "Mic Diagnostic: L_raw=%ld R_raw=%ld l16=%d r16=%d s0=%d Energy=%lld",
                             (long)raw_buff[0], (long)raw_buff[1],
                             (int)(raw_buff[0] >> 14), (int)(raw_buff[1] >> 14),
                             (int)i2s_buff[0], (long long)energy);
                }

                if (energy > 2500000) { /* Significant spoken voice threshold */
                    vad_consecutive_triggers++;
                    if (vad_consecutive_triggers >= 3) { /* 3 consecutive chunks = ~45ms of stable speech */
                        vad_consecutive_triggers = 0;
                        voice_capture_start_streaming(1);
                        process_and_stream_samples(i2s_buff, mono_samples);
                    }
                } else {
                    vad_consecutive_triggers = 0;
                }
            }
#else
            /* Feed into AFE engine for wake-word detection and noise suppression (NS + AGC) */
            s_afe_handle->feed(afe_data, i2s_buff);
#endif
        } else {
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }

    free(raw_buff);
    free(i2s_buff);
    vTaskDelete(NULL);
}

#if HAS_WAKENET
/* ─── Task: Audio Detect (WakeNet & Clean AFE Streaming) ─────────────── */

static void audio_detect_task(void *arg)
{
    esp_afe_sr_data_t *afe_data = (esp_afe_sr_data_t *)arg;
    int afe_chunksize = s_afe_handle->get_fetch_chunksize(afe_data);
    ESP_LOGI(TAG, "Audio detect task running (fetch chunk: %d)...", afe_chunksize);

    int neural_silence_count = 0;

    while (1) {
        afe_fetch_result_t *res = s_afe_handle->fetch(afe_data);
        if (!res || res->ret_value < 0) {
            continue;
        }

        if (res->wakeup_state == WAKENET_DETECTED) {
            ESP_LOGW(TAG, ">>> [T1 WAKENET DETECTED] Wake Word Triggered! (index=%d) <<<",
                     res->wake_word_index);

            /* Flush AFE buffer to avoid feeding past audio into session */
            s_afe_handle->reset_buffer(afe_data);

            voice_capture_start_streaming(res->wake_word_index);
            neural_silence_count = 0;
            continue;
        }

        /* While streaming is active: stream the clean, filtered audio from AFE */
        if (s_is_streaming) {
            if (res->data_size > 0 && res->data) {
                int filtered_samples = res->data_size / sizeof(int16_t);
                process_and_stream_samples(res->data, filtered_samples);
            }

            /* Neural VAD: Cleanly terminate recording when silence is detected */
            if (res->vad_state == AFE_VAD_SILENCE) {
                neural_silence_count++;
                if (s_stream_frames > VAD_IGNORE_FRAMES && neural_silence_count >= 25) {
                    ESP_LOGI(TAG, "Neural VAD: Silence detected by ESP-SR -> ending recording");
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
#endif
