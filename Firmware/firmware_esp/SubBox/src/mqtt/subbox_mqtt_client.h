/**
 * @file subbox_mqtt_client.h
 * @brief ESP-IDF MQTT Client for SubBox <-> Raspberry Pi 4 Hub
 */

#pragma once

#include <string>
#include <functional>
#include <mutex>
#include <atomic>
#include "esp_event.h"
#include "mqtt_client.h"

class MqttClient {
public:
    explicit MqttClient(const std::string& broker_uri, const std::string& subbox_id);
    ~MqttClient();

    bool init();
    void stop();
    bool isConnected() const { return m_connected; }

    bool publishState(const std::string& json_payload);
    bool publishEvent(const std::string& event_type, const std::string& json_payload);
    bool publishVoiceRequest(const std::string& origin_node_id, const std::string& transcript);

    void registerCommandCallback(std::function<void(const std::string& topic, const std::string& payload)> cb);
    void registerVoiceResponseCallback(std::function<void(const std::string& target_node_id, const std::string& text, const uint8_t* audio, size_t audio_len)> cb);

private:
    static void mqttEventHandler(void* handler_args, esp_event_base_t base, int32_t event_id, void* event_data);
    void onMqttData(const char* topic, int topic_len, const char* data, int data_len);

    std::string m_broker_uri;
    std::string m_subbox_id;
    esp_mqtt_client_handle_t m_client;
    std::atomic<bool> m_connected;
    std::string m_ca, m_user, m_password;

    std::string m_topic_state;
    std::string m_topic_event;
    std::string m_topic_command;
    std::string m_topic_voice_req;
    std::string m_topic_voice_resp;

    std::function<void(const std::string&, const std::string&)> m_cmd_callback;
    std::function<void(const std::string&, const std::string&, const uint8_t*, size_t)> m_voice_resp_callback;
    mutable std::mutex m_mutex;
};
