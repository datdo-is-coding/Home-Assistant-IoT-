#include "espnow_audio_transport.h"
#include "hc_runtime.h"
#include "esp_log.h"
#include "system/subbox_led.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include <cstring>
#include <algorithm>
#include "cJSON.h"
#include "storage/nvs_manager.h"
#include "network/espnow_receiver.h"

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
    if (hc_runtime_enabled() && len >= 2 && data[0] == 'H' && data[1] == 'C') {
        hc_runtime_receive_radio(recv_info->src_addr,data,(size_t)len); return;
    }

    bool is_broadcast = true;
    for (int i = 0; i < 6; i++) {
        if (recv_info->des_addr[i] != 0xFF) {
            is_broadcast = false;
            break;
        }
    }
    bool is_for_us = (memcmp(recv_info->des_addr, s_instance->m_local_mac, 6) == 0);
    if (!is_broadcast && !is_for_us) return;

    bool is_kws_or_audio = (data[0] >= 0x20 && data[0] <= 0x22) || (data[0] == 0x25);
    if (hc_runtime_enabled() && (is_broadcast || !hc_runtime_trusted_peer(recv_info->src_addr) || !is_kws_or_audio)) return;

    bool trusted = hc_runtime_enabled();
    for (const auto& peer : s_instance->m_trusted_peers) {
        if (memcmp(peer.mac, recv_info->src_addr, 6) == 0) {
            trusted = true;
            break;
        }
    }
    if (!trusted) {
        std::lock_guard<std::mutex> lock(s_instance->m_macs_mutex);
        for(const auto& peer:s_instance->m_registered_peers)
            if(memcmp(peer.mac,recv_info->src_addr,6)==0) {trusted=true;break;}
    }
    if (!trusted && s_instance->isPairingDiscoveryActive()) {
        trusted = true;
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

    if (!hc_runtime_enabled() && len==sizeof(ClaimReceipt) && data[0]==CLAIM_RECEIPT) {
        ClaimReceipt receipt; memcpy(&receipt,data,sizeof(receipt));
        if(receipt.version!=3 || !memchr(receipt.node_id,0,sizeof(receipt.node_id)) ||
            !memchr(receipt.operation,0,sizeof(receipt.operation))) return;
        std::lock_guard<std::mutex> lock(m_ack_mutex);
        if(!m_claim_operation.empty() && m_claim_operation==receipt.operation &&
            m_pending_node==receipt.node_id && memcmp(m_pending_mac,mac,6)==0) {
            m_claim_receipt=receipt; xSemaphoreGive(m_ack_sem);
        }
        return;
    }
    uint8_t msg_type = data[0];
    bool is_known_type = (msg_type >= 0x20 && msg_type <= 0x22) || (msg_type == 0x25) || (msg_type == '{');
    if (!is_known_type) return;

    if (msg_type == MSG_TYPE_KEYWORD_EVENT) {
        subbox_espnow_handle_keyword_event(data, len);
        return;
    }

    std::string source;
    if (msg_type >= 0x20 && msg_type <= 0x22 && hc_runtime_enabled()) {
        const uint32_t source_id = hc_runtime_peer_node_id(mac);
        if (!source_id || !hc_runtime_registered()) return;
        source = std::to_string(source_id);
    } else if (msg_type >= 0x20 && msg_type <= 0x22) {
        std::lock_guard<std::mutex> lock(m_macs_mutex);
        for (const auto& entry : m_node_macs)
            if (entry.second.size() == 6 && memcmp(entry.second.data(), mac, 6) == 0) source = entry.first;
        if (source.empty()) return;
    }

    if (msg_type == 0x20) {
        if (len < 3) return;
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

        if (!pcm_len || (pcm_len & 1) || pcm_len != len - 4 ||
            pcm_len > SUBBOX_AUDIO_MAX_PACKET_PAYLOAD) return;
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

    if (data[0] == '{') {
        if (hc_runtime_enabled()) return;
        cJSON* root = cJSON_ParseWithLength(reinterpret_cast<const char*>(data), len);
        if (!root) return;
        const cJSON* node = cJSON_GetObjectItem(root, "node_id");
        const cJSON* uid = cJSON_GetObjectItem(root, "hardware_uid");
        const cJSON* version = cJSON_GetObjectItem(root, "protocol_version");
        char expected_uid[13];
        snprintf(expected_uid, sizeof(expected_uid), "%02X%02X%02X%02X%02X%02X", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
        if (!cJSON_IsNumber(version) || version->valueint != 3 || !cJSON_IsString(uid) ||
            strcmp(uid->valuestring, expected_uid) != 0) { cJSON_Delete(root); return; }
        bool registered=false;
        { std::lock_guard<std::mutex> lock(m_macs_mutex);
          for(const auto& peer:m_registered_peers) if(memcmp(peer.mac,mac,6)==0) {registered=true;break;} }
        if (!registered && !SecurityConfig::isPeerTrusted(mac) && !SecurityConfig::isPairingAllowed()) {
            ESP_LOGW(TAG, "Rejected untrusted ActionBox peer %02X:%02X:%02X:%02X:%02X:%02X (pairing not open)",
                     mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            cJSON_Delete(root);
            return;
        }

        const cJSON* type=cJSON_GetObjectItem(root,"type");
        const bool setup=cJSON_IsString(type) && strcmp(type->valuestring,"SETUP")==0;
        if(!registered && !SecurityConfig::isPeerTrusted(mac) && !setup) {cJSON_Delete(root);return;}
        if(setup) {
            const auto* session=cJSON_GetObjectItem(root,"setup_session");
            const auto* remaining=cJSON_GetObjectItem(root,"setup_remaining_ms");
            std::string canonical="AB"+std::string(expected_uid);
            if(!SecurityConfig::isPairingAllowed() || !cJSON_IsString(node) || canonical!=node->valuestring ||
               !cJSON_IsNumber(session) || session->valuedouble<1 || session->valuedouble>UINT32_MAX ||
               !cJSON_IsNumber(remaining) || remaining->valuedouble<=0 || remaining->valuedouble>180000) {
                cJSON_Delete(root);return;
            }
            std::lock_guard<std::mutex> lock(m_macs_mutex);
            // Expired discoveries must not occupy slots needed by another board.
            for(auto it=m_candidates.begin();it!=m_candidates.end();) {
                if(it->second.expires_us<esp_timer_get_time()) {m_node_macs.erase(it->first);it=m_candidates.erase(it);}
                else ++it;
            }
            if(!m_candidates.count(canonical) && m_candidates.size()>=4) {cJSON_Delete(root);return;}
            m_candidates[canonical]={static_cast<uint32_t>(session->valuedouble),
                esp_timer_get_time()+static_cast<int64_t>(remaining->valuedouble)*1000};
        }
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

    for(unsigned slot=0;slot<4;++slot) {
        RegisteredPeer registered{};
        if(!SecurityConfig::loadRegistration(slot,registered)) continue;
        esp_now_peer_info_t peer{};
        memcpy(peer.peer_addr,registered.mac,6); peer.ifidx=WIFI_IF_STA;
        // Never replace or downgrade an existing encrypted peer.
        if(!esp_now_is_peer_exist(registered.mac) && esp_now_add_peer(&peer)==ESP_OK) {
            m_registered_peers.push_back(registered);
            m_node_macs[registered.claim.node_id]=std::vector<uint8_t>(registered.mac,registered.mac+6);
        }
    }

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
        int length = snprintf(payload, sizeof(payload), "{\"type\":\"heartbeat\",\"protocol_version\":3,\"subbox_id\":\"%s\",\"channel\":%u,\"wifi\":%s,\"mqtt\":%s,\"setup\":%s}", cfg.subbox_id, channel, subbox_led_wifi_connected() ? "true" : "false", subbox_led_mqtt_connected() ? "true" : "false", SecurityConfig::isPairingAllowed() ? "true" : "false");

        esp_now_send(bcast_mac, reinterpret_cast<const uint8_t*>(payload), length);

        for (const auto& peer : self->m_trusted_peers)
            esp_now_send(peer.mac, reinterpret_cast<const uint8_t*>(payload), length);

        { std::lock_guard<std::mutex> lock(self->m_macs_mutex);
          for(const auto& peer:self->m_registered_peers)
              esp_now_send(peer.mac,reinterpret_cast<const uint8_t*>(payload),length); }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    vTaskDelete(nullptr);
}

bool EspNowAudioTransport::sendAudio(const char* target_node_id, const AudioPacket& packet) {
    if (!m_running) return false;

    return true;
}

bool EspNowAudioTransport::sendCommand(const char* target_node_id, const std::string& json_cmd, std::string* response) {
    if (hc_runtime_enabled() || !m_running || !m_ack_sem || !target_node_id || json_cmd.empty()) return false;
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

bool EspNowAudioTransport::claimDevice(const std::string& request, std::string& result) {
    result.clear();
    if(hc_runtime_enabled() || !m_running || !m_ack_sem) return false;
    cJSON* root=cJSON_Parse(request.c_str());
    if(!root) return false;
    ClaimFrame claim{}; claim.type=CLAIM_FRAME; claim.version=3;
    auto copy=[root](const char* key,char* out,size_t capacity) {
        const auto* value=cJSON_GetObjectItem(root,key);
        if(!cJSON_IsString(value) || !value->valuestring[0] || strlen(value->valuestring)>=capacity) return false;
        strcpy(out,value->valuestring);return true;
    };
    const auto* revision=cJSON_GetObjectItem(root,"revision");
    const auto* session=cJSON_GetObjectItem(root,"setup_session");
    bool valid=copy("device_uid",claim.node_id,sizeof(claim.node_id)) &&
        copy("op_id",claim.operation,sizeof(claim.operation)) && copy("room_key",claim.room,sizeof(claim.room));
    valid &= cJSON_IsNumber(revision) && revision->valuedouble>=1 && revision->valuedouble<=UINT32_MAX &&
        cJSON_IsNumber(session) && session->valuedouble>=1 && session->valuedouble<=UINT32_MAX;
    if(valid) {claim.revision=static_cast<uint32_t>(revision->valuedouble);claim.session=static_cast<uint32_t>(session->valuedouble);}
    const auto* channels=cJSON_GetObjectItem(root,"channels");
    const char* defaults[]={"light","fan","switch"};
    for(int i=0;i<3;++i) {
        char key[]="ch1"; key[2]+=i;
        const auto* channel=cJSON_GetObjectItem(channels,key);
        const auto* type=cJSON_IsObject(channel)?cJSON_GetObjectItem(channel,"type"):channel;
        const char* value=cJSON_IsString(type)?type->valuestring:defaults[i];
        if(strlen(value)>=sizeof(claim.channels[i])) valid=false;
        else strcpy(claim.channels[i],value);
    }
    cJSON_Delete(root);
    if(!valid || !valid_claim(claim)) return false;
    std::lock_guard<std::mutex> command_lock(m_command_mutex);
    RegisteredPeer registration{}; registration.claim=claim;
    {
        std::lock_guard<std::mutex> lock(m_macs_mutex);
        const auto peer=m_node_macs.find(claim.node_id);
        if(peer==m_node_macs.end() || peer->second.size()!=6) return false;
        memcpy(registration.mac,peer->second.data(),6);
        bool retry=false, already_registered=false;
        for(const auto& registered:m_registered_peers) {
            retry |= memcmp(&registered,&registration,sizeof(registration))==0;
            already_registered |= memcmp(registered.mac,registration.mac,6)==0;
        }
        if(!already_registered && m_registered_peers.size()+m_trusted_peers.size()>=4) return false;
        for(const auto& encrypted:m_trusted_peers)
            if(memcmp(encrypted.mac,registration.mac,6)==0) return false;
        const auto candidate=m_candidates.find(claim.node_id);
        if(!retry && (!SecurityConfig::isPairingAllowed() || candidate==m_candidates.end() ||
            candidate->second.session!=claim.session || candidate->second.expires_us<=esp_timer_get_time())) return false;
    }
    {
        std::lock_guard<std::mutex> lock(m_ack_mutex);
        m_claim_operation=claim.operation; m_pending_node=claim.node_id;
        memcpy(m_pending_mac,registration.mac,6); m_claim_receipt={};
        xSemaphoreTake(m_ack_sem,0);
    }
    bool received=false;
    for(int attempt=0;attempt<3 && !received;++attempt) {
        if(esp_now_send(registration.mac,reinterpret_cast<const uint8_t*>(&claim),sizeof(claim))==ESP_OK)
            received=xSemaphoreTake(m_ack_sem,pdMS_TO_TICKS(1000))==pdTRUE;
    }
    ClaimReceipt receipt{};
    {
        std::lock_guard<std::mutex> lock(m_ack_mutex);
        receipt=m_claim_receipt; m_claim_operation.clear();
    }
    if(!received || receipt.success!=1 || receipt.revision!=claim.revision || !receipt.owner_epoch) return false;
    if(SecurityConfig::saveRegistration(registration)!=ESP_OK) return false;
    {
        std::lock_guard<std::mutex> lock(m_macs_mutex);
        auto old=std::find_if(m_registered_peers.begin(),m_registered_peers.end(),[&](const RegisteredPeer& p) {
            return memcmp(p.mac,registration.mac,6)==0;
        });
        if(old==m_registered_peers.end()) m_registered_peers.push_back(registration); else *old=registration;
        m_candidates.erase(claim.node_id);
    }
    cJSON* applied=cJSON_CreateObject();
    cJSON_AddStringToObject(applied,"type","CLAIM_APPLIED");
    cJSON_AddNumberToObject(applied,"protocol_version",3);
    cJSON_AddStringToObject(applied,"node_id",claim.node_id);
    cJSON_AddStringToObject(applied,"hardware_uid",claim.node_id+2);
    cJSON_AddStringToObject(applied,"operation_id",claim.operation);
    cJSON_AddNumberToObject(applied,"config_version",receipt.revision);
    cJSON_AddNumberToObject(applied,"owner_epoch",receipt.owner_epoch);
    char* encoded=cJSON_PrintUnformatted(applied);
    if(encoded) {result=encoded;cJSON_free(encoded);}
    cJSON_Delete(applied);
    return !result.empty();
}
