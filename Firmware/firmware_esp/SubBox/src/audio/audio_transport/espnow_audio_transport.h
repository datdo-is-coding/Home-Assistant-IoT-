/**
 * @file espnow_audio_transport.h
 * @brief Reliable ESP-NOW Audio & Command Transport for SubBox <-> ActionBox
 */

#pragma once

#include "audio_transport.h"
#include <map>
#include <set>
#include <vector>
#include <string>
#include <mutex>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_now.h"
#include "esp_idf_version.h"
#include "storage/security_config.h"

class EspNowAudioTransport : public AudioTransport {
public:
    EspNowAudioTransport();
    virtual ~EspNowAudioTransport();

    bool init() override;
    bool sendAudio(const char* target_node_id, const AudioPacket& packet) override;
    bool sendCommand(const char* target_node_id, const std::string& json_cmd, std::string* response = nullptr) override;
    void registerJsonCallback(std::function<void(const std::string&)> callback) override;
    void registerRxCallback(std::function<void(const AudioPacket&)> callback) override;
    void stop() override;
    bool isRunning() const override { return m_running; }

    static EspNowAudioTransport* getInstance() { return s_instance; }

private:
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
    static void onEspNowSend(const wifi_tx_info_t *tx_info, esp_now_send_status_t status);
#else
    static void onEspNowSend(const uint8_t *mac_addr, esp_now_send_status_t status);
#endif
    static void onEspNowRecv(const esp_now_recv_info_t *recv_info, const uint8_t *data, int len);
    void handleReceivedPacket(const uint8_t* mac, const uint8_t* data, int len);
    struct RxItem { uint8_t mac[6]; uint16_t len; uint8_t data[1470]; };
    static void receiveTask(void* arg);
    static void heartbeatTask(void* arg);
    TaskHandle_t m_heartbeat_task = nullptr;
    std::vector<TrustedPeer> m_trusted_peers;
    uint8_t m_local_mac[6]{};
    QueueHandle_t m_rx_queue = nullptr;
    TaskHandle_t m_rx_task = nullptr;

    volatile bool m_running;
    std::function<void(const AudioPacket&)> m_rx_callback;
    std::mutex m_callback_mutex;

    // Track paired ActionBox MACs
    std::map<std::string, std::vector<uint8_t>> m_node_macs;
    std::set<std::string> m_conflicting_nodes;
    std::mutex m_macs_mutex;
    std::function<void(const std::string&)> m_json_callback;
    std::mutex m_command_mutex;
    std::mutex m_ack_mutex;
    SemaphoreHandle_t m_ack_sem = nullptr;
    uint32_t m_pending_request = 0;
    uint32_t m_pending_session = 0;
    uint8_t m_pending_mac[6]{};
    std::string m_ack_json;
    std::string m_pending_node;
    bool m_ack_ok = false;

    static EspNowAudioTransport* s_instance;
};
