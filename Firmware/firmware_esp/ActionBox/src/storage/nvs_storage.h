/**
 * @file nvs_storage.h
 * @brief Persistent Configuration Storage using ESP-IDF NVS
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "board_pins.h"
#include "app_config.h"
#include "current_sensor.h"
#include "relay_driver.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    STARTUP_MODE_ALWAYS_OFF    = 0,
    STARTUP_MODE_ALWAYS_ON     = 1,
    STARTUP_MODE_RESTORE_LAST  = 2
} StartupMode;

typedef struct {
    char              node_id[APP_MAX_NODE_ID_LEN];
    char              room_id[APP_MAX_ROOM_ID_LEN];
    char              channel_names[BOARD_RELAY_CHANNEL_COUNT][APP_MAX_CH_NAME_LEN];
    StartupMode       startup_modes[BOARD_RELAY_CHANNEL_COUNT];
    RelayState        last_states[BOARD_RELAY_CHANNEL_COUNT];
    uint32_t          max_current_ma[BOARD_RELAY_CHANNEL_COUNT];
    SensorCalibration calibrations[BOARD_RELAY_CHANNEL_COUNT];
    char              firmware_version[16];
    uint8_t           assigned_subbox_mac[6];
    bool              has_assigned_subbox;
    uint32_t          config_version;
} ActionBoxPersistentConfig;

/**
 * @brief Initialize NVS flash partition and load configuration
 * @return ESP_OK on success
 */
esp_err_t nvs_storage_init(void);

/**
 * @brief Load persistent configuration from NVS (or writes factory defaults on first boot)
 * @param out_cfg Pointer to destination struct
 * @return ESP_OK on success
 */
esp_err_t nvs_storage_load_config(ActionBoxPersistentConfig *out_cfg);

/**
 * @brief Save modified configuration to NVS
 * Only performs write if fields have changed.
 * @param cfg Pointer to config struct
 * @return ESP_OK on success
 */
esp_err_t nvs_storage_save_config(const ActionBoxPersistentConfig *cfg);

/**
 * @brief Reset all parameters to factory defaults in NVS
 * @param out_cfg Optional destination pointer for new defaults
 * @return ESP_OK on success
 */
esp_err_t nvs_storage_factory_reset(ActionBoxPersistentConfig *out_cfg);

/**
 * @brief Update last known relay state safely with rate limiting and change check
 * Does NOT cause rapid flash wear.
 * @param channel Channel ID (1 or 2)
 * @param state New RelayState
 */
void nvs_storage_record_relay_state(uint8_t channel, RelayState state);

/**
 * @brief Read currently cached configuration pointer
 * @return Const pointer to in-memory config struct
 */
const ActionBoxPersistentConfig* nvs_storage_get_cached_config(void);

#ifdef __cplusplus
}
#endif
