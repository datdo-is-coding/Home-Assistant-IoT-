/**
 * @file nvs_manager.h
 * @brief Persistent Non-Volatile Storage (NVS) for SubBox Settings
 */

#pragma once

#include <string>
#include "esp_err.h"
#include "nlu/entity/entity_types.h"

struct SubBoxPersistentConfig {
    char subbox_id[32];
    char room_name[32];
    RoomType room_type;
    char wifi_ssid[32];
    char wifi_pass[64];
    char mqtt_broker_uri[128];
    uint32_t current_overload_limit_ma;
    float temp_fan_trigger_c;
};

class NVSManager {
public:
    static esp_err_t init();
    static esp_err_t loadConfig(SubBoxPersistentConfig& config);
    static esp_err_t saveConfig(const SubBoxPersistentConfig& config);
    static esp_err_t factoryReset();
};
