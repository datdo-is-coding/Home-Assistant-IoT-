/*
 * WebSocket Audio Client — Implementation
 * DTV Smart Home — ESP32-S3 Voice Node
 *
 * Handles:
 *   1. WebSocket connection to Pi 4 (ws://pi_ip:8765)
 *   2. Mic PCM streaming after WakeNet detection
 *   3. Silence detection (VAD) to end recording
 *   4. Receiving TTS PCM audio from Pi
 *   5. Playing TTS on I2S speaker (MAX98357A)
 *
 * State Machine:
 *   IDLE → (WakeNet) → STREAMING → (silence) → PROCESSING → (audio_start) → PLAYING → (audio_end) → IDLE
 */

#include "ws_audio_client.h"

#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "esp_heap_caps.h"
#include "cJSON.h"

static const char *TAG = "WS_AUDIO";

/* ─── Configuration ──────────────────────────────────────────────────── */

#define MIC_STREAM_BUF_SIZE    (16000)    /* 500ms of 16kHz/16-bit PCM in PSRAM */
#define SPK_STREAM_BUF_SIZE    (64000)    /* 2 seconds of 16kHz/16-bit PCM in PSRAM */
#define WS_SEND_BUF_SIZE       (640)      /* 20ms frame: 320 samples × 2 bytes */
#define SPK_PLAY_BUF_SIZE      (1024)     /* Speaker write chunk */

/* VAD (Voice Activity Detection) configuration */
#define VAD_SILENCE_ENERGY     (40000)    /* Mean-square threshold (~RMS 200) */
#define VAD_SILENCE_FRAMES     (75)       /* 75 × 20ms = 1.5 seconds */
#define VAD_IGNORE_FRAMES      (25)       /* Ignore first 0.5s for speech onset */
#define MAX_STREAM_FRAMES      (500)      /* 500 × 20ms = 10 seconds max recording */

/* ─── State ──────────────────────────────────────────────────────────── */

static esp_websocket_client_handle_t ws_client = NULL;
static volatile ws_audio_state_t ws_state = WS_STATE_IDLE;
static volatile bool ws_connected = false;
static volatile bool spk_audio_complete = false;

/* FreeRTOS stream buffers */
static StreamBufferHandle_t mic_stream_buf = NULL;   /* audio_feed_task → stream_task */
static StreamBufferHandle_t spk_stream_buf = NULL;   /* ws_event → speaker_task */

/* Task handles */
static TaskHandle_t stream_task_handle = NULL;
static TaskHandle_t speaker_task_handle = NULL;

/* Speaker I2S handle (passed from main) */
static i2s_chan_handle_t spk_i2s_handle = NULL;

/* LED control callback — defined in main.c */
extern void set_rgb_led_color(uint8_t r, uint8_t g, uint8_t b);

/* ─── Forward Declarations ───────────────────────────────────────────── */

static void ws_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data);
static void audio_stream_task(void *arg);
static void speaker_playback_task(void *arg);
static void handle_ws_text_message(const char *data, int len);

/* ─── Public API ─────────────────────────────────────────────────────── */

