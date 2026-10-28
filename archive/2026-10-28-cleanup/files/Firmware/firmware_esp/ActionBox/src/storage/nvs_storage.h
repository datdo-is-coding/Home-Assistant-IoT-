#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "board_pins.h"
#include "app_config.h"
#include "current_sensor.h"
#include "relay_driver.h"
#include "device_reset.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    STARTUP_MODE_ALWAYS_OFF    = 0,
    STARTUP_MODE_ALWAYS_ON     = 1,
    STARTUP_MODE_RESTORE_LAST  = 2
} StartupMode;

#define NVS_FACTORY_DATA_MAGIC      0xFAC10001
#define NVS_USER_CONFIG_MAGIC       0xCF010001
#define NVS_LIFECYCLE_META_MAGIC    0x4C430001

// 1. Factory Data: UID, board_model, factory calibrations per channel, CRC32.
// MUST NEVER BE ERASED OR OVERWRITTEN ON FACTORY RESET!
typedef struct {
    uint32_t          magic;
    uint32_t          schema_version;
    char              device_uid[64];
    char              board_model[32];
    SensorCalibration calibrations[BOARD_RELAY_CHANNEL_COUNT];
    uint32_t          crc32;
} NvsFactoryData;

// 2. User Config: node_id, room_id, channel_names, startup_modes, assigned_subbox_mac, has_assigned_subbox, CRC32.
// Erased on factory reset. Network reset only unlinks SubBox/peers.
typedef struct {
    uint32_t          magic;
    uint32_t          schema_version;
    char              node_id[APP_MAX_NODE_ID_LEN];
    char              room_id[APP_MAX_ROOM_ID_LEN];
    char              channel_names[BOARD_RELAY_CHANNEL_COUNT][APP_MAX_CH_NAME_LEN];
    StartupMode       startup_modes[BOARD_RELAY_CHANNEL_COUNT];
    RelayState        last_states[BOARD_RELAY_CHANNEL_COUNT];
    uint32_t          max_current_ma[BOARD_RELAY_CHANNEL_COUNT];
    uint8_t           assigned_subbox_mac[6];
    bool              has_assigned_subbox;
    uint32_t          config_version;
    uint32_t          crc32;
} NvsUserConfig;

// 3. Lifecycle Metadata: owner_epoch (monotonically increasing), boot_id, reset_generation, CRC32.
typedef struct {
    uint32_t          magic;
    uint32_t          schema_version;
    uint32_t          owner_epoch;
    uint32_t          reset_generation;
    char              boot_id[64];
    uint32_t          crc32;
} NvsLifecycleMetadata;

// Unified in-memory persistent config structure
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

esp_err_t nvs_storage_init(void);
void nvs_storage_deinit(void);

esp_err_t nvs_storage_load_config(ActionBoxPersistentConfig *out_cfg);

esp_err_t nvs_storage_save_config(const ActionBoxPersistentConfig *cfg);

esp_err_t nvs_storage_factory_reset(ActionBoxPersistentConfig *out_cfg);

esp_err_t nvs_storage_reset_network(void);

void nvs_storage_record_relay_state(uint8_t channel, RelayState state);

const ActionBoxPersistentConfig* nvs_storage_get_cached_config(void);

bool nvs_storage_is_claimed(void);

// Granular accessors for lifecycle and factory data
esp_err_t nvs_storage_get_factory_data(NvsFactoryData *out_factory);
esp_err_t nvs_storage_get_lifecycle_metadata(NvsLifecycleMetadata *out_meta);
uint32_t  nvs_storage_get_owner_epoch(void);
esp_err_t nvs_storage_increment_owner_epoch(void);
void      nvs_storage_generate_new_boot_id(void);

// Reset intent management
esp_err_t nvs_storage_write_reset_intent(const ResetIntent *intent);
esp_err_t nvs_storage_read_reset_intent(ResetIntent *out_intent);
esp_err_t nvs_storage_clear_reset_intent(void);

#ifdef __cplusplus
}
#endif
