#include "ws_asr.h"
#include "infrared/infrared.h"
#include "config/board_pins.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "cJSON.h"
#include <cstring>
#include <cstdio>
#include "storage/security_config.h"
#include "esp_timer.h"
#include "hc_runtime.h"
#include "hc_provisioning.h"
#include "esp_random.h"
#include "audio_output/sound_player.h"

static const char* TAG = "WS_ASR";

WsASR::WsASR(const std::string& ws_uri, const std::string& node_id, bool pi_voice)
    : m_uri(ws_uri),
      m_pi_voice(pi_voice),
      m_node_id(node_id),
      m_client(nullptr),
      m_connected(false),
      m_streaming(false),
      m_confidence(0.0f),
      m_has_final(false),
      m_has_partial(false),
      m_result_sem(nullptr),
      m_send_buf_count(0) {
    m_result_sem = xSemaphoreCreateBinary();
}

WsASR::~WsASR() {
    infrared_unbind(this);
    if (m_client) {
        esp_websocket_client_stop(m_client);
        esp_websocket_client_destroy(m_client);
        m_client = nullptr;
    }
    heap_caps_free(m_text_message);
    if (m_result_sem) {
        vSemaphoreDelete(m_result_sem);
        m_result_sem = nullptr;
    }
}

bool WsASR::init() {
    ESP_LOGI(TAG, "Initializing WebSocket ASR client -> %s (node: %s)...",
             m_uri.c_str(), m_node_id.c_str());

    m_disconnected_at = esp_timer_get_time();
    std::string sec_uri = SecurityConfig::get("ws_uri");
    if (!sec_uri.empty()) {
        m_uri = sec_uri;
    }
    m_ca = SecurityConfig::get("ca_pem");
    auto token = SecurityConfig::get("ws_token");

    hc_provisioned_config enrollment{};
    m_core_identity = hc_provisioning_load(&enrollment) == ESP_OK && enrollment.subbox;
    m_core_playback = m_core_identity && !m_pi_voice;
    if (m_core_identity) {
        char derived[65]{};
        if (!enrollment.committed || m_ca.empty() || hc_provisioning_speaker_token(derived) != ESP_OK ||
                strncmp(enrollment.mqtt_uri, "mqtts://", 8) != 0) {
            memset(&enrollment, 0, sizeof(enrollment));
            ESP_LOGE(TAG, "Core speaker requires committed identity and pinned Gateway CA");
            return false;
        }
        std::string host(enrollment.mqtt_uri + 8);
        host = host.substr(0, host.find_first_of(":/"));
        if (host.empty() || host.size() > 63 || host.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-") != std::string::npos) {
            memset(&enrollment, 0, sizeof(enrollment));memset(derived, 0, sizeof(derived));return false;
        }
        m_node_id = "SB" + std::string(enrollment.factory_id + 3, 12);
        m_uri = "wss://" + host + ":8765/ws/audio";
        token = derived;
        memset(derived, 0, sizeof(derived));
    }
    memset(&enrollment, 0, sizeof(enrollment));

    bool is_wss = (m_uri.rfind("wss://", 0) == 0);
    bool is_ws = (m_uri.rfind("ws://", 0) == 0);
    if (!is_wss && !is_ws) {
        ESP_LOGE(TAG, "Invalid WS URI scheme: %s", m_uri.c_str());
        return false;
    }

    if (is_wss && (m_ca.empty() || token.empty())) {
        ESP_LOGE(TAG, "WSS unavailable: provision URI, pinned CA and per-device token over USB");
        return false;
    }

    if (!token.empty()) {
        m_headers = "Authorization: Bearer " + token + "\r\nX-Device-ID: " + m_node_id + "\r\n";
    } else {
        m_headers = "X-Device-ID: " + m_node_id + "\r\n";
    }

    if (m_core_identity) {
        m_ir_available = infrared_bind(this, [](void* owner, const char* message, size_t length) {
            auto* self = static_cast<WsASR*>(owner);
            std::lock_guard<std::mutex> lock(self->m_send_mutex);
            return self->m_client && self->m_connected.load() &&
                esp_websocket_client_send_text(self->m_client, message, length, pdMS_TO_TICKS(1000)) == static_cast<int>(length);
        });
    }
    esp_websocket_client_config_t ws_cfg = {};
    if (is_wss) {
        ws_cfg.cert_pem = m_ca.c_str();
    }
    ws_cfg.headers = m_headers.c_str();
    ws_cfg.uri = m_uri.c_str();
    ws_cfg.buffer_size = 4096;
    ws_cfg.reconnect_timeout_ms = 3000;
    ws_cfg.network_timeout_ms = 10000;
    ws_cfg.ping_interval_sec = 15;
    ws_cfg.pingpong_timeout_sec = 30;
    ws_cfg.disable_auto_reconnect = false;
    ws_cfg.enable_close_reconnect = true;

    m_client = esp_websocket_client_init(&ws_cfg);
    if (!m_client) {
        ESP_LOGE(TAG, "Failed to create WebSocket client handle!");
        return false;
    }

    esp_err_t err = esp_websocket_register_events(m_client, WEBSOCKET_EVENT_ANY, wsEventHandler, this);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register WebSocket event handler: %s", esp_err_to_name(err));
        return false;
    }

    err = esp_websocket_client_start(m_client);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "WebSocket client start returned: %s (will retry upon Wi-Fi connection)", esp_err_to_name(err));
    }

    return true;
}