esp_err_t ws_audio_client_init(const char *uri, i2s_chan_handle_t spk_handle)
{
    ESP_LOGI(TAG, "Initializing WebSocket audio client → %s", uri);
    spk_i2s_handle = spk_handle;

    /* Allocate buffer storage in Octal PSRAM (8MB available) to preserve internal SRAM */
    static uint8_t *mic_buf_storage = NULL;
    static StaticStreamBuffer_t mic_buf_struct;
    static uint8_t *spk_buf_storage = NULL;
    static StaticStreamBuffer_t spk_buf_struct;

    if (!mic_buf_storage) {
        mic_buf_storage = (uint8_t *)heap_caps_malloc(MIC_STREAM_BUF_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (!spk_buf_storage) {
        spk_buf_storage = (uint8_t *)heap_caps_malloc(SPK_STREAM_BUF_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }

    if (mic_buf_storage && spk_buf_storage) {
        mic_stream_buf = xStreamBufferCreateStatic(MIC_STREAM_BUF_SIZE, 1, mic_buf_storage, &mic_buf_struct);
        spk_stream_buf = xStreamBufferCreateStatic(SPK_STREAM_BUF_SIZE, 1, spk_buf_storage, &spk_buf_struct);
        ESP_LOGI(TAG, "Stream buffers allocated in Octal PSRAM (mic=%d KB, spk=%d KB)",
                 MIC_STREAM_BUF_SIZE / 1024, SPK_STREAM_BUF_SIZE / 1024);
    } else {
        ESP_LOGW(TAG, "PSRAM alloc failed, falling back to internal SRAM buffers");
        mic_stream_buf = xStreamBufferCreate(3200, 1);
        spk_stream_buf = xStreamBufferCreate(16000, 1);
    }

    if (!mic_stream_buf || !spk_stream_buf) {
        ESP_LOGE(TAG, "Failed to create stream buffers! Check free heap.");
        return ESP_ERR_NO_MEM;
    }

    /* Configure WebSocket client */
    esp_websocket_client_config_t ws_cfg = {
        .uri = uri,
        .buffer_size = 4096,
        .reconnect_timeout_ms = 5000,
        .network_timeout_ms = 10000,
        .ping_interval_sec = 15,
        .pingpong_timeout_sec = 30,
        .disable_auto_reconnect = false,
    };

    ws_client = esp_websocket_client_init(&ws_cfg);
    if (!ws_client) {
        ESP_LOGE(TAG, "Failed to create WebSocket client!");
        return ESP_FAIL;
    }

    /* Register event handler */
    esp_websocket_register_events(ws_client, WEBSOCKET_EVENT_ANY,
                                  ws_event_handler, NULL);

    /* Create background tasks (4KB stack is sufficient for stream and playback) */
    BaseType_t ret;
    ret = xTaskCreatePinnedToCore(audio_stream_task, "audio_stream",
                                  4 * 1024, NULL, 4, &stream_task_handle, 1);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create audio_stream_task!");
        return ESP_ERR_NO_MEM;
    }

    ret = xTaskCreatePinnedToCore(speaker_playback_task, "spk_play",
                                  4 * 1024, NULL, 3, &speaker_task_handle, 1);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create speaker_playback_task!");
        return ESP_ERR_NO_MEM;
    }

    /* Start WebSocket connection (non-blocking, connects in background) */
    esp_err_t err = esp_websocket_client_start(ws_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "WebSocket client start failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "WebSocket audio client initialized. Waiting for connection...");
    return ESP_OK;
}

esp_err_t ws_audio_start_stream(void)
{
    if (!ws_connected) {
        ESP_LOGW(TAG, "Cannot stream: WebSocket not connected to Pi");
        set_rgb_led_color(255, 0, 0);   /* Red flash = not connected */
        vTaskDelay(pdMS_TO_TICKS(300));
        set_rgb_led_color(0, 0, 30);
        return ESP_ERR_INVALID_STATE;
    }

    if (ws_state != WS_STATE_IDLE) {
        ESP_LOGW(TAG, "Cannot stream: already in state %d", ws_state);
        return ESP_ERR_INVALID_STATE;
    }

    /* Clear stream buffers */
    xStreamBufferReset(mic_stream_buf);
    xStreamBufferReset(spk_stream_buf);
    spk_audio_complete = false;

    /* Send START message to Pi */
    const char *start_msg = "{\"type\":\"start\",\"codec\":\"pcm\",\"sample_rate\":16000}";
    int sent = esp_websocket_client_send_text(ws_client, start_msg,
                                              strlen(start_msg),
                                              pdMS_TO_TICKS(2000));
    if (sent < 0) {
        ESP_LOGE(TAG, "Failed to send start message!");
        return ESP_FAIL;
    }

    ws_state = WS_STATE_STREAMING;
    ESP_LOGI(TAG, "🎙️ Audio streaming STARTED — recording voice command...");

    /* Notify stream task to begin reading from mic buffer */
    xTaskNotifyGive(stream_task_handle);

    return ESP_OK;
}

void ws_audio_feed_pcm(const int16_t *pcm_data, int num_samples)
{
    if (ws_state != WS_STATE_STREAMING || !mic_stream_buf) return;

    size_t bytes = num_samples * sizeof(int16_t);
    /* Non-blocking write — drop data if buffer full (better than blocking AFE) */
    xStreamBufferSend(mic_stream_buf, pcm_data, bytes, 0);
}

bool ws_audio_is_streaming(void)
{
    return (ws_state == WS_STATE_STREAMING);
}

ws_audio_state_t ws_audio_get_state(void)
{
    return ws_state;
}

/* ─── WebSocket Event Handler ────────────────────────────────────────── */

static void ws_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;

    switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
        ws_connected = true;
        set_rgb_led_color(0, 0, 30);     /* Dim blue = idle connected */
        ESP_LOGI(TAG, "✅ WebSocket connected to Pi 4 Gateway");
        break;

    case WEBSOCKET_EVENT_DISCONNECTED:
        ws_connected = false;
        if (ws_state == WS_STATE_STREAMING || ws_state == WS_STATE_PROCESSING) {
            ws_state = WS_STATE_IDLE;
            ESP_LOGW(TAG, "WebSocket disconnected during operation! Resetting state.");
        }
        set_rgb_led_color(255, 50, 0);   /* Orange = disconnected */
        ESP_LOGW(TAG, "⚠️ WebSocket disconnected from Pi");
        break;

    case WEBSOCKET_EVENT_DATA:
        if (data->op_code == 0x01) {
            /* Text frame — JSON control message from Pi */
            handle_ws_text_message(data->data_ptr, data->data_len);
        }
        else if (data->op_code == 0x02) {
            /* Binary frame — PCM audio data for speaker */
            if (ws_state == WS_STATE_PLAYING && spk_stream_buf) {
                xStreamBufferSend(spk_stream_buf, data->data_ptr,
                                  data->data_len, pdMS_TO_TICKS(50));
            }
        }
        break;

    case WEBSOCKET_EVENT_ERROR:
        ESP_LOGE(TAG, "❌ WebSocket error occurred");
        break;

    default:
        break;
    }
}

