#include "nvs_manager.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "config/subbox_config.h"
#include <cstring>
#include "esp_mac.h"
#include "security_config.h"

static const char* TAG = "NVS_MGR";
static const char* NVS_NAMESPACE = "subbox_cfg";

esp_err_t NVSManager::init() {
    esp_err_t ret = nvs_flash_init();

    return ret;
}

esp_err_t NVSManager::loadConfig(SubBoxPersistentConfig& config) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);

    config = {};

    uint8_t mac[6]{}; esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(config.subbox_id, sizeof(config.subbox_id), "SB%02X%02X%02X%02X%02X%02X", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    strncpy(config.room_name, SUBBOX_DEFAULT_ROOM_NAME, sizeof(config.room_name) - 1);
    config.room_type = RoomType::BEDROOM;
    strncpy(config.wifi_ssid, SUBBOX_DEFAULT_WIFI_SSID, sizeof(config.wifi_ssid) - 1);
    strncpy(config.wifi_pass, SUBBOX_DEFAULT_WIFI_PASS, sizeof(config.wifi_pass) - 1);
    strncpy(config.mqtt_broker_uri, SUBBOX_DEFAULT_MQTT_BROKER_URI, sizeof(config.mqtt_broker_uri) - 1);
    strncpy(config.ws_gateway_uri, SUBBOX_DEFAULT_WS_GATEWAY_URI, sizeof(config.ws_gateway_uri) - 1);
    config.current_overload_limit_ma = 10000;
    config.temp_fan_trigger_c = 32.0f;

    if (err != ESP_OK) {
        ESP_LOGI(TAG, "No existing configuration in NVS, using system defaults.");
        return ESP_OK;
    }

    size_t len = 0;
    len = sizeof(config.subbox_id);
    nvs_get_str(handle, "id", config.subbox_id, &len);

    len = sizeof(config.room_name);
    nvs_get_str(handle, "room", config.room_name, &len);

    uint8_t room_val = 0;
    if (nvs_get_u8(handle, "rtype", &room_val) == ESP_OK) {
        config.room_type = static_cast<RoomType>(room_val);
    }

    len = sizeof(config.wifi_ssid);
    nvs_get_str(handle, "ssid", config.wifi_ssid, &len);

    len = sizeof(config.wifi_pass);
    nvs_get_str(handle, "pass", config.wifi_pass, &len);

    len = sizeof(config.mqtt_broker_uri);
    nvs_get_str(handle, "broker", config.mqtt_broker_uri, &len);

    len = sizeof(config.ws_gateway_uri);
    nvs_get_str(handle, "wsuri", config.ws_gateway_uri, &len);

    nvs_get_u32(handle, "cur_lim", &config.current_overload_limit_ma);

    nvs_close(handle);

    ESP_LOGI(TAG, "Loaded config: ID='%s', Room='%s', Wi-Fi='%s', Broker='%s'",
             config.subbox_id, config.room_name, config.wifi_ssid, config.mqtt_broker_uri);
    return ESP_OK;
}

esp_err_t NVSManager::saveConfig(const SubBoxPersistentConfig& config) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;

    nvs_set_str(handle, "id", config.subbox_id);
    nvs_set_str(handle, "room", config.room_name);
    nvs_set_u8(handle, "rtype", static_cast<uint8_t>(config.room_type));
    nvs_set_str(handle, "ssid", config.wifi_ssid);
    nvs_set_str(handle, "pass", config.wifi_pass);
    nvs_set_str(handle, "broker", config.mqtt_broker_uri);
    nvs_set_str(handle, "wsuri", config.ws_gateway_uri);
    nvs_set_u32(handle, "cur_lim", config.current_overload_limit_ma);

    err = nvs_commit(handle);
    nvs_close(handle);
    ESP_LOGI(TAG, "Config committed to NVS successfully.");
    return err;
}

esp_err_t NVSManager::networkReset() {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;

    nvs_erase_key(handle, "ssid");
    nvs_erase_key(handle, "pass");
    nvs_commit(handle);
    nvs_close(handle);

    SecurityConfig::networkReset();
    ESP_LOGW(TAG, "SubBox Network Reset performed: Wi-Fi credentials cleared, 180s setup window open.");
    return ESP_OK;
}

esp_err_t NVSManager::factoryReset() {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;

    char subbox_id[32] = {0};
    size_t id_len = sizeof(subbox_id);
    nvs_get_str(handle, "id", subbox_id, &id_len);

    nvs_erase_all(handle);

    // Restore factory UID so device identity is never lost
    if (strlen(subbox_id) > 0) {
        nvs_set_str(handle, "id", subbox_id);
    }
    nvs_commit(handle);
    nvs_close(handle);

    SecurityConfig::factoryReset();
    ESP_LOGW(TAG, "SubBox Factory Reset performed: User config & credentials wiped, factory UID preserved.");
    return ESP_OK;
}