void WsASR::setSourceNodeId(const char* node_id) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_source_node_id = node_id ? node_id : "";
}

bool WsASR::start() {
    if (m_core_playback) return false;
    std::lock_guard<std::mutex> send_lock(m_send_mutex);
    std::string source_node_id;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        source_node_id = m_source_node_id;
        m_has_final = false;
        m_has_partial = false;
        m_final_result.clear();
        m_partial_result.clear();
        m_confidence = 0.0f;
    }
    m_streaming = false;
    m_send_buf_count = 0;

    if (m_result_sem) {
        xSemaphoreTake(m_result_sem, 0);
    }

    if (!m_client || !m_connected.load()) {
        ESP_LOGW(TAG, "Cannot start ASR stream: WebSocket not yet connected to Gateway at %s", m_uri.c_str());
        return false;
    }

    if (source_node_id.empty() || source_node_id.size() > 31 ||
        source_node_id.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-") != std::string::npos) {
        ESP_LOGE(TAG, "Cannot relay audio without a valid ActionBox source ID");
        return false;
    }
    char start_msg[320];
    if (m_core_identity || hc_runtime_enabled()) {
        if (!hc_runtime_registered() || source_node_id.find_first_not_of("0123456789") != std::string::npos) return false;
        uint32_t nonce[4];
        esp_fill_random(nonce, sizeof(nonce));
        snprintf(start_msg, sizeof(start_msg),
                 "{\"type\":\"start\",\"codec\":\"pcm\",\"sample_rate\":16000,\"source_node_id\":%s,\"request_id\":\"%08lx%08lx%08lx%08lx\"}",
                 source_node_id.c_str(), (unsigned long)nonce[0], (unsigned long)nonce[1],
                 (unsigned long)nonce[2], (unsigned long)nonce[3]);
    } else snprintf(start_msg, sizeof(start_msg),
             "{\"type\":\"start\",\"codec\":\"pcm\",\"sample_rate\":16000,\"node_id\":\"%s\",\"speaker\":false,\"audio_relay\":true,\"asr_only\":false}",
             source_node_id.c_str());

    int sent = esp_websocket_client_send_text(m_client, start_msg, strlen(start_msg), pdMS_TO_TICKS(1000));
    if (sent != (int)strlen(start_msg)) {
        ESP_LOGE(TAG, "Failed to send START to Pi 4 ASR!");
        return false;
    }

    m_streaming = true;
    ESP_LOGI(TAG, "PCM relay started from %s -> Pi 4 owns ASR and command processing", source_node_id.c_str());
    return true;
}