/* ─── JSON Message Handler ───────────────────────────────────────────── */

static void handle_ws_text_message(const char *data, int len)
{
    /* Null-terminate the JSON string */
    char *json_str = malloc(len + 1);
    if (!json_str) return;
    memcpy(json_str, data, len);
    json_str[len] = '\0';

    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGW(TAG, "Failed to parse JSON: %.*s", len, data);
        free(json_str);
        return;
    }

    const cJSON *type = cJSON_GetObjectItem(root, "type");
    if (!cJSON_IsString(type)) {
        cJSON_Delete(root);
        free(json_str);
        return;
    }

    const char *type_str = type->valuestring;

    if (strcmp(type_str, "status") == 0) {
        const cJSON *state = cJSON_GetObjectItem(root, "state");
        if (cJSON_IsString(state)) {
            ESP_LOGI(TAG, "Pi status: %s", state->valuestring);
            if (strcmp(state->valuestring, "processing") == 0) {
                /* Pi acknowledged recording, now processing ASR+LLM */
                set_rgb_led_color(0, 0, 255);  /* Blue pulse = processing */
            }
        }
    }
    else if (strcmp(type_str, "transcript") == 0) {
        const cJSON *text = cJSON_GetObjectItem(root, "text");
        if (cJSON_IsString(text)) {
            ESP_LOGI(TAG, "📝 ASR Transcript: \"%s\"", text->valuestring);
        }
    }
    else if (strcmp(type_str, "command_result") == 0) {
        const cJSON *verify = cJSON_GetObjectItem(root, "verify");
        const cJSON *reply = cJSON_GetObjectItem(root, "voice_reply");
        ESP_LOGI(TAG, "🎯 Command result: verify=%s, reply=%s",
                 cJSON_IsString(verify) ? verify->valuestring : "null",
                 cJSON_IsString(reply) ? reply->valuestring : "null");
    }
    else if (strcmp(type_str, "audio_start") == 0) {
        /* Pi is about to send TTS audio for speaker playback */
        const cJSON *size = cJSON_GetObjectItem(root, "size");
        int audio_size = cJSON_IsNumber(size) ? size->valueint : 0;
        ESP_LOGI(TAG, "🔊 Receiving TTS audio (%d bytes) for speaker playback", audio_size);

        xStreamBufferReset(spk_stream_buf);
        spk_audio_complete = false;
        ws_state = WS_STATE_PLAYING;

        /* Notify speaker task to start playing */
        xTaskNotifyGive(speaker_task_handle);

        set_rgb_led_color(0, 255, 100);  /* Green = playing */
    }
    else if (strcmp(type_str, "audio_end") == 0) {
        ESP_LOGI(TAG, "🔊 TTS audio transmission complete");
        spk_audio_complete = true;
        /* Speaker task will drain remaining buffer and go idle */
    }
    else if (strcmp(type_str, "pong") == 0) {
        /* Heartbeat response, ignore */
    }
    else if (strcmp(type_str, "error") == 0) {
        const cJSON *msg = cJSON_GetObjectItem(root, "message");
        ESP_LOGW(TAG, "Pi error: %s",
                 cJSON_IsString(msg) ? msg->valuestring : "unknown");
        ws_state = WS_STATE_IDLE;
        set_rgb_led_color(0, 0, 30);
    }

    cJSON_Delete(root);
    free(json_str);
}

