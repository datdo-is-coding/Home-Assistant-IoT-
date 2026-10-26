#pragma once

#include <string>
#include "esp_err.h"
#include "nlu/entity/entity_types.h"

struct SubBoxPersistentConfig {
    char subbox_id[32];
    char room_name[32];
    RoomType room_type;
    char wifi_ssid[33];
    char wifi_pass[65];
    char mqtt_broker_uri[128];
    char ws_gateway_uri[128];
    uint32_t current_overload_limit_ma;
    float temp_fan_trigger_c;
};

class NVSManager {
public:
    static esp_err_t init();
    static esp_err_t loadConfig(SubBoxPersistentConfig& config);
    static esp_err_t saveConfig(const SubBoxPersistentConfig& config);
    static esp_err_t loadKwsSnapshot(std::string& snapshot);
    static esp_err_t saveKwsSnapshot(const std::string& snapshot);
    static esp_err_t networkReset();
    static esp_err_t factoryReset();
};
