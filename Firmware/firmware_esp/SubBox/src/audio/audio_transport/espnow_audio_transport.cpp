/**
 * @file espnow_audio_transport.cpp
 * @brief Reliable ESP-NOW Audio & Command Transport Implementation
 */

#include "espnow_audio_transport.h"
#include "esp_log.h"
#include "system/subbox_led.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include <cstring>
#include <algorithm>
#include "cJSON.h"
#include "storage/nvs_manager.h"

static const char* TAG = "ESPNOW_TRANSPORT";



EspNowAudioTransport* EspNowAudioTransport::s_instance = nullptr;

EspNowAudioTransport::EspNowAudioTransport()
    : m_running(false) {
    s_instance = this;
    m_ack_sem = xSemaphoreCreateBinary();
}

EspNowAudioTransport::~EspNowAudioTransport() {
    stop();
    if (m_ack_sem) vSemaphoreDelete(m_ack_sem);
    s_instance = nullptr;
}

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
void EspNowAudioTransport::onEspNowSend(const wifi_tx_info_t *tx_info, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS && tx_info) {
        ESP_LOGD(TAG, "ESP-NOW delivery status: %d to %02X:%02X:%02X:%02X:%02X:%02X",
                 status,
                 tx_info->des_addr[0], tx_info->des_addr[1], tx_info->des_addr[2],
                 tx_info->des_addr[3], tx_info->des_addr[4], tx_info->des_addr[5]);
    }
}
#else
void EspNowAudioTransport::onEspNowSend(const uint8_t *mac_addr, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS && mac_addr) {
        ESP_LOGD(TAG, "ESP-NOW delivery status: %d to %02X:%02X:%02X:%02X:%02X:%02X",
                 status,
                 mac_addr[0], mac_addr[1], mac_addr[2], mac_addr[3], mac_addr[4], mac_addr[5]);
    }
}
#endif

void EspNowAudioTransport::onEspNowRecv(const esp_now_recv_info_t *recv_info, const uint8_t *data, int len) {
    if (!recv_info || !data || len <= 0) return;
    if (!s_instance) return;

    bool is_broadcast = true;
    for (int i = 0; i < 6; i++) {
        if (recv_info->des_addr[i] != 0xFF) {
            is_broadcast = false;
            break;
        }
    }
    bool is_for_us = (memcmp(recv_info->des_addr, s_instance->m_local_mac, 6) == 0);
    if (!is_broadcast && !is_for_us) return;

    bool trusted = s_instance->m_trusted_peers.empty();
    for (const auto& peer : s_instance->m_trusted_peers) {
        if (memcmp(peer.mac, recv_info->src_addr, 6) == 0) {
            trusted = true;
            break;
        }
    }
    if (!trusted) return;

    if (s_instance->m_rx_queue && len <= 1470) {
        RxItem item{};
        memcpy(item.mac, recv_info->src_addr, 6);
        item.len = len;
        memcpy(item.data, data, len);
        xQueueSend(s_instance->m_rx_queue, &item, 0);
    }
}

void EspNowAudioTransport::receiveTask(void* arg) {
    auto* self = static_cast<EspNowAudioTransport*>(arg);
    RxItem item;
    while (true) {
        if (xQueueReceive(self->m_rx_queue, &item, portMAX_DELAY) == pdTRUE)
            self->handleReceivedPacket(item.mac, item.data, item.len);
    }
}

