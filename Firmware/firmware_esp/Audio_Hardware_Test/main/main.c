/*
 * DTV Smart Home — Audio Dataset Acquisition Node
 * Target: ESP32-S3 (Native USB / COM8)
 *
 * Architecture:
 *   ├── input/
 *   │   ├── audio_input.h/c      (INMP441 + Active Channel Lock + 4th-Order Bandpass + Noise Gate)
 *   │   └── trigger_manager.h/c  (Physical Buttons BUT1/BOOT + USB Serial Command Listener)
 *   ├── output/
 *   │   ├── usb_stream.h/c       (High-speed USB Binary Framing + RIFF WAV Header Streamer)
 *   │   ├── audio_output.h/c     (MAX98357A Loa + Smart SD Muting + "Ding/Boop" Feedback)
 *   │   └── status_indicator.h/c (LED Visual Feedback: Green=Ready, Blue=Active)
 *   └── main.c                   (Event-Driven Dataset Recording Coordinator)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "app_config.h"
#include "input/audio_input.h"
#include "input/trigger_manager.h"
#include "output/usb_stream.h"
#include "output/audio_output.h"
#include "output/status_indicator.h"

static const char *TAG = "DATASET_NODE";

/* Recording buffer in PSRAM */
static int16_t s_record_buffer[MAX_RECORD_SAMPLES];
static int s_recorded_samples = 0;

/* Option: Set to true if you want speaker playback of recorded voice */
#define ENABLE_SPEAKER_PLAYBACK 0

static void audio_collector_task(void *arg)
{
    int16_t frame_buf[AUDIO_FRAME_SAMPLES];
    float frame_rms = 0.0f;
    app_state_t state = STATE_IDLE;
    int heartbeat = 0;

    int speech_count = 0;
    int silence_count = 0;
    bool has_spoken = false;

    while (1) {
        switch (state) {
        case STATE_IDLE: {
            /* 1. Read Clean Filtered Audio Frame from INPUT */
            if (audio_input_read_clean(frame_buf, AUDIO_FRAME_SAMPLES, &frame_rms) != ESP_OK) {
                vTaskDelay(pdMS_TO_TICKS(10));
                continue;
            }

            /* 2. Poll triggers (Hardware button BUT1/BOOT or USB commands 'r'/'R') */
            trigger_source_t trig = trigger_manager_poll();

            if (trig != TRIGGER_NONE) {
                const char *src = (trig == TRIGGER_USB_CMD) ? "USB COMMAND ('r')" : "HARDWARE BUTTON";
                ESP_LOGI(TAG, "==================================================");
                ESP_LOGW(TAG, "🎙️ [RECORD START] Triggered by %s!", src);
                ESP_LOGI(TAG, "==================================================");

                /* Sound chime prompt & set LED */
                audio_output_play_chime(CHIME_WAKE);
                status_indicator_set_state(STATE_RECORDING);

                /* Flush stale DMA buffers to prevent echo of chime */
                audio_input_flush_buffers();

                /* Inform USB host of session start */
                usb_stream_send_start(AUDIO_SAMPLE_RATE, 1, 16);

                s_recorded_samples = 0;
                speech_count = 0;
                silence_count = 0;
                has_spoken = false;
                state = STATE_RECORDING;
            } else {
                heartbeat++;
                if (heartbeat % 150 == 0) { /* Every ~3 seconds */
                    ESP_LOGI(TAG, "🟢 [READY] Press BUT1/BOOT or send 'r' via USB to record...");
                }
            }
            break;
        }

        case STATE_RECORDING: {
            /* 1. Read clean audio frame */
            if (audio_input_read_clean(frame_buf, AUDIO_FRAME_SAMPLES, &frame_rms) != ESP_OK) {
                continue;
            }

            bool is_speech = audio_input_is_speech(frame_rms);
            bool btn_down  = trigger_manager_is_button_down();

            /* 2. Real-time stream frame over USB to PC/Phone */
            usb_stream_send_frame(frame_buf, AUDIO_FRAME_SAMPLES, is_speech, btn_down);

            /* 3. Store into PSRAM record buffer */
            if (s_recorded_samples + AUDIO_FRAME_SAMPLES <= MAX_RECORD_SAMPLES) {
                memcpy(&s_record_buffer[s_recorded_samples], frame_buf, AUDIO_FRAME_SAMPLES * sizeof(int16_t));
                s_recorded_samples += AUDIO_FRAME_SAMPLES;
            }

            /* 4. Track speech & silence */
            if (is_speech) {
                speech_count++;
                silence_count = 0;
                if (speech_count >= 2) {
                    has_spoken = true;
                }
            } else {
                if (has_spoken) {
                    silence_count++;
                }
            }

            /* 5. Check Stop Triggers */
            bool stop_req = trigger_manager_poll_stop();
            bool max_len  = (s_recorded_samples >= MAX_RECORD_SAMPLES);
            bool vad_stop = (has_spoken && silence_count >= 25 && s_recorded_samples >= (AUDIO_SAMPLE_RATE * 7 / 10));

            if (stop_req || max_len || vad_stop) {
                if (stop_req) {
                    ESP_LOGI(TAG, "⏹️ [STOP] Triggered by user/button!");
                } else if (max_len) {
                    ESP_LOGI(TAG, "⏱️ [STOP] Maximum recording duration (%.1fs) reached.", (float)MAX_RECORD_SECONDS);
                } else {
                    ESP_LOGI(TAG, "🛑 [VAD] End of utterance detected (silence > 500ms)!");
                }

                state = STATE_FINALIZE;
            }
            break;
        }

        case STATE_FINALIZE: {
            status_indicator_set_state(STATE_FINALIZE);

            /* Send session end packet */
            usb_stream_send_end(s_recorded_samples);

            /* Also send WAV header so host can dump directly */
            usb_stream_send_wav_header(s_recorded_samples);

            float duration = (float)s_recorded_samples / (float)AUDIO_SAMPLE_RATE;

            ESP_LOGI(TAG, "💾 [SESSION SAVED] Sent %.2fs (%d samples) over USB!", duration, s_recorded_samples);

#if ENABLE_SPEAKER_PLAYBACK
            ESP_LOGI(TAG, "🔊 Playing back on MAX98357A speaker...");
            audio_output_play_voice(s_record_buffer, s_recorded_samples);
#endif

            audio_input_flush_buffers();
            vTaskDelay(pdMS_TO_TICKS(150));

            state = STATE_IDLE;
            status_indicator_set_state(STATE_IDLE);
            ESP_LOGI(TAG, "🟢 [READY] Ready for next recording sample!\n");
            break;
        }

        default:
            state = STATE_IDLE;
            break;
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "==============================================================");
    ESP_LOGI(TAG, "   DTV SMART HOME — AUDIO DATASET ACQUISITION NODE            ");
    ESP_LOGI(TAG, "   High-Speed USB Streaming (Native USB / CDC on COM8)        ");
    ESP_LOGI(TAG, "==============================================================");

    /* Initialize NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* 1. Initialize OUTPUT Modules */
    status_indicator_init();
    usb_stream_init();
    audio_output_init();


    /* 2. Initialize INPUT Modules */
    audio_input_init();
    trigger_manager_init();

    /* 3. Launch Coordinator Task */
    xTaskCreatePinnedToCore(audio_collector_task, "audio_collector", 8192, NULL, 5, NULL, 0);

    ESP_LOGI(TAG, "🚀 SYSTEM ONLINE!");
    ESP_LOGI(TAG, "👉 Press BUT1/BOOT or send 'r' over USB to start recording!");
}
