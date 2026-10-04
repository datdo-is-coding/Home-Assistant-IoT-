/**
 * @file ws_asr.cpp
 * @brief High-Performance WebSocket Streaming ASR Client for Pi 4 (Sherpa-ONNX) Implementation
 */

#include "ws_asr.h"
#include "esp_log.h"
#include "cJSON.h"
#include <cstring>
#include <cstdio>
#include "storage/security_config.h"
#include "esp_timer.h"

static const char* TAG = "WS_ASR";

WsASR::WsASR(const std::string& ws_uri, const std::string& node_id)
    : m_uri(ws_uri),
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
    if (m_client) {
        esp_websocket_client_stop(m_client);
        esp_websocket_client_destroy(m_client);
        m_client = nullptr;
    }
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
    const auto token = SecurityConfig::get("ws_token");

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
    std::lock_guard<std::mutex> lock(m_mutex);
    m_has_final = false;
    m_has_partial = false;
    m_final_result.clear();
    m_partial_result.clear();
    m_confidence = 0.0f;
    m_send_buf_count = 0;

    if (m_result_sem) {
        xSemaphoreTake(m_result_sem, 0); // Drain any stale semaphore
    }

    if (!m_client || !m_connected.load()) {
        ESP_LOGW(TAG, "Cannot start ASR stream: WebSocket not yet connected to Gateway at %s", m_uri.c_str());
        return false;
    }

    if (m_source_node_id.empty() || m_source_node_id.size() > 31 ||
        m_source_node_id.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-") != std::string::npos) {
        ESP_LOGE(TAG, "Cannot relay audio without a valid ActionBox source ID");
        return false;
    }
    char start_msg[256];
    snprintf(start_msg, sizeof(start_msg),
             "{\"type\":\"start\",\"codec\":\"pcm\",\"sample_rate\":16000,\"node_id\":\"%s\",\"speaker\":false,\"audio_relay\":true,\"asr_only\":false}",
             m_source_node_id.c_str());

    int sent = esp_websocket_client_send_text(m_client, start_msg, strlen(start_msg), pdMS_TO_TICKS(1000));
    if (sent != (int)strlen(start_msg)) {
        ESP_LOGE(TAG, "Failed to send START to Pi 4 ASR!");
        return false;
    }

    m_streaming = true;
    ESP_LOGI(TAG, "PCM relay started from %s -> Pi 4 owns ASR and command processing", m_source_node_id.c_str());
    return true;
}

void WsASR::cancel() {
    if (m_streaming.load() && m_client && m_connected.load()) {
        const char* message = "{\"type\":\"cancel\"}";
        esp_websocket_client_send_text(m_client, message, strlen(message), pdMS_TO_TICKS(1000));
    }
    reset();
}

void WsASR::stop() {
    if (!m_streaming.load()) return;

    {
        std::lock_guard<std::mutex> lock(m_mutex);
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
    if (!pcm || samples == 0 || !m_streaming.load() || !m_client || !m_connected.load()) {
        return false;
    }

    std::lock_guard<std::mutex> lock(m_mutex);
    for (size_t i = 0; i < samples; i++) {
        m_send_buf[m_send_buf_count++] = pcm[i];
        if (m_send_buf_count >= 480) { // 480 samples = 30ms = 960 bytes
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
    std::lock_guard<std::mutex> lock(m_mutex);
    m_streaming = false;
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
            // Send compact hello
            {
                char hello[192];
                snprintf(hello, sizeof(hello),
                         "{\"t\":\"hello\",\"id\":\"%s\",\"speaker\":false,\"audio_relay\":true,\"asr_only\":false,\"rl\":[0,0],\"cfg\":1}",
                         self->m_node_id.c_str());
                esp_websocket_client_send_text(self->m_client, hello, strlen(hello), pdMS_TO_TICKS(1000));
            }
            break;

        case WEBSOCKET_EVENT_CLOSED:
        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "⚠️ Disconnected from Pi 4 Audio Server");
            self->m_connected = false;
            self->m_disconnected_at = esp_timer_get_time();
            self->m_streaming = false;
            break;

        case WEBSOCKET_EVENT_DATA:
            if (data->op_code == 0x01 && data->data_ptr && data->data_len > 0) { // Text frame
                self->handleTextMessage(data->data_ptr, data->data_len);
            }
            break;

        case WEBSOCKET_EVENT_ERROR:
            ESP_LOGE(TAG, "❌ WebSocket error occurred");
            break;

        default:
            break;
    }
}

void WsASR::handleTextMessage(const char* data, int len) {
    cJSON* root = cJSON_ParseWithLength(data, len);
    if (!root) return;

    cJSON* type = cJSON_GetObjectItem(root, "type");
    if (cJSON_IsString(type)) {
        if (strcmp(type->valuestring, "transcript") == 0) {
            cJSON* text = cJSON_GetObjectItem(root, "text");
            cJSON* conf = cJSON_GetObjectItem(root, "confidence");
            float confidence = (conf && cJSON_IsNumber(conf)) ? (float)conf->valuedouble : 1.0f;

            if (cJSON_IsString(text) && text->valuestring) {
                std::lock_guard<std::mutex> lock(m_mutex);
                // Fail closed if the Gateway does not explicitly accept recognition.
                const bool accepted = cJSON_IsTrue(cJSON_GetObjectItem(root, "accepted"));
                m_final_result = accepted ? text->valuestring : "";
                m_confidence = confidence;
                m_has_final = true;

                ESP_LOGI(TAG, "📢 [REAL VIETNAMESE ASR] Decoded: \"%s\" (Confidence: %.2f)",
                         m_final_result.c_str(), m_confidence);

                if (m_result_sem) {
                    xSemaphoreGive(m_result_sem);
                }
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