void WsASR::cancel() {
    {
        std::lock_guard<std::mutex> send_lock(m_send_mutex);
        if (m_streaming.load() && m_client && m_connected.load()) {
            const char* message = "{\"type\":\"cancel\"}";
            esp_websocket_client_send_text(m_client, message, strlen(message), pdMS_TO_TICKS(1000));
        }
    }
    reset();
}

void WsASR::stop() {
    std::lock_guard<std::mutex> send_lock(m_send_mutex);
    if (!m_streaming.load()) return;

    {
        if (m_send_buf_count > 0 && m_client && m_connected.load()) {
            int sent = esp_websocket_client_send_bin(
                m_client,
                reinterpret_cast<const char*>(m_send_buf),
                m_send_buf_count * sizeof(int16_t),
                pdMS_TO_TICKS(1000)
            );
            if (sent != (int)(m_send_buf_count * sizeof(int16_t))) {
                const char* cancel_msg = "{\"type\":\"cancel\"}";
                esp_websocket_client_send_text(m_client, cancel_msg, strlen(cancel_msg), pdMS_TO_TICKS(1000));
                m_streaming = false;
                m_send_buf_count = 0;
                return;
            }
            m_send_buf_count = 0;
        }
    }

    m_streaming = false;

    if (m_client && m_connected.load()) {
        const char* stop_msg = "{\"type\":\"stop\"}";
        int sent = esp_websocket_client_send_text(m_client, stop_msg, strlen(stop_msg), pdMS_TO_TICKS(2000));
        if (sent >= 0) {
            ESP_LOGI(TAG, "🛑 Sent STOP to Pi 4 ASR -> Waiting for Sherpa-ONNX transcription...");
        } else {
            ESP_LOGW(TAG, "Failed to send STOP to Pi 4 ASR");
        }
    }
}

bool WsASR::feedAudio(const int16_t* pcm, size_t samples) {
    std::lock_guard<std::mutex> send_lock(m_send_mutex);
    if (!pcm || samples == 0 || !m_streaming.load() || !m_client || !m_connected.load()) {
        return false;
    }

    for (size_t i = 0; i < samples; i++) {
        m_send_buf[m_send_buf_count++] = pcm[i];
        if (m_send_buf_count >= 480) {
            int sent = esp_websocket_client_send_bin(
                m_client,
                reinterpret_cast<const char*>(m_send_buf),
                m_send_buf_count * sizeof(int16_t),
                pdMS_TO_TICKS(1000)
            );
            m_send_buf_count = 0;
            if (sent != (int)sizeof(m_send_buf)) return false;
        }
    }
    return true;
}

bool WsASR::hasPartialResult() const {
    return m_has_partial.load();
}

bool WsASR::hasFinalResult() const {
    return m_has_final.load();
}

const char* WsASR::getPartialResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_partial_result.c_str();
}

const char* WsASR::getFinalResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_final_result.c_str();
}

void WsASR::reset() {
    std::lock_guard<std::mutex> send_lock(m_send_mutex);
    std::lock_guard<std::mutex> lock(m_mutex);
    m_streaming = false;
    if (m_receiving_tts.exchange(false)) {
        SoundPlayer::instance().finishPcmStream();
    }
    m_has_final = false;
    m_has_partial = false;
    m_final_result.clear();
    m_partial_result.clear();
    m_confidence = 0.0f;
    m_send_buf_count = 0;
    if (m_result_sem) {
        xSemaphoreTake(m_result_sem, 0);
    }
}

bool WsASR::waitForFinalResult(uint32_t timeout_ms) {
    if (m_has_final.load()) return true;
    if (!m_result_sem) return false;

    if (xSemaphoreTake(m_result_sem, pdMS_TO_TICKS(timeout_ms)) == pdTRUE) {
        return m_has_final.load();
    }

    ESP_LOGW(TAG, "⏱️ Timed out waiting for Pi 4 ASR transcript (%lu ms)", (unsigned long)timeout_ms);
    return false;
}