/* ─── Audio Stream Task ──────────────────────────────────────────────── */
/*
 * Reads PCM data from mic_stream_buf (fed by audio_feed_task in main.c),
 * sends it to Pi via WebSocket, and monitors for silence to end recording.
 */

static void audio_stream_task(void *arg)
{
    uint8_t send_buf[WS_SEND_BUF_SIZE];

    ESP_LOGI(TAG, "Audio stream task ready, waiting for WakeNet trigger...");

    while (1) {
        /* Block until WakeNet triggers ws_audio_start_stream() */
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        ESP_LOGI(TAG, "Stream task activated — sending mic PCM to Pi...");

        int silence_count = 0;
        int frame_count = 0;
        int speech_detected = 0;

        while (ws_state == WS_STATE_STREAMING && frame_count < MAX_STREAM_FRAMES) {
            /* Read PCM data from mic stream buffer */
            size_t received = xStreamBufferReceive(mic_stream_buf, send_buf,
                                                    sizeof(send_buf),
                                                    pdMS_TO_TICKS(100));
            if (received == 0) {
                /* Timeout — no data from mic. Check if we should abort. */
                if (!ws_connected) break;
                continue;
            }

            /* Send PCM binary frame to Pi via WebSocket */
            int sent = esp_websocket_client_send_bin(ws_client,
                                                      (const char *)send_buf,
                                                      received,
                                                      pdMS_TO_TICKS(500));
            if (sent < 0) {
                ESP_LOGW(TAG, "WebSocket send failed, aborting stream");
                break;
            }

            frame_count++;

            /* ─── Simple Energy-Based VAD ─── */
            int16_t *samples = (int16_t *)send_buf;
            int num_samples = received / sizeof(int16_t);
            int64_t energy = 0;

            for (int i = 0; i < num_samples; i++) {
                energy += (int64_t)samples[i] * samples[i];
            }
            if (num_samples > 0) {
                energy /= num_samples;  /* Mean square energy */
            }

            /* Skip VAD for the first 0.5 seconds (let speech start) */
            if (frame_count < VAD_IGNORE_FRAMES) {
                if (energy > VAD_SILENCE_ENERGY) {
                    speech_detected = 1;
                }
                continue;
            }

            /* Track speech presence */
            if (energy > VAD_SILENCE_ENERGY) {
                speech_detected = 1;
                silence_count = 0;
            } else {
                silence_count++;
            }

            /* End recording if silence > 1.5 seconds (after speech was detected) */
            if (speech_detected && silence_count >= VAD_SILENCE_FRAMES) {
                ESP_LOGI(TAG, "VAD: Silence detected for 1.5s — ending recording");
                break;
            }

            /* Log streaming progress every ~1 second */
            if (frame_count % 50 == 0) {
                ESP_LOGI(TAG, "Streaming: %d frames sent (%.1fs), energy=%lld",
                         frame_count, frame_count * 0.02f, (long long)energy);
            }
        }

        /* ─── End of Recording ─── */
        if (ws_state == WS_STATE_STREAMING) {
            /* Send STOP message to Pi */
            const char *stop_msg = "{\"type\":\"stop\"}";
            esp_websocket_client_send_text(ws_client, stop_msg,
                                           strlen(stop_msg),
                                           pdMS_TO_TICKS(2000));
            ws_state = WS_STATE_PROCESSING;

            ESP_LOGI(TAG, "🛑 Recording ended after %d frames (%.1fs). Waiting for Pi response...",
                     frame_count, frame_count * 0.02f);

            set_rgb_led_color(0, 50, 255);  /* Blue = processing on Pi */
        }

        /* If we broke out due to error, reset to idle */
        if (ws_state == WS_STATE_STREAMING) {
            ws_state = WS_STATE_IDLE;
            set_rgb_led_color(0, 0, 30);
        }
    }
}