void EspNowAudioTransport::handleReceivedPacket(const uint8_t* mac, const uint8_t* data, int len) {
    if (!m_running || len <= 0) return;

    uint8_t msg_type = data[0];
    std::string source;
    if (msg_type >= 0x20 && msg_type <= 0x22) {
        std::lock_guard<std::mutex> lock(m_macs_mutex);
        for (const auto& entry : m_node_macs)
            if (entry.second.size() == 6 && memcmp(entry.second.data(), mac, 6) == 0) source = entry.first;
        if (source.empty()) return;
    }

    // Case 1: Audio START (0x20)
    if (msg_type == 0x20) {
        AudioPacket pkt = {};
        pkt.version = AUDIO_PROTOCOL_VERSION;
        pkt.msg_type = AUDIO_MSG_TYPE_STREAM_START;
        snprintf(pkt.source_node_id, sizeof(pkt.source_node_id), "%s", source.c_str());
        pkt.sequence_num = (len >= 2) ? data[1] : 0;
        pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        pkt.codec = AUDIO_CODEC_RAW_PCM;
        pkt.sample_rate = SUBBOX_AUDIO_SAMPLE_RATE;
        pkt.channels = 1;
        pkt.payload_len = 0;

        ESP_LOGI(TAG, "🎙️ [ESPNOW RX] Audio STREAM_START from %02X:%02X:%02X:%02X:%02X:%02X (Node: %s)",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], pkt.source_node_id);

        // Store peer MAC for unicast reply
        {
            std::lock_guard<std::mutex> lock(m_macs_mutex);
            m_node_macs[pkt.source_node_id] = std::vector<uint8_t>(mac, mac + 6);
        }

        std::lock_guard<std::mutex> lock(m_callback_mutex);
        if (m_rx_callback) {
            m_rx_callback(pkt);
        }
        return;
    }

    // Case 2: Audio CHUNK (0x21)
    if (msg_type == 0x21 && len >= 4) {
        uint8_t seq = data[1];
        uint16_t pcm_len = (uint16_t)data[2] | ((uint16_t)data[3] << 8);

        AudioPacket pkt = {};
        pkt.version = AUDIO_PROTOCOL_VERSION;
        pkt.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK;
        snprintf(pkt.source_node_id, sizeof(pkt.source_node_id), "%s", source.c_str());
        pkt.sequence_num = seq;
        pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        pkt.codec = AUDIO_CODEC_RAW_PCM;
        pkt.sample_rate = SUBBOX_AUDIO_SAMPLE_RATE;
        pkt.channels = 1;

        size_t available_bytes = (size_t)(len - 4);
        size_t copy_bytes = std::min((size_t)pcm_len, available_bytes);
        copy_bytes = std::min(copy_bytes, (size_t)SUBBOX_AUDIO_MAX_PACKET_PAYLOAD);

        pkt.payload_len = (uint16_t)copy_bytes;
        memcpy(pkt.payload, &data[4], copy_bytes);

        std::lock_guard<std::mutex> lock(m_callback_mutex);
        if (m_rx_callback) {
            m_rx_callback(pkt);
        }
        return;
    }

    // Case 3: Audio END (0x22)
    if (msg_type == 0x22) {
        AudioPacket pkt = {};
        pkt.version = AUDIO_PROTOCOL_VERSION;
        pkt.msg_type = AUDIO_MSG_TYPE_STREAM_END;
        snprintf(pkt.source_node_id, sizeof(pkt.source_node_id), "%s", source.c_str());
        pkt.sequence_num = (len >= 2) ? data[1] : 0;
        pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        pkt.payload_len = 0;

        ESP_LOGI(TAG, "🛑 [ESPNOW RX] Audio STREAM_END from ActionBox (Node: %s)", pkt.source_node_id);

        std::lock_guard<std::mutex> lock(m_callback_mutex);
        if (m_rx_callback) {
            m_rx_callback(pkt);
        }
        return;
    }

    // JSON carries the physical board identity; audio packets inherit it by MAC.
    if (data[0] == '{') {
        cJSON* root = cJSON_ParseWithLength(reinterpret_cast<const char*>(data), len);
        if (!root) return;
        const cJSON* node = cJSON_GetObjectItem(root, "node_id");
        const cJSON* uid = cJSON_GetObjectItem(root, "hardware_uid");
        const cJSON* version = cJSON_GetObjectItem(root, "protocol_version");
        char expected_uid[13];
        snprintf(expected_uid, sizeof(expected_uid), "%02X%02X%02X%02X%02X%02X", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
        if (!cJSON_IsNumber(version) || version->valueint != 3 || !cJSON_IsString(uid) ||
            strcmp(uid->valuestring, expected_uid) != 0) { cJSON_Delete(root); return; }
        if (cJSON_IsString(node) && strlen(node->valuestring) < 32) {
            {
                std::lock_guard<std::mutex> lock(m_macs_mutex);
                const auto known = m_node_macs.find(node->valuestring);
                if (known != m_node_macs.end() && memcmp(known->second.data(), mac, 6) != 0) {
                    m_conflicting_nodes.insert(node->valuestring);
                    m_node_macs.erase(known);
                    ESP_LOGE(TAG, "Duplicate board ID: %s; provision unique IDs before controlling", node->valuestring);
                }
                if (m_conflicting_nodes.count(node->valuestring) ||
                    (m_node_macs.count(node->valuestring) == 0 && m_node_macs.size() + m_conflicting_nodes.size() >= SUBBOX_MAX_ACTIONBOXES_PER_ROOM)) {
                    cJSON_Delete(root);
                    return;
                }
                m_node_macs[node->valuestring] = std::vector<uint8_t>(mac, mac + 6);
            }
            if (!esp_now_is_peer_exist(mac)) {
                esp_now_peer_info_t peer = {};
                memcpy(peer.peer_addr, mac, 6);
                peer.channel = 0;
                peer.ifidx = WIFI_IF_STA;
                peer.encrypt = false;
                esp_now_add_peer(&peer);
                ESP_LOGI(TAG, "Auto-registered ActionBox peer %02X:%02X:%02X:%02X:%02X:%02X (%s)",
                         mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], node->valuestring);
            }
            const cJSON* request = cJSON_GetObjectItem(root, "request_id");
            const cJSON* status = cJSON_GetObjectItem(root, "status");
            const cJSON* session = cJSON_GetObjectItem(root, "session_id");
            {
                std::lock_guard<std::mutex> lock(m_ack_mutex);
                if (cJSON_IsNumber(request) && cJSON_IsString(status) &&
                    m_pending_request != 0 && request->valuedouble == m_pending_request &&
                    cJSON_IsNumber(session) && session->valuedouble == m_pending_session &&
                    memcmp(mac, m_pending_mac, 6) == 0 && m_pending_node == node->valuestring) {
                    m_ack_json.assign(reinterpret_cast<const char*>(data), len);
                    m_ack_ok = strcmp(status->valuestring, "OK") == 0;
                    xSemaphoreGive(m_ack_sem);
                }
            }
            std::function<void(const std::string&)> callback;
            { std::lock_guard<std::mutex> lock(m_callback_mutex); callback = m_json_callback; }
            if (callback) callback(std::string(reinterpret_cast<const char*>(data), len));
        }
        cJSON_Delete(root);
    }
}