void WsASR::wsEventHandler(void* handler_args, esp_event_base_t base, int32_t event_id, void* event_data) {
    auto* self = static_cast<WsASR*>(handler_args);
    auto* data = static_cast<esp_websocket_event_data_t*>(event_data);

    switch (event_id) {
        case WEBSOCKET_EVENT_CONNECTED:
            ESP_LOGI(TAG, "✅ Connected to Pi 4 Audio Server (%s)!", self->m_uri.c_str());
            self->m_connected = true;
            infrared_session(self, ++self->m_ir_generation);

            {
                char hello[280];
                snprintf(hello, sizeof(hello),
                         "{\"t\":\"hello\",\"id\":\"%s\",\"speaker\":true,\"playback_only\":%s,\"audio_relay\":true,\"asr_only\":false,\"rl\":[0,0],\"cfg\":1,\"infrared\":{\"version\":2,\"tx\":%s,\"rx\":%s,\"rx_supported\":true}}",
                         self->m_node_id.c_str(), self->m_core_playback ? "true" : "false",
                         self->m_ir_available ? "true" : "false", (self->m_ir_available && BOARD_IR_RX_ENABLED) ? "true" : "false");
                esp_websocket_client_send_text(self->m_client, hello, strlen(hello), pdMS_TO_TICKS(1000));
            }
            break;

        case WEBSOCKET_EVENT_CLOSED:
        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "⚠️ Disconnected from Pi 4 Audio Server");
            self->m_connected = false;
            infrared_session(self, ++self->m_ir_generation);
            self->m_disconnected_at = esp_timer_get_time();
            self->m_streaming = false;
            if (self->m_receiving_tts.exchange(false)) {
                SoundPlayer::instance().finishPcmStream();
            }
            break;

        case WEBSOCKET_EVENT_DATA:
            if ((data->op_code == 0x01 || (data->op_code == 0 && self->m_text_message)) && data->data_ptr && data->data_len > 0) {
                if (data->payload_offset == 0) {
                    heap_caps_free(self->m_text_message); self->m_text_message = nullptr;
                    self->m_text_received = 0; self->m_text_expected = data->payload_len;
                    if (data->payload_len > 4096 || data->payload_len < data->data_len) break;
                    if (data->payload_len == data->data_len) {
                        self->handleTextMessage(data->data_ptr, data->data_len); break;
                    }
                    self->m_text_message = static_cast<char*>(heap_caps_malloc(data->payload_len + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
                }
                if (self->m_text_message && static_cast<size_t>(data->payload_offset) == self->m_text_received &&
                    self->m_text_received + data->data_len <= self->m_text_expected) {
                    memcpy(self->m_text_message + self->m_text_received, data->data_ptr, data->data_len);
                    self->m_text_received += data->data_len;
                    if (self->m_text_received == self->m_text_expected) {
                        self->m_text_message[self->m_text_expected] = 0;
                        self->handleTextMessage(self->m_text_message, self->m_text_expected);
                        heap_caps_free(self->m_text_message); self->m_text_message = nullptr;
                    }
                }
            } else if (data->op_code == 0x02 && data->data_ptr && data->data_len > 0) {
                if (self->m_receiving_tts.load()) {
                    size_t samples = data->data_len / sizeof(int16_t);
                    self->m_playback_bytes += data->data_len;
                    if ((data->data_len & 1) || (self->m_playback_bytes > self->m_playback_expected && self->m_core_identity) ||
                            !SoundPlayer::instance().streamPcmChunk(reinterpret_cast<const int16_t*>(data->data_ptr), samples)) {
                        self->m_playback_ok = false;
                    }
                }
            }
            break;

        case WEBSOCKET_EVENT_ERROR:
            ESP_LOGE(TAG, "❌ WebSocket error occurred");
            if (self->m_receiving_tts.exchange(false)) {
                SoundPlayer::instance().finishPcmStream();
            }
            break;

        default:
            break;
    }
}

void WsASR::handleTextMessage(const char* data, int len) {
    cJSON* root = cJSON_ParseWithLength(data, len);
    const char* ir_type = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(root, "type"));
    if (root && ir_type && (!strcmp(ir_type, "ir_send") || !strcmp(ir_type, "ir_learn") || !strcmp(ir_type, "ir_prepare"))) {
        if (m_ir_available && m_core_identity && hc_runtime_registered() && m_connected.load())
            infrared_submit(this, m_ir_generation, root);
        cJSON_Delete(root); return;
    }

    if (!root) return;

    cJSON* type = cJSON_GetObjectItem(root, "type");
    if (cJSON_IsString(type)) {
        if (strcmp(type->valuestring, "transcript") == 0) {
            cJSON* text = cJSON_GetObjectItem(root, "text");
            cJSON* conf = cJSON_GetObjectItem(root, "confidence");
            float confidence = (conf && cJSON_IsNumber(conf)) ? (float)conf->valuedouble : 1.0f;
            const bool accepted = cJSON_IsTrue(cJSON_GetObjectItem(root, "accepted"));

            if (cJSON_IsString(text) && text->valuestring) {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_final_result = accepted ? text->valuestring : "";
                m_confidence = confidence;
                m_has_final = true;

                ESP_LOGI(TAG, "📢 [REAL VIETNAMESE ASR] Decoded: \"%s\" (Confidence: %.2f, Accepted: %d)",
                         m_final_result.c_str(), m_confidence, accepted);

                if (m_result_sem) {
                    xSemaphoreGive(m_result_sem);
                }
            }

            if (!accepted) {
                ESP_LOGW(TAG, "ASR transcript rejected -> Triggering acoustic error feedback");
                SoundPlayer::instance().play(SoundType::ERROR);
            }
        } else if (strcmp(type->valuestring, "audio_start") == 0) {
            cJSON* fmt = cJSON_GetObjectItem(root, "format");
            if (!fmt || !cJSON_IsString(fmt) || strcmp(fmt->valuestring, "pcm") != 0) {
                ESP_LOGW(TAG, "Rejecting audio_start: unsupported format");
                cJSON_Delete(root);
                return;
            }
            ESP_LOGI(TAG, "🔊 Incoming TTS audio stream starting from Gateway...");
            const auto* id = cJSON_GetObjectItem(root, "playback_id");
            const auto* size = cJSON_GetObjectItem(root, "size");
            m_playback_id = cJSON_IsString(id) ? id->valuestring : "";
            m_playback_expected = cJSON_IsNumber(size) && size->valuedouble > 0 && size->valuedouble <= 256000 &&
                static_cast<unsigned>(size->valuedouble) == size->valuedouble ? static_cast<size_t>(size->valuedouble) : 0;
            const auto* rate = cJSON_GetObjectItem(root, "sample_rate");
            const auto* channels = cJSON_GetObjectItem(root, "channels");
            const auto* width = cJSON_GetObjectItem(root, "sample_width");
            if (m_core_identity && (m_playback_id.size() != 32 || m_playback_id.find_first_not_of("0123456789abcdef") != std::string::npos ||
                    !m_playback_expected || (m_playback_expected & 1) || !cJSON_IsNumber(rate) || rate->valuedouble != 16000 ||
                    !cJSON_IsNumber(channels) || channels->valuedouble != 1 || !cJSON_IsNumber(width) || width->valuedouble != 2)) {
                cJSON_Delete(root);return;
            }
            m_playback_bytes = 0;
            m_playback_ok = SoundPlayer::instance().startPcmStream();
            m_receiving_tts = m_playback_ok;
        } else if (strcmp(type->valuestring, "audio_end") == 0) {
            ESP_LOGI(TAG, "🏁 Incoming TTS audio stream finished.");
            if (m_receiving_tts.exchange(false)) {
                m_playback_ok = SoundPlayer::instance().finishPcmStream() && m_playback_ok;
                const auto* id = cJSON_GetObjectItem(root, "playback_id");
                if (m_core_identity && cJSON_IsString(id) && m_playback_id == id->valuestring) {
                    char reply[192];
                    snprintf(reply,sizeof(reply),"{\"type\":\"playback_complete\",\"playback_id\":\"%s\",\"success\":%s,\"received_bytes\":%u}",
                             m_playback_id.c_str(),m_playback_ok && m_playback_bytes==m_playback_expected ? "true" : "false",static_cast<unsigned>(m_playback_bytes));
                    std::lock_guard<std::mutex> send_lock(m_send_mutex);
                    esp_websocket_client_send_text(m_client,reply,strlen(reply),pdMS_TO_TICKS(1000));
                }
                const auto* command = cJSON_GetObjectItem(root, "follow_up_command");
                if (cJSON_IsTrue(cJSON_GetObjectItem(root, "follow_up")) && cJSON_IsString(command)) {
                    std::function<void(const std::string&)> callback;
                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        callback = m_followup_cb;
                    }
                    if (callback) callback(command->valuestring);
                }
            }
        } else if (strcmp(type->valuestring, "kws_playback_done") == 0) {
            std::function<void(const std::string&)> callback;
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                callback = m_playback_done_cb;
            }
            if (callback) callback(std::string(data, static_cast<size_t>(len)));
        } else if (strcmp(type->valuestring, "speaker_busy") == 0) {
            cJSON* busy = cJSON_GetObjectItem(root, "busy");
            bool is_busy = busy && cJSON_IsTrue(busy);
            ESP_LOGI(TAG, "📢 Speaker busy status: %d", is_busy);
        } else if (strcmp(type->valuestring, "suppressed") == 0) {
            cJSON* reason = cJSON_GetObjectItem(root, "reason");
            const char* r_str = (reason && cJSON_IsString(reason)) ? reason->valuestring : "spatial_arbiter";
            ESP_LOGI(TAG, "Audio stream suppressed by Gateway (%s)", r_str);
            m_streaming = false;
            if (m_result_sem) {
                xSemaphoreGive(m_result_sem);
            }
        } else if (strcmp(type->valuestring, "command_result") == 0) {
            cJSON* verify = cJSON_GetObjectItem(root, "verify");
            cJSON* reply = cJSON_GetObjectItem(root, "voice_reply");
            bool has_tts = cJSON_IsTrue(cJSON_GetObjectItem(root, "has_tts"));
            const char* v_str = cJSON_IsString(verify) ? verify->valuestring : "";
            const char* r_str = cJSON_IsString(reply) ? reply->valuestring : "";

            ESP_LOGI(TAG, "🎯 [COMMAND_RESULT] Verify: \"%s\" | Reply: \"%s\" | has_tts: %d", v_str, r_str, has_tts);

            if (strcmp(v_str, "success") == 0 || strcmp(v_str, "alarm_played") == 0 ||
                strcmp(v_str, "conversational") == 0 || strcmp(v_str, "ack_only") == 0 ||
                strcmp(v_str, "confirmed_load") == 0 || strcmp(v_str, "already_in_state") == 0) {
                if (!has_tts) {
                    ESP_LOGI(TAG, "Acoustic feedback: Command SUCCESS -> Melodic confirmation chime");
                    SoundPlayer::instance().play(SoundType::SUCCESS);
                } else {
                    ESP_LOGI(TAG, "Command SUCCESS with TTS -> Suppressing chime in favor of TTS speech");
                }
            } else {
                ESP_LOGW(TAG, "Acoustic feedback: Command FAILED (%s)", v_str);
                if (!has_tts) {
                    SoundPlayer::instance().play(SoundType::ERROR);
                }
            }

            CommandResultCallback cb_copy = nullptr;
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                cb_copy = m_cmd_result_cb;
            }
            if (cb_copy) {
                cb_copy(v_str, r_str);
            }
        } else if (strcmp(type->valuestring, "status") == 0) {
            cJSON* state = cJSON_GetObjectItem(root, "state");
            if (cJSON_IsString(state)) {
                ESP_LOGD(TAG, "Pi 4 status: %s", state->valuestring);
            }
        }
    }
    cJSON_Delete(root);
}
