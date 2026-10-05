/**
 * @file subbox_mqtt_client.cpp
 * @brief ESP-IDF MQTT Client Implementation for Pi4 Integration
 */

#include "subbox_mqtt_client.h"
#include "esp_log.h"
#include <cstring>
#include "cJSON.h"
#include "esp_random.h"
#include "storage/security_config.h"
#include "system/subbox_led.h"

static const char* TAG = "SUBBOX_MQTT";

MqttClient::MqttClient(const std::string& broker_uri, const std::string& subbox_id)
    : m_broker_uri(broker_uri),
      m_subbox_id(subbox_id),
      m_client(nullptr),
      m_connected(false),
      m_cmd_callback(nullptr),
      m_voice_resp_callback(nullptr) {

    m_topic_state      = "home/subbox/" + m_subbox_id + "/state";
    m_topic_event      = "home/subbox/" + m_subbox_id + "/event";
    m_topic_command    = "home/subbox/" + m_subbox_id + "/command";
    m_topic_voice_req  = "home/subbox/" + m_subbox_id + "/voice/request";
    m_topic_voice_resp = "home/subbox/" + m_subbox_id + "/voice/response";
}

MqttClient::~MqttClient() {
    stop();
}

bool MqttClient::init() {
    if (m_client) return true;

    ESP_LOGI(TAG, "Initializing MQTT connection to: %s...", m_broker_uri.c_str());

    m_broker_uri = SecurityConfig::get("mqtt_uri");
    m_ca = SecurityConfig::get("ca_pem");
    m_user = SecurityConfig::get("mqtt_user");
    m_password = SecurityConfig::get("mqtt_pass");
    if (m_broker_uri.rfind("mqtts://", 0) != 0 || m_ca.empty() || m_user.empty() || m_password.empty()) {
        subbox_led_set_mqtt_configured(false);
        ESP_LOGE(TAG, "TLS MQTT unavailable: provision URI, CA and per-device credentials over USB");
        return false;
    }
    subbox_led_set_mqtt_configured(true);
    esp_mqtt_client_config_t mqtt_cfg = {};
    mqtt_cfg.broker.verification.certificate = m_ca.c_str();
    mqtt_cfg.credentials.client_id = m_subbox_id.c_str();
    mqtt_cfg.credentials.username = m_user.c_str();
    mqtt_cfg.credentials.authentication.password = m_password.c_str();
    mqtt_cfg.buffer.size = 2048;
    mqtt_cfg.broker.address.uri = m_broker_uri.c_str();
    mqtt_cfg.network.reconnect_timeout_ms = 5000;

    m_client = esp_mqtt_client_init(&mqtt_cfg);
    if (!m_client) {
        ESP_LOGE(TAG, "Failed to create MQTT client handle!");
        return false;
    }

    esp_mqtt_client_register_event(m_client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqttEventHandler, this);
    esp_err_t err = esp_mqtt_client_start(m_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return false;
    }

    return true;
}

void MqttClient::stop() {
    if (m_client) {
        esp_mqtt_client_stop(m_client);
        esp_mqtt_client_destroy(m_client);
        m_client = nullptr;
        m_connected = false;
    }
}

void MqttClient::registerCommandCallback(std::function<void(const std::string&, const std::string&)> cb) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_cmd_callback = cb;
}

void MqttClient::registerVoiceResponseCallback(
    std::function<void(const std::string&, const std::string&, const uint8_t*, size_t)> cb
) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_voice_resp_callback = cb;
}

bool MqttClient::publishState(const std::string& json_payload) {
    if (!m_client || !m_connected) return false;
    int msg_id = esp_mqtt_client_publish(m_client, m_topic_state.c_str(), json_payload.c_str(), json_payload.length(), 1, 0);
    return (msg_id >= 0);
}

bool MqttClient::publishEvent(const std::string& event_type, const std::string& json_payload) {
    if (!m_client || !m_connected) return false;
    std::string topic = m_topic_event + "/" + event_type;
    int msg_id = esp_mqtt_client_enqueue(m_client, topic.c_str(), json_payload.c_str(), json_payload.length(), 1, 0, true);
    return (msg_id >= 0);
}

bool MqttClient::publishVoiceRequest(const std::string& origin_node_id, const std::string& transcript) {
    if (!m_client || !m_connected) return false;
    cJSON* root = cJSON_CreateObject();
    if (!root) return false;
    cJSON_AddStringToObject(root, "origin_node", origin_node_id.c_str());
    cJSON_AddStringToObject(root, "text", transcript.c_str());
    cJSON_AddNumberToObject(root, "request_id", esp_random());
    char* encoded = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!encoded) return false;
    std::string payload(encoded);
    cJSON_free(encoded);
    int msg_id = esp_mqtt_client_publish(m_client, m_topic_voice_req.c_str(), payload.c_str(), payload.length(), 1, 0);
    ESP_LOGI(TAG, "Voice request forwarded to Pi4 on %s: %s", m_topic_voice_req.c_str(), payload.c_str());
    return (msg_id >= 0);
}

void MqttClient::mqttEventHandler(void* handler_args, esp_event_base_t base, int32_t event_id, void* event_data) {
    auto* self = static_cast<MqttClient*>(handler_args);
    auto* event = static_cast<esp_mqtt_event_handle_t>(event_data);

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT Connected to Pi4 Broker! Subscribing to command topics...");
            self->m_connected = true;
            subbox_led_set_mqtt_connected(true);
            esp_mqtt_client_subscribe(self->m_client, self->m_topic_command.c_str(), 1);
            esp_mqtt_client_subscribe(self->m_client, self->m_topic_voice_resp.c_str(), 1);
            break;

        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "MQTT Disconnected from Pi4 Broker! Operating in standalone local mode.");
            self->m_connected = false;
            subbox_led_set_mqtt_connected(false);
            break;

        case MQTT_EVENT_DATA:
            // Never execute a partial MQTT message as a complete command.
            if (event->current_data_offset == 0 && event->data_len == event->total_data_len)
                self->onMqttData(event->topic, event->topic_len, event->data, event->data_len);
            break;

        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT Error encountered");
            break;

        default:
            break;
    }
}

void MqttClient::onMqttData(const char* topic, int topic_len, const char* data, int data_len) {
    if (!topic || topic_len <= 0 || !data || data_len <= 0) return;

    std::string s_topic(topic, topic_len);
    std::string s_data(data, data_len);

    ESP_LOGI(TAG, "MQTT Inbound: [%s] -> %s", s_topic.c_str(), s_data.c_str());

    std::function<void(const std::string&, const std::string&)> cmd_cb;
    std::function<void(const std::string&, const std::string&, const uint8_t*, size_t)> voice_cb;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        cmd_cb = m_cmd_callback;
        voice_cb = m_voice_resp_callback;
    }

    if (s_topic == m_topic_command && cmd_cb) {
        cmd_cb(s_topic, s_data);
    } else if (s_topic == m_topic_voice_resp && voice_cb) {
        voice_cb("", s_data, nullptr, 0);
    }
}
