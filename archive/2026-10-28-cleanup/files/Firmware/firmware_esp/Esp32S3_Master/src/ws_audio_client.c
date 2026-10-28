#include "ws_audio_client.h"
#include "audio_feedback.h"
#include "mqtt_relay.h"
#include "ota_updater.h"

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

#define MIC_STREAM_BUF_SIZE    (16000)
#define SPK_STREAM_BUF_SIZE    (512000)
#define WS_SEND_BUF_SIZE       (640)
#define SPK_PLAY_BUF_SIZE      (1024)

#define VAD_SILENCE_ENERGY     (40000)
#define VAD_SILENCE_FRAMES     (30)
#define VAD_IGNORE_FRAMES      (15)
#define MAX_STREAM_FRAMES      (500)

static esp_websocket_client_handle_t ws_client = NULL;
static volatile ws_audio_state_t ws_state = WS_STATE_IDLE;
static volatile bool ws_connected = false;
static volatile bool s_speaker_busy = false;
static volatile bool spk_audio_complete = false;
static volatile bool pending_followup = false;

static StreamBufferHandle_t mic_stream_buf = NULL;
static StreamBufferHandle_t spk_stream_buf = NULL;

static TaskHandle_t stream_task_handle = NULL;
static TaskHandle_t speaker_task_handle = NULL;

static uint8_t s_residual_byte = 0;
static bool s_has_residual = false;
static uint8_t s_last_op_code = 0;

static i2s_chan_handle_t spk_i2s_handle = NULL;

extern void led1_set(bool on);
extern void led2_set(bool on);

static void ws_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data);
static void audio_stream_task(void *arg);
static void speaker_playback_task(void *arg);
static void handle_ws_text_message(const char *data, int len);

esp_err_t ws_audio_client_init(const char *uri, i2s_chan_handle_t spk_handle)
{
    ESP_LOGI(TAG, "Initializing WebSocket audio client → %s", uri);
    spk_i2s_handle = spk_handle;

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
        mic_stream_buf = xStreamBufferCreateStatic(MIC_STREAM_BUF_SIZE, 2, mic_buf_storage, &mic_buf_struct);
        spk_stream_buf = xStreamBufferCreateStatic(SPK_STREAM_BUF_SIZE, 2, spk_buf_storage, &spk_buf_struct);
        ESP_LOGI(TAG, "Stream buffers allocated in Octal PSRAM (mic=%d KB, spk=%d KB)",
                 MIC_STREAM_BUF_SIZE / 1024, SPK_STREAM_BUF_SIZE / 1024);
    } else {
        ESP_LOGW(TAG, "PSRAM alloc failed, falling back to internal SRAM buffers");
        mic_stream_buf = xStreamBufferCreate(3200, 1);
        spk_stream_buf = xStreamBufferCreate(32000, 1);
    }

    if (!mic_stream_buf || !spk_stream_buf) {
        ESP_LOGE(TAG, "Failed to create stream buffers! Check free heap.");
        return ESP_ERR_NO_MEM;
    }

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

    esp_websocket_register_events(ws_client, WEBSOCKET_EVENT_ANY,
                                  ws_event_handler, NULL);

    BaseType_t ret;
    ret = xTaskCreatePinnedToCore(audio_stream_task, "audio_stream",
                                  6 * 1024, NULL, 4, &stream_task_handle, 1);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create audio_stream_task!");
        return ESP_ERR_NO_MEM;
    }

    ret = xTaskCreatePinnedToCore(speaker_playback_task, "spk_play",
                                  8 * 1024, NULL, 3, &speaker_task_handle, 1);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create speaker_playback_task!");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "WebSocket audio client initialized (ready for network IP)...");
    return ESP_OK;
}

static bool ws_client_started = false;