bool EspNowAudioTransport::init() {
    if (m_running) return true;
    m_rx_queue = xQueueCreate(32, sizeof(RxItem));
    if (!m_rx_queue) return false;
    if (xTaskCreate(receiveTask, "espnow_rx", 6144, this, 5, &m_rx_task) != pdPASS) {
        vQueueDelete(m_rx_queue);
        m_rx_queue = nullptr;
        return false;
    }

    ESP_LOGI(TAG, "Initializing SubBox ESP-NOW Audio Transport (following Wi-Fi STA channel)...");

    // Disable Wi-Fi power saving for minimal latency
    esp_wifi_set_ps(WIFI_PS_NONE);

    esp_err_t err = esp_now_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "esp_now_init failed: %s", esp_err_to_name(err));
        vTaskDelete(m_rx_task);
        vQueueDelete(m_rx_queue);
        m_rx_task = nullptr;
        m_rx_queue = nullptr;
        return false;
    }

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
    esp_now_register_send_cb(onEspNowSend);
#else
    esp_now_register_send_cb(onEspNowSend);
#endif
    esp_now_register_recv_cb(onEspNowRecv);

    esp_read_mac(m_local_mac, ESP_MAC_WIFI_STA);
    for (unsigned slot=0; slot<SUBBOX_MAX_ACTIONBOXES_PER_ROOM; ++slot) {
        TrustedPeer trusted{};
        if (!SecurityConfig::loadPeer(slot, trusted)) continue;
        esp_now_peer_info_t peer{};
        memcpy(peer.peer_addr, trusted.mac, 6);
        memcpy(peer.lmk, trusted.lmk, 16);
        peer.channel = 0;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = true;
        if (esp_now_add_peer(&peer) == ESP_OK) m_trusted_peers.push_back(trusted);
        else ESP_LOGE(TAG, "Failed to load encrypted peer slot %u", slot);
    }

    /* Register Broadcast Peer (FF:FF:FF:FF:FF:FF) */
    const uint8_t bcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    if (!esp_now_is_peer_exist(bcast_mac)) {
        esp_now_peer_info_t bcast_peer = {};
        memcpy(bcast_peer.peer_addr, bcast_mac, 6);
        bcast_peer.channel = 0;
        bcast_peer.ifidx = WIFI_IF_STA;
        bcast_peer.encrypt = false;
        esp_now_add_peer(&bcast_peer);
        ESP_LOGI(TAG, "Registered ESP-NOW broadcast peer.");
    }

    m_running = true;
    xTaskCreate(heartbeatTask, "peer_heartbeat", 4096, this, 3, &m_heartbeat_task);
    ESP_LOGI(TAG, "SubBox ESP-NOW Audio Transport fully active & listening for ActionBox.");
    return true;
}

