/**
 * @file nvs_storage.cpp
 * @brief Thread-safe Persistent Configuration Storage Implementation
 */

#include "nvs_storage.h"
#include "board_pins.h"
#include "app_config.h"
#include "bl0942.h"

#include <string.h>
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "NVS_STORAGE";
static const char *NVS_NAMESPACE = "actionbox_cfg";
static const char *NVS_BLOB_KEY  = "config_blob";

#define CONFIG_MAGIC_VAL 0xAB001001

static ActionBoxPersistentConfig s_cached_config;
static SemaphoreHandle_t s_storage_mutex = NULL;
static bool s_storage_initialized = false;
static int64_t s_last_relay_save_us = 0;

static void set_factory_defaults(ActionBoxPersistentConfig *cfg) {
    memset(cfg, 0, sizeof(ActionBoxPersistentConfig));

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    snprintf(cfg->node_id, sizeof(cfg->node_id), "AB%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    strncpy(cfg->room_id, APP_DEFAULT_ROOM_ID, sizeof(cfg->room_id) - 1);
    strncpy(cfg->firmware_version, APP_FW_VERSION_STR, sizeof(cfg->firmware_version) - 1);

    cfg->channel_names[0][0] = '\0';
    cfg->channel_names[1][0] = '\0';
    snprintf(cfg->channel_names[0], sizeof(cfg->channel_names[0]), "Relay Channel 1");
    snprintf(cfg->channel_names[1], sizeof(cfg->channel_names[1]), "Relay Channel 2");

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        cfg->startup_modes[i] = STARTUP_MODE_ALWAYS_OFF;
        cfg->last_states[i]   = RELAY_STATE_OFF;
        cfg->max_current_ma[i]= SAFETY_DEFAULT_MAX_CURRENT_MA;
        cfg->calibrations[i].current_factor = BL0942_DEFAULT_CAL_CURRENT;
        cfg->calibrations[i].voltage_factor = BL0942_DEFAULT_CAL_VOLTAGE;
        cfg->calibrations[i].power_factor   = BL0942_DEFAULT_CAL_POWER;
    }

    cfg->has_assigned_subbox = false;
    memset(cfg->assigned_subbox_mac, 0, 6);
    cfg->config_version = CONFIG_MAGIC_VAL;
}

esp_err_t nvs_storage_init(void) {
    if (s_storage_initialized) return ESP_OK;

    ESP_LOGI(TAG, "Initializing NVS Flash Storage...");
    s_storage_mutex = xSemaphoreCreateMutex();
    if (!s_storage_mutex) {
        ESP_LOGE(TAG, "Failed to create storage mutex!");
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing corrupted or older NVS partition...");
        err = nvs_flash_erase();
        if (err != ESP_OK) return err;
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS flash init failed: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_storage_load_config(&s_cached_config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Loading configuration failed. Writing factory defaults...");
        set_factory_defaults(&s_cached_config);
        nvs_storage_save_config(&s_cached_config);
    }

    s_storage_initialized = true;
    ESP_LOGI(TAG, "NVS Storage initialized. Node ID: %s, Room: %s, FW: %s",
             s_cached_config.node_id, s_cached_config.room_id, s_cached_config.firmware_version);
    return ESP_OK;
}

esp_err_t nvs_storage_load_config(ActionBoxPersistentConfig *out_cfg) {
    if (!out_cfg) return ESP_ERR_INVALID_ARG;

    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    size_t required_size = sizeof(ActionBoxPersistentConfig);
    err = nvs_get_blob(handle, NVS_BLOB_KEY, out_cfg, &required_size);
    nvs_close(handle);

    if (err == ESP_OK) {
        if (out_cfg->config_version != CONFIG_MAGIC_VAL) {
            ESP_LOGW(TAG, "Config magic version mismatch. Stale config detected.");
            err = ESP_ERR_INVALID_VERSION;
        }
    }

    xSemaphoreGive(s_storage_mutex);
    return err;
}

esp_err_t nvs_storage_save_config(const ActionBoxPersistentConfig *cfg) {
    if (!cfg) return ESP_ERR_INVALID_ARG;

    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    err = nvs_set_blob(handle, NVS_BLOB_KEY, cfg, sizeof(ActionBoxPersistentConfig));
    if (err == ESP_OK) {
        err = nvs_commit(handle);
        if (err == ESP_OK) {
            s_cached_config = *cfg;
            ESP_LOGI(TAG, "Persistent configuration successfully written to NVS.");
        }
    }
    nvs_close(handle);

    xSemaphoreGive(s_storage_mutex);
    return err;
}

esp_err_t nvs_storage_factory_reset(ActionBoxPersistentConfig *out_cfg) {
    ESP_LOGW(TAG, "FACTORY RESET INITIATED! Restoring all defaults...");
    ActionBoxPersistentConfig defaults;
    set_factory_defaults(&defaults);

    esp_err_t err = nvs_storage_save_config(&defaults);
    if (err == ESP_OK && out_cfg) {
        *out_cfg = defaults;
    }
    return err;
}

void nvs_storage_record_relay_state(uint8_t channel, RelayState state) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT) return;
    uint8_t idx = channel - 1;

    /* Only record if channel is configured for restore-last mode */
    if (s_cached_config.startup_modes[idx] != STARTUP_MODE_RESTORE_LAST) {
        return;
    }

    /* Check if actually changed */
    if (s_cached_config.last_states[idx] == state) {
        return;
    }

    /* Cooldown check to prevent flash exhaustion during rapid toggle tests (min 10s gap) */
    int64_t now_us = esp_timer_get_time();
    int64_t elapsed_ms = (now_us - s_last_relay_save_us) / 1000;
    if (elapsed_ms < 10000) {
        s_cached_config.last_states[idx] = state;
        return;
    }

    s_cached_config.last_states[idx] = state;
    s_last_relay_save_us = now_us;
    nvs_storage_save_config(&s_cached_config);
}

const ActionBoxPersistentConfig* nvs_storage_get_cached_config(void) {
    return &s_cached_config;
}