esp_err_t ws_audio_client_start(void)
{
    if (!ws_client) return ESP_FAIL;
    if (ws_client_started) return ESP_OK;

    ESP_LOGI(TAG, "🔄 Starting WebSocket connection to Gateway...");
    esp_err_t err = esp_websocket_client_start(ws_client);
    if (err == ESP_OK) {
        ws_client_started = true;
    } else {
        ESP_LOGE(TAG, "WebSocket client start failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t ws_audio_start_stream(void)
{
    if (!ws_connected) {
        ESP_LOGW(TAG, "Cannot stream: WebSocket not connected to Pi");
        led2_set(true);
        vTaskDelay(pdMS_TO_TICKS(200));
        led2_set(false);
        return ESP_ERR_INVALID_STATE;
    }

    if (ws_state != WS_STATE_IDLE) {
        ESP_LOGW(TAG, "Cannot stream: already in state %d", ws_state);
        return ESP_ERR_INVALID_STATE;
    }

    xStreamBufferReset(mic_stream_buf);
    xStreamBufferReset(spk_stream_buf);
    spk_audio_complete = false;

    char start_msg[160];
    snprintf(start_msg, sizeof(start_msg),
             "{\"type\":\"start\",\"codec\":\"pcm\",\"sample_rate\":16000,\"node_id\":\"%s\"}",
             mqtt_relay_get_node_id());
    int sent = esp_websocket_client_send_text(ws_client, start_msg,
                                              strlen(start_msg),
                                              pdMS_TO_TICKS(2000));
    if (sent < 0) {
        ESP_LOGE(TAG, "Failed to send start message!");
        return ESP_FAIL;
    }

    ws_state = WS_STATE_STREAMING;
    ESP_LOGI(TAG, "🎙️ Audio streaming STARTED — recording voice command...");

    xTaskNotifyGive(stream_task_handle);

    return ESP_OK;
}

void ws_audio_feed_pcm(const int16_t *pcm_data, int num_samples)
{
    if (ws_state != WS_STATE_STREAMING || !mic_stream_buf) return;

    size_t bytes = num_samples * sizeof(int16_t);

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

bool ws_audio_is_followup_pending(void)
{
    return pending_followup;
}

static void ws_event_handler(void *arg, esp_event_base_t event_base,
                             int32_t event_id, void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;

    switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
        ws_connected = true;
        led1_set(true);
        ESP_LOGI(TAG, "✅ WebSocket connected to Pi 4 Gateway");

        char ws_hello[192];
        if (mqtt_relay_is_provisioned()) {
            snprintf(ws_hello, sizeof(ws_hello),
                     "{\"t\":\"hello\",\"id\":\"%s\",\"mac\":\"%s\",\"cfg\":%lu,\"rl\":[%d,%d]}",
                     mqtt_relay_get_node_id(), mqtt_relay_get_mac_str(),
                     (unsigned long)mqtt_relay_get_cfg_version(),
                     mqtt_relay_get_state(1) ? 1 : 0, mqtt_relay_get_state(2) ? 1 : 0);
        } else {
            snprintf(ws_hello, sizeof(ws_hello),
                     "{\"t\":\"hello\",\"mac\":\"%s\",\"cfg\":null,\"rl\":[%d,%d]}",
                     mqtt_relay_get_mac_str(),
                     mqtt_relay_get_state(1) ? 1 : 0, mqtt_relay_get_state(2) ? 1 : 0);
        }
        esp_websocket_client_send_text(ws_client, ws_hello, strlen(ws_hello), pdMS_TO_TICKS(1000));
        break;

    case WEBSOCKET_EVENT_DISCONNECTED:
        ws_connected = false;
        s_has_residual = false;
        s_last_op_code = 0;
        if (ws_state != WS_STATE_IDLE) {
            ESP_LOGW(TAG, "WebSocket disconnected during state %d! Resetting to IDLE.", ws_state);
            ws_state = WS_STATE_IDLE;
            spk_audio_complete = true;
            if (spk_stream_buf) {
                xStreamBufferReset(spk_stream_buf);
            }
        }
        led1_set(false);
        led2_set(false);
        ESP_LOGW(TAG, "⚠️ WebSocket disconnected from Pi");
        break;

    case WEBSOCKET_EVENT_DATA:
        if (data->op_code != 0x00) {
            s_last_op_code = data->op_code;
        }

        if (data->op_code == 0x01) {

            handle_ws_text_message(data->data_ptr, data->data_len);
        }
        else if (data->op_code == 0x02 || (data->op_code == 0x00 && s_last_op_code == 0x02)) {

            if (ws_state == WS_STATE_PLAYING && spk_stream_buf && data->data_len > 0) {
                const uint8_t *p_data = (const uint8_t *)data->data_ptr;
                int len = data->data_len;

                if (s_has_residual && len > 0) {
                    uint8_t pair[2] = { s_residual_byte, *p_data };
                    xStreamBufferSend(spk_stream_buf, pair, 2, pdMS_TO_TICKS(50));
                    p_data++;
                    len--;
                    s_has_residual = false;
                }

                if (len & 1) {
                    s_residual_byte = p_data[len - 1];
                    s_has_residual = true;
                    len--;
                }

                if (len > 0) {
                    xStreamBufferSend(spk_stream_buf, p_data, len, pdMS_TO_TICKS(50));
                }
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

static void handle_ws_text_message(const char *data, int len)
{

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

    const cJSON *t_item = cJSON_GetObjectItem(root, "t");
    if (cJSON_IsString(t_item)) {
        const char *t_str = t_item->valuestring;
        if (strcmp(t_str, "rl") == 0) {

            const cJSON *ch_item = cJSON_GetObjectItem(root, "ch");
            const cJSON *s_item = cJSON_GetObjectItem(root, "s");
            const cJSON *seq_item = cJSON_GetObjectItem(root, "seq");
            int ch = cJSON_IsNumber(ch_item) ? ch_item->valueint : 0;
            int s = cJSON_IsNumber(s_item) ? s_item->valueint : 0;
            int seq = cJSON_IsNumber(seq_item) ? seq_item->valueint : 0;
            if (ch >= 1 && ch <= 2) {
                mqtt_relay_set(ch, s == 1);
                char ack[128];
                snprintf(ack, sizeof(ack),
                         "{\"t\":\"ack\",\"id\":\"%s\",\"rl\":[%d,%d],\"seq\":%d}",
                         mqtt_relay_get_node_id(),
                         mqtt_relay_get_state(1)?1:0, mqtt_relay_get_state(2)?1:0,
                         seq);
                esp_websocket_client_send_text(ws_client, ack, strlen(ack), pdMS_TO_TICKS(500));
            }
            cJSON_Delete(root);
            free(json_str);
            return;
        } else if (strcmp(t_str, "cfg") == 0) {
            mqtt_relay_handle_cfg_json(json_str);
            cJSON_Delete(root);
            free(json_str);
            return;
        } else if (strcmp(t_str, "hello_ok") == 0) {
            ESP_LOGI(TAG, "Gateway acknowledged WebSocket connection (hello_ok)");
            cJSON_Delete(root);
            free(json_str);
            return;
        } else if (strcmp(t_str, "ota") == 0) {

            const cJSON *url_item = cJSON_GetObjectItem(root, "url");
            const cJSON *size_item = cJSON_GetObjectItem(root, "size");
            const cJSON *md5_item = cJSON_GetObjectItem(root, "md5");
            if (cJSON_IsString(url_item) && url_item->valuestring && strlen(url_item->valuestring) > 7) {
                size_t expected_size = cJSON_IsNumber(size_item) ? size_item->valueint : 0;
                const char *expected_md5 = cJSON_IsString(md5_item) ? md5_item->valuestring : NULL;
                ESP_LOGI(TAG, "🚀 [WS OTA] Trigger received: URL='%s', size=%zu, md5=%s",
                         url_item->valuestring, expected_size, expected_md5 ? expected_md5 : "none");
                ota_updater_start_http_pull(url_item->valuestring, expected_size, expected_md5);
            }
            cJSON_Delete(root);
            free(json_str);
            return;
        }
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

                led2_set(true);
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
        const cJSON *follow_up_item = cJSON_GetObjectItem(root, "follow_up");
        if (cJSON_IsBool(follow_up_item)) {
            pending_followup = cJSON_IsTrue(follow_up_item);
            ESP_LOGI(TAG, "Follow-up required from command_result: %s", pending_followup ? "YES" : "NO");
        }
        ESP_LOGI(TAG, "🎯 Command result: verify=%s, reply=%s, follow_up=%s",
                 cJSON_IsString(verify) ? verify->valuestring : "null",
                 cJSON_IsString(reply) ? reply->valuestring : "null",
                 pending_followup ? "true" : "false");

        if (!cJSON_IsString(reply) || strlen(reply->valuestring) == 0) {
            ESP_LOGI(TAG, "No voice reply expected, resetting state to IDLE");
            ws_state = WS_STATE_IDLE;
            led2_set(false);
        }
    }
    else if (strcmp(type_str, "suppressed") == 0) {
        ESP_LOGI(TAG, "🔇 Stream suppressed by Gateway Spatial Arbiter (another node dominant)");
        ws_audio_reset_state();
    }
    else if (strcmp(type_str, "audio_start") == 0) {

        const cJSON *size = cJSON_GetObjectItem(root, "size");
        int audio_size = cJSON_IsNumber(size) ? size->valueint : 0;
        ESP_LOGI(TAG, "🔊 Receiving TTS audio (%d bytes) for speaker playback", audio_size);

        xStreamBufferReset(spk_stream_buf);
        s_has_residual = false;
        s_last_op_code = 0;
        spk_audio_complete = false;
        ws_state = WS_STATE_PLAYING;

        xTaskNotifyGive(speaker_task_handle);

        led2_set(true);
    }
    else if (strcmp(type_str, "audio_end") == 0) {
        ESP_LOGI(TAG, "🔊 TTS audio transmission complete");

        if (s_has_residual && spk_stream_buf) {
            uint8_t pair[2] = { s_residual_byte, 0 };
            xStreamBufferSend(spk_stream_buf, pair, 2, pdMS_TO_TICKS(50));
            s_has_residual = false;
        }
        const cJSON *follow_up_item = cJSON_GetObjectItem(root, "follow_up");
        if (cJSON_IsBool(follow_up_item)) {
            pending_followup = cJSON_IsTrue(follow_up_item);
            ESP_LOGI(TAG, "Follow-up required from audio_end: %s", pending_followup ? "YES" : "NO");
        }
        spk_audio_complete = true;

    }
    else if (strcmp(type_str, "pong") == 0) {

    }
    else if (strcmp(type_str, "speaker_busy") == 0) {
        const cJSON *busy_item = cJSON_GetObjectItem(root, "busy");
        if (cJSON_IsBool(busy_item)) {
            s_speaker_busy = cJSON_IsTrue(busy_item);
            ESP_LOGI(TAG, "📢 Speaker busy status from Gateway: %s",
                     s_speaker_busy ? "BUSY (Microphone suppressed)" : "FREE (Ready)");
        }
    }
    else if (strcmp(type_str, "error") == 0) {
        const cJSON *msg = cJSON_GetObjectItem(root, "message");
        ESP_LOGW(TAG, "Pi error: %s",
                 cJSON_IsString(msg) ? msg->valuestring : "unknown");
        ws_state = WS_STATE_IDLE;
        led2_set(false);
    }

    cJSON_Delete(root);
    free(json_str);
}

static void audio_stream_task(void *arg)
{
    uint8_t send_buf[WS_SEND_BUF_SIZE];

    ESP_LOGI(TAG, "Audio stream task ready, waiting for WakeNet trigger...");

    while (1) {

        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        ESP_LOGI(TAG, "Stream task activated — sending mic PCM to Pi...");

        int silence_count = 0;
        int frame_count = 0;
        int speech_detected = 0;

        while (ws_state == WS_STATE_STREAMING && frame_count < MAX_STREAM_FRAMES) {

            size_t received = xStreamBufferReceive(mic_stream_buf, send_buf,
                                                    sizeof(send_buf),
                                                    pdMS_TO_TICKS(100));
            if (received == 0) {

                if (!ws_connected) break;
                continue;
            }

            int sent = esp_websocket_client_send_bin(ws_client,
                                                      (const char *)send_buf,
                                                      received,
                                                      pdMS_TO_TICKS(500));
            if (sent < 0) {
                ESP_LOGW(TAG, "WebSocket send failed, aborting stream");
                break;
            }

            frame_count++;

            int16_t *samples = (int16_t *)send_buf;
            int num_samples = received / sizeof(int16_t);
            int64_t energy = 0;

            for (int i = 0; i < num_samples; i++) {
                energy += (int64_t)samples[i] * samples[i];
            }
            if (num_samples > 0) {
                energy /= num_samples;
            }

            if (frame_count < VAD_IGNORE_FRAMES) {
                if (energy > VAD_SILENCE_ENERGY) {
                    speech_detected = 1;
                }
                continue;
            }

            if (energy > VAD_SILENCE_ENERGY) {
                speech_detected = 1;
                silence_count = 0;
            } else {
                silence_count++;
            }

            if (speech_detected && silence_count >= VAD_SILENCE_FRAMES) {
                ESP_LOGI(TAG, "VAD: Silence detected for 0.6s — ending recording");
                break;
            }

            if (!speech_detected && frame_count >= 250) {
                ESP_LOGI(TAG, "VAD: No speech detected for 5s — ending recording");
                break;
            }

            if (frame_count % 50 == 0) {
                ESP_LOGI(TAG, "Streaming: %d frames sent (%.1fs), energy=%lld",
                         frame_count, frame_count * 0.02f, (long long)energy);
            }
        }

        if (ws_state == WS_STATE_STREAMING) {
            ESP_LOGI(TAG, "🛑 Recording ended after %d frames (%.1fs).",
                     frame_count, frame_count * 0.02f);

            const char *stop_msg = "{\"type\":\"stop\"}";
            esp_websocket_client_send_text(ws_client, stop_msg,
                                           strlen(stop_msg),
                                           pdMS_TO_TICKS(2000));
            ws_state = WS_STATE_PROCESSING;

            led2_set(true);
            ESP_LOGI(TAG, "Waiting for Pi response...");
        }

        if (ws_state == WS_STATE_STREAMING) {
            ws_state = WS_STATE_IDLE;
            led2_set(false);
        }
    }
}

extern void speaker_enable(bool enable);

static void speaker_playback_task(void *arg)
{
    uint8_t play_buf[SPK_PLAY_BUF_SIZE];

    ESP_LOGI(TAG, "Speaker playback task ready, waiting for TTS audio...");

    while (1) {

        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        if (!spk_i2s_handle) {
            ESP_LOGW(TAG, "Speaker I2S handle not available, discarding audio");

            while (ws_state == WS_STATE_PLAYING) {
                size_t n = xStreamBufferReceive(spk_stream_buf, play_buf,
                                                sizeof(play_buf),
                                                pdMS_TO_TICKS(500));
                if (n == 0 && spk_audio_complete) break;
            }
            ws_state = WS_STATE_IDLE;
            led2_set(false);
            continue;
        }

        if (!audio_feedback_lock(pdMS_TO_TICKS(2000))) {
            ESP_LOGW(TAG, "Could not acquire speaker lock for playback");
            ws_state = WS_STATE_IDLE;
            led2_set(false);
            continue;
        }

        ESP_LOGI(TAG, "🔊 Preparing speaker playback...");

        {
            int prefill_wait = 0;
            while (xStreamBufferBytesAvailable(spk_stream_buf) < 4096 && prefill_wait < 25) {
                vTaskDelay(pdMS_TO_TICKS(10));
                prefill_wait++;
                if (spk_audio_complete) break;
            }
            ESP_LOGI(TAG, "Pre-fill: %d bytes buffered in %dms",
                     (int)xStreamBufferBytesAvailable(spk_stream_buf), prefill_wait * 10);
        }

        {
            uint8_t silence[SPK_PLAY_BUF_SIZE];
            memset(silence, 0, sizeof(silence));
            size_t dummy = 0;
            for (int i = 0; i < 2; i++) {
                i2s_channel_write(spk_i2s_handle, silence, sizeof(silence), &dummy, pdMS_TO_TICKS(50));
            }
        }

        speaker_enable(true);
        vTaskDelay(pdMS_TO_TICKS(15));

        int total_played = 0;
        int empty_wait_count = 0;

        while (ws_state == WS_STATE_PLAYING) {
            size_t received = xStreamBufferReceive(spk_stream_buf, play_buf,
                                                    sizeof(play_buf),
                                                    pdMS_TO_TICKS(200));
            if (received > 0) {
                empty_wait_count = 0;
                size_t aligned_to_write = received & ~1;
                if (aligned_to_write > 0) {
                    size_t bytes_written = 0;
                    esp_err_t err = i2s_channel_write(spk_i2s_handle, play_buf,
                                                       aligned_to_write, &bytes_written,
                                                       pdMS_TO_TICKS(1000));
                    if (err != ESP_OK) {
                        ESP_LOGW(TAG, "I2S speaker write error: %s", esp_err_to_name(err));
                    }
                    total_played += bytes_written;
                }
            } else {

                if (spk_audio_complete) {
                    ESP_LOGI(TAG, "Speaker playback complete. Played %d bytes (%.2fs)",
                             total_played, (float)total_played / (16000 * 2));
                    break;
                }
                empty_wait_count++;
                if (empty_wait_count >= 15) {
                    ESP_LOGW(TAG, "Speaker playback timed out waiting for audio data");
                    break;
                }
            }
        }

        memset(play_buf, 0, sizeof(play_buf));
        for (int i = 0; i < 4; i++) {
            size_t dummy = 0;
            i2s_channel_write(spk_i2s_handle, play_buf, sizeof(play_buf), &dummy, pdMS_TO_TICKS(50));
        }
        vTaskDelay(pdMS_TO_TICKS(50));

        speaker_enable(false);
        audio_feedback_unlock();

        ws_state = WS_STATE_IDLE;

        if (pending_followup) {
            pending_followup = false;
            ESP_LOGW(TAG, "🔄 Follow-Up Active: Continuous listening without 'Hi ESP'...");
            led2_set(true);
            audio_feedback_play(AUDIO_FB_WAKEUP);
            vTaskDelay(pdMS_TO_TICKS(100));
            ws_audio_start_stream();
        } else {
            led2_set(false);
            ESP_LOGI(TAG, "🎙️ Ready for next voice command. Say 'Hi ESP'...");
        }
    }
}

void ws_audio_client_reconnect(void)
{
    if (ws_client && (!ws_connected || !esp_websocket_client_is_connected(ws_client))) {
        ws_connected = false;
        esp_websocket_client_stop(ws_client);
        vTaskDelay(pdMS_TO_TICKS(50));
        esp_err_t err = esp_websocket_client_start(ws_client);
        ESP_LOGI(TAG, "🔄 Auto-reconnecting WebSocket: %s", esp_err_to_name(err));
    }
}

void ws_audio_reset_state(void)
{
    ws_state = WS_STATE_IDLE;
    spk_audio_complete = true;
    s_has_residual = false;
    s_last_op_code = 0;
    led2_set(false);
    if (mic_stream_buf) xStreamBufferReset(mic_stream_buf);
    if (spk_stream_buf) xStreamBufferReset(spk_stream_buf);
    ESP_LOGI(TAG, "Audio state manually reset to IDLE");
}

void ws_audio_set_state(ws_audio_state_t state)
{
    ws_state = state;
    if (state == WS_STATE_IDLE) {
        led2_set(false);
    }
}

bool ws_audio_is_speaker_busy(void)
{
    return s_speaker_busy;
}