void EspNowAudioTransport::heartbeatTask(void* arg) {
    auto* self = static_cast<EspNowAudioTransport*>(arg);
    SubBoxPersistentConfig cfg{};
    NVSManager::loadConfig(cfg);
    const uint8_t bcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

    while (self->m_running) {
        uint8_t channel=0; wifi_second_chan_t secondary;
        esp_wifi_get_channel(&channel, &secondary);
        char payload[192];
        int length = snprintf(payload, sizeof(payload), "{\"type\":\"heartbeat\",\"protocol_version\":3,\"subbox_id\":\"%s\",\"channel\":%u,\"wifi\":%s,\"mqtt\":%s}", cfg.subbox_id, channel, subbox_led_wifi_connected() ? "true" : "false", subbox_led_mqtt_connected() ? "true" : "false");

        /* Broadcast heartbeat to all ActionBoxes */
        esp_now_send(bcast_mac, reinterpret_cast<const uint8_t*>(payload), length);

        for (const auto& peer : self->m_trusted_peers)
            esp_now_send(peer.mac, reinterpret_cast<const uint8_t*>(payload), length);

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    vTaskDelete(nullptr);
}

bool EspNowAudioTransport::sendAudio(const char* target_node_id, const AudioPacket& packet) {
    if (!m_running) return false;
    // Note: ActionBoxes in this hardware revision do not have speakers enabled.
    // Suppress heavy audio frame broadcast to prevent saturating ActionBox's RX queue.
    return true;
}

bool EspNowAudioTransport::sendCommand(const char* target_node_id, const std::string& json_cmd, std::string* response) {
    if (!m_running || !m_ack_sem || !target_node_id || json_cmd.empty()) return false;
    std::lock_guard<std::mutex> command_lock(m_command_mutex);
    uint8_t dest[6];
    {
        std::lock_guard<std::mutex> lock(m_macs_mutex);
        auto it = m_node_macs.find(target_node_id);
        if (it == m_node_macs.end() || it->second.size() != 6) return false;
        memcpy(dest, it->second.data(), 6);
    }
    cJSON* root = cJSON_Parse(json_cmd.c_str());
    if (!root) return false;
    const auto* cmd = cJSON_GetObjectItem(root, "cmd");
    const auto* version = cJSON_GetObjectItem(root, "protocol_version");
    if (!cJSON_IsString(cmd) || strcmp(cmd->valuestring, "TOGGLE") == 0 ||
        !cJSON_IsNumber(version) || version->valueint != 3) { cJSON_Delete(root); return false; }
    cJSON* request = cJSON_GetObjectItem(root, "request_id");
    cJSON* session = cJSON_GetObjectItem(root, "session_id");
    if (!cJSON_IsNumber(request) || request->valuedouble <= 0 || request->valuedouble > UINT32_MAX ||
        !cJSON_IsNumber(session) || session->valuedouble < 0 || session->valuedouble > UINT32_MAX) {
        cJSON_Delete(root);
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(m_ack_mutex);
        m_pending_request = static_cast<uint32_t>(request->valuedouble);
        m_pending_node = target_node_id;
        m_pending_session = static_cast<uint32_t>(session->valuedouble);
        memcpy(m_pending_mac, dest, 6);
        m_ack_json.clear();
        m_ack_ok = false;
        xSemaphoreTake(m_ack_sem, 0);
    }
    cJSON_Delete(root);
    esp_now_peer_info_t peer{};
    if (esp_now_get_peer(dest, &peer) != ESP_OK) {
        memset(&peer, 0, sizeof(peer));
        memcpy(peer.peer_addr, dest, 6);
        peer.channel = 0;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = false;
        esp_now_add_peer(&peer);
    }
    const bool sent = esp_now_send(dest, reinterpret_cast<const uint8_t*>(json_cmd.data()), json_cmd.size()) == ESP_OK;
    const bool received = sent && xSemaphoreTake(m_ack_sem, pdMS_TO_TICKS(3000)) == pdTRUE;
    std::lock_guard<std::mutex> lock(m_ack_mutex);
    m_pending_request = 0;
    if (received && response) *response = m_ack_json;
    return received && m_ack_ok;
}

void EspNowAudioTransport::registerJsonCallback(std::function<void(const std::string&)> callback) {
    std::lock_guard<std::mutex> lock(m_callback_mutex);
    m_json_callback = callback;
}

void EspNowAudioTransport::registerRxCallback(std::function<void(const AudioPacket&)> callback) {
    std::lock_guard<std::mutex> lock(m_callback_mutex);
    m_rx_callback = callback;
}

void EspNowAudioTransport::stop() {
    if (!m_running) return;
    m_running = false;
    if (m_heartbeat_task) { vTaskDelete(m_heartbeat_task); m_heartbeat_task = nullptr; }
    esp_now_unregister_recv_cb();
    if (m_rx_task) { vTaskDelete(m_rx_task); m_rx_task = nullptr; }
    if (m_rx_queue) { vQueueDelete(m_rx_queue); m_rx_queue = nullptr; }
    esp_now_unregister_send_cb();
    esp_now_deinit();
    ESP_LOGI(TAG, "ESP-NOW Audio Transport stopped.");
}