/* ─── Speaker Playback Task ──────────────────────────────────────────── */
/*
 * Reads PCM data from spk_stream_buf (fed by WebSocket event handler),
 * writes it to I2S speaker for playback.
 * Runs continuously once activated, stops when all TTS audio is played.
 */

extern void speaker_enable(bool enable);

static void speaker_playback_task(void *arg)
{
    uint8_t play_buf[SPK_PLAY_BUF_SIZE];

    ESP_LOGI(TAG, "Speaker playback task ready, waiting for TTS audio...");

    while (1) {
        /* Block until TTS audio_start is received */
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        if (!spk_i2s_handle) {
            ESP_LOGW(TAG, "Speaker I2S handle not available, discarding audio");
            /* Drain the buffer without playing */
            while (ws_state == WS_STATE_PLAYING) {
                size_t n = xStreamBufferReceive(spk_stream_buf, play_buf,
                                                sizeof(play_buf),
                                                pdMS_TO_TICKS(500));
                if (n == 0 && spk_audio_complete) break;
            }
            ws_state = WS_STATE_IDLE;
            set_rgb_led_color(0, 0, 30);
            continue;
        }

        ESP_LOGI(TAG, "🔊 Starting speaker playback...");
        /* Unmute / Enable MAX98357A amplifier via SP_SD GPIO 2 */
        speaker_enable(true);
        vTaskDelay(pdMS_TO_TICKS(30)); /* Let amp power up smoothly */

        int total_played = 0;
        int empty_wait_count = 0;

        while (ws_state == WS_STATE_PLAYING) {
            size_t received = xStreamBufferReceive(spk_stream_buf, play_buf,
                                                    sizeof(play_buf),
                                                    pdMS_TO_TICKS(200));
            if (received > 0) {
                empty_wait_count = 0;
                size_t bytes_written = 0;
                esp_err_t err = i2s_channel_write(spk_i2s_handle, play_buf,
                                                   received, &bytes_written,
                                                   pdMS_TO_TICKS(1000));
                if (err != ESP_OK) {
                    ESP_LOGW(TAG, "I2S speaker write error: %s", esp_err_to_name(err));
                }
                total_played += bytes_written;
            } else {
                /* Timeout — no more data in buffer */
                if (spk_audio_complete) {
                    ESP_LOGI(TAG, "Speaker playback complete. Played %d bytes (%.2fs)",
                             total_played, (float)total_played / (16000 * 2));
                    break;
                }
                empty_wait_count++;
                if (empty_wait_count >= 15) { // 3 seconds timeout
                    ESP_LOGW(TAG, "Speaker playback timed out waiting for audio data");
                    break;
                }
            }
        }

        /* ── Drain I2S DMA with silence (zeros) so no residual buffer buzz remains ── */
        memset(play_buf, 0, sizeof(play_buf));
        for (int i = 0; i < 4; i++) {
            size_t dummy = 0;
            i2s_channel_write(spk_i2s_handle, play_buf, sizeof(play_buf), &dummy, pdMS_TO_TICKS(50));
        }
        vTaskDelay(pdMS_TO_TICKS(50)); /* Let zero-samples output completely */

        /* ── Put MAX98357A into hardware SHUTDOWN (mute) to eliminate idle hum/hiss ── */
        speaker_enable(false);

        /* Return to idle state */
        ws_state = WS_STATE_IDLE;
        set_rgb_led_color(0, 0, 30);  /* Dim blue = idle */
        ESP_LOGI(TAG, "🎙️ Ready for next voice command. Say 'Hi ESP'...");
    }
}
