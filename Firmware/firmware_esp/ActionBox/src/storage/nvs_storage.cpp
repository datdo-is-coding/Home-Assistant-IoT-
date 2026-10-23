#include "nvs_storage.h"
#include "board_pins.h"
#include "app_config.h"
#include "bl0942.h"
#include "device_lifecycle.h"

#include <string.h>
#include <stddef.h>
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#ifndef ESP_ERR_NVS_NOT_FOUND
#define ESP_ERR_NVS_NOT_FOUND ESP_ERR_NOT_FOUND
#endif

static const char *TAG = "NVS_STORAGE";
static const char *NVS_NAMESPACE = "actionbox_cfg";
static const char *BOARD_MODEL_NAME = "actionbox_v1";

static const char *NVS_KEY_FACTORY_DATA = "factory_data";
static const char *NVS_KEY_USER_CONFIG  = "user_config";
static const char *NVS_KEY_LIFECYCLE    = "lifecycle_meta";
static const char *NVS_KEY_RESET_INTENT = "reset_intent";
static const char *NVS_KEY_LEGACY_BLOB  = "config_blob";

#define CONFIG_MAGIC_VAL 0xAB001001

static NvsFactoryData s_factory_data;
static NvsUserConfig s_user_config;
static NvsLifecycleMetadata s_lifecycle_meta;
static ActionBoxPersistentConfig s_cached_config;
static SemaphoreHandle_t s_storage_mutex = NULL;
static bool s_storage_initialized = false;
static int64_t s_last_relay_save_us = 0;

static void generate_boot_id(char *out_id, size_t max_len) {
    if (!out_id || max_len == 0) return;
    int64_t t = esp_timer_get_time();
    uint32_t r = esp_random();
    snprintf(out_id, max_len, "boot_%llx_%08lx", (unsigned long long)t, (unsigned long)r);
}

static bool verify_factory_data_crc(const NvsFactoryData *fd) {
    if (!fd || fd->magic != NVS_FACTORY_DATA_MAGIC) return false;
    uint32_t expected = calculate_crc32((const uint8_t*)fd, offsetof(NvsFactoryData, crc32));
    return fd->crc32 == expected;
}

static bool verify_user_config_crc(const NvsUserConfig *uc) {
    if (!uc || uc->magic != NVS_USER_CONFIG_MAGIC) return false;
    uint32_t expected = calculate_crc32((const uint8_t*)uc, offsetof(NvsUserConfig, crc32));
    return uc->crc32 == expected;
}

static bool verify_lifecycle_meta_crc(const NvsLifecycleMetadata *lm) {
    if (!lm || lm->magic != NVS_LIFECYCLE_META_MAGIC) return false;
    uint32_t expected = calculate_crc32((const uint8_t*)lm, offsetof(NvsLifecycleMetadata, crc32));
    return lm->crc32 == expected;
}

static void update_cached_config(void) {
    strncpy(s_cached_config.node_id, s_user_config.node_id, sizeof(s_cached_config.node_id) - 1);
    s_cached_config.node_id[sizeof(s_cached_config.node_id) - 1] = '\0';
    strncpy(s_cached_config.room_id, s_user_config.room_id, sizeof(s_cached_config.room_id) - 1);
    s_cached_config.room_id[sizeof(s_cached_config.room_id) - 1] = '\0';
    strncpy(s_cached_config.firmware_version, APP_FW_VERSION_STR, sizeof(s_cached_config.firmware_version) - 1);
    s_cached_config.firmware_version[sizeof(s_cached_config.firmware_version) - 1] = '\0';

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        strncpy(s_cached_config.channel_names[i], s_user_config.channel_names[i], sizeof(s_cached_config.channel_names[i]) - 1);
        s_cached_config.channel_names[i][sizeof(s_cached_config.channel_names[i]) - 1] = '\0';
        s_cached_config.startup_modes[i] = s_user_config.startup_modes[i];
        s_cached_config.last_states[i]   = s_user_config.last_states[i];
        s_cached_config.max_current_ma[i]= s_user_config.max_current_ma[i];
        s_cached_config.calibrations[i]  = s_factory_data.calibrations[i];
    }

    s_cached_config.has_assigned_subbox = s_user_config.has_assigned_subbox;
    memcpy(s_cached_config.assigned_subbox_mac, s_user_config.assigned_subbox_mac, 6);
    s_cached_config.config_version = s_user_config.config_version;
}

static esp_err_t migrate_legacy_blob(nvs_handle_t handle, const ActionBoxPersistentConfig *legacy) {
    if (!legacy) return ESP_ERR_INVALID_ARG;
    if (legacy->config_version != CONFIG_MAGIC_VAL) {
        ESP_LOGE(TAG, "Legacy blob has invalid config version/magic (0x%08lx != 0x%08x)",
                 (unsigned long)legacy->config_version, CONFIG_MAGIC_VAL);
        return ESP_ERR_INVALID_VERSION;
    }

    ESP_LOGI(TAG, "Migrating legacy config blob to schema with CRC32 protection...");

    // 1. Factory data
    memset(&s_factory_data, 0, sizeof(NvsFactoryData));
    s_factory_data.magic = NVS_FACTORY_DATA_MAGIC;
    s_factory_data.schema_version = 1;
    strncpy(s_factory_data.device_uid, legacy->node_id, sizeof(s_factory_data.device_uid) - 1);
    strncpy(s_factory_data.board_model, BOARD_MODEL_NAME, sizeof(s_factory_data.board_model) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        s_factory_data.calibrations[i] = legacy->calibrations[i];
    }
    s_factory_data.crc32 = calculate_crc32((const uint8_t*)&s_factory_data, offsetof(NvsFactoryData, crc32));

    // 2. User config
    memset(&s_user_config, 0, sizeof(NvsUserConfig));
    s_user_config.magic = NVS_USER_CONFIG_MAGIC;
    s_user_config.schema_version = 1;
    strncpy(s_user_config.node_id, legacy->node_id, sizeof(s_user_config.node_id) - 1);
    strncpy(s_user_config.room_id, legacy->room_id, sizeof(s_user_config.room_id) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        strncpy(s_user_config.channel_names[i], legacy->channel_names[i], sizeof(s_user_config.channel_names[i]) - 1);
        s_user_config.startup_modes[i] = legacy->startup_modes[i];
        s_user_config.last_states[i]   = legacy->last_states[i];
        s_user_config.max_current_ma[i]= legacy->max_current_ma[i];
    }
    memcpy(s_user_config.assigned_subbox_mac, legacy->assigned_subbox_mac, 6);
    s_user_config.has_assigned_subbox = legacy->has_assigned_subbox;
    s_user_config.config_version = 1;
    s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));

    // 3. Lifecycle metadata
    memset(&s_lifecycle_meta, 0, sizeof(NvsLifecycleMetadata));
    s_lifecycle_meta.magic = NVS_LIFECYCLE_META_MAGIC;
    s_lifecycle_meta.schema_version = 1;
    s_lifecycle_meta.owner_epoch = 1;
    s_lifecycle_meta.reset_generation = 0;
    generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
    s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));

    // Write all three to NVS
    esp_err_t err = nvs_set_blob(handle, NVS_KEY_FACTORY_DATA, &s_factory_data, sizeof(NvsFactoryData));
    if (err != ESP_OK) return err;

    err = nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
    if (err != ESP_OK) return err;

    err = nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
    if (err != ESP_OK) return err;

    err = nvs_commit(handle);
    if (err != ESP_OK) return err;

    nvs_erase_key(handle, NVS_KEY_LEGACY_BLOB);
    nvs_commit(handle);

    update_cached_config();
    ESP_LOGI(TAG, "Legacy migration successful. Calibration preserved with CRC32.");
    return ESP_OK;
}

static esp_err_t init_brand_new_factory_defaults(nvs_handle_t handle) {
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    // Factory data
    memset(&s_factory_data, 0, sizeof(NvsFactoryData));
    s_factory_data.magic = NVS_FACTORY_DATA_MAGIC;
    s_factory_data.schema_version = 1;
    snprintf(s_factory_data.device_uid, sizeof(s_factory_data.device_uid), "AB%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    strncpy(s_factory_data.board_model, BOARD_MODEL_NAME, sizeof(s_factory_data.board_model) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        s_factory_data.calibrations[i].current_factor = BL0942_DEFAULT_CAL_CURRENT;
        s_factory_data.calibrations[i].voltage_factor = BL0942_DEFAULT_CAL_VOLTAGE;
        s_factory_data.calibrations[i].power_factor   = BL0942_DEFAULT_CAL_POWER;
    }
    s_factory_data.crc32 = calculate_crc32((const uint8_t*)&s_factory_data, offsetof(NvsFactoryData, crc32));

    // User config
    memset(&s_user_config, 0, sizeof(NvsUserConfig));
    s_user_config.magic = NVS_USER_CONFIG_MAGIC;
    s_user_config.schema_version = 1;
    strncpy(s_user_config.node_id, s_factory_data.device_uid, sizeof(s_user_config.node_id) - 1);
    strncpy(s_user_config.room_id, APP_DEFAULT_ROOM_ID, sizeof(s_user_config.room_id) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        snprintf(s_user_config.channel_names[i], sizeof(s_user_config.channel_names[i]), "Relay Channel %u", i + 1);
        s_user_config.startup_modes[i] = STARTUP_MODE_ALWAYS_OFF;
        s_user_config.last_states[i]   = RELAY_STATE_OFF;
        s_user_config.max_current_ma[i]= SAFETY_DEFAULT_MAX_CURRENT_MA;
    }
    s_user_config.has_assigned_subbox = false;
    memset(s_user_config.assigned_subbox_mac, 0, 6);
    s_user_config.config_version = 0;
    s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));

    // Lifecycle metadata
    memset(&s_lifecycle_meta, 0, sizeof(NvsLifecycleMetadata));
    s_lifecycle_meta.magic = NVS_LIFECYCLE_META_MAGIC;
    s_lifecycle_meta.schema_version = 1;
    s_lifecycle_meta.owner_epoch = 1;
    s_lifecycle_meta.reset_generation = 0;
    generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
    s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));

    esp_err_t err = nvs_set_blob(handle, NVS_KEY_FACTORY_DATA, &s_factory_data, sizeof(NvsFactoryData));
    if (err == ESP_OK) err = nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
    if (err == ESP_OK) err = nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
    if (err == ESP_OK) err = nvs_commit(handle);

    update_cached_config();
    return err;
}

void nvs_storage_deinit(void) {
    if (s_storage_mutex) {
        vSemaphoreDelete(s_storage_mutex);
        s_storage_mutex = NULL;
    }
    s_storage_initialized = false;
}

esp_err_t nvs_storage_init(void) {
    if (s_storage_initialized) return ESP_OK;

    ESP_LOGI(TAG, "Initializing NVS Flash Storage...");
    if (!s_storage_mutex) {
        s_storage_mutex = xSemaphoreCreateMutex();
        if (!s_storage_mutex) {
            ESP_LOGE(TAG, "Failed to create storage mutex!");
            return ESP_ERR_NO_MEM;
        }
    }

    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS flash init failed: %s", esp_err_to_name(err));
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    nvs_handle_t handle;
    err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace '%s': %s", NVS_NAMESPACE, esp_err_to_name(err));
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    // Check if factory_data exists
    size_t f_sz = sizeof(NvsFactoryData);
    err = nvs_get_blob(handle, NVS_KEY_FACTORY_DATA, &s_factory_data, &f_sz);
    if (err != ESP_OK || f_sz != sizeof(NvsFactoryData) || !verify_factory_data_crc(&s_factory_data)) {
        // Factory data missing or corrupt. Check if legacy config_blob exists for migration!
        size_t leg_sz = sizeof(ActionBoxPersistentConfig);
        ActionBoxPersistentConfig legacy_blob;
        memset(&legacy_blob, 0, sizeof(legacy_blob));
        esp_err_t leg_err = nvs_get_blob(handle, NVS_KEY_LEGACY_BLOB, &legacy_blob, &leg_sz);
        if (leg_err == ESP_OK && leg_sz == sizeof(ActionBoxPersistentConfig) && legacy_blob.config_version == CONFIG_MAGIC_VAL) {
            err = migrate_legacy_blob(handle, &legacy_blob);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Legacy migration failed with code %d. Refusing default fallback.", err);
                nvs_close(handle);
                xSemaphoreGive(s_storage_mutex);
                return err;
            }
        } else if (leg_err == ESP_ERR_NVS_NOT_FOUND || leg_err == ESP_ERR_NOT_FOUND) {
            // NVS hoàn toàn trống (thiết bị mới xuất xưởng): ghi factory defaults lần đầu
            ESP_LOGI(TAG, "Clean NVS detected. Initializing factory defaults...");
            init_brand_new_factory_defaults(handle);
        } else {
            // config_blob tồn tại nhưng bị hỏng version hoặc sai kích thước: TỪ CHỐI FALLBACK để bảo vệ calibration!
            ESP_LOGE(TAG, "Corrupted legacy config_blob detected (err=0x%x, size=%u, magic=0x%x). Refusing default overwrite!",
                     leg_err, (unsigned)leg_sz, (unsigned)legacy_blob.config_version);
            nvs_close(handle);
            xSemaphoreGive(s_storage_mutex);
            return ESP_ERR_INVALID_VERSION;
        }
    } else {
        // Factory data exists and CRC32 is valid!
        // Load user_config
        size_t u_sz = sizeof(NvsUserConfig);
        err = nvs_get_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, &u_sz);
        if (err != ESP_OK || u_sz != sizeof(NvsUserConfig) || !verify_user_config_crc(&s_user_config)) {
            ESP_LOGW(TAG, "User config missing or invalid. Initializing default user config...");
            memset(&s_user_config, 0, sizeof(NvsUserConfig));
            s_user_config.magic = NVS_USER_CONFIG_MAGIC;
            s_user_config.schema_version = 1;
            strncpy(s_user_config.node_id, s_factory_data.device_uid, sizeof(s_user_config.node_id) - 1);
            strncpy(s_user_config.room_id, APP_DEFAULT_ROOM_ID, sizeof(s_user_config.room_id) - 1);
            for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
                snprintf(s_user_config.channel_names[i], sizeof(s_user_config.channel_names[i]), "Relay Channel %u", i + 1);
                s_user_config.startup_modes[i] = STARTUP_MODE_ALWAYS_OFF;
                s_user_config.last_states[i]   = RELAY_STATE_OFF;
                s_user_config.max_current_ma[i]= SAFETY_DEFAULT_MAX_CURRENT_MA;
            }
            s_user_config.has_assigned_subbox = false;
            memset(s_user_config.assigned_subbox_mac, 0, 6);
            s_user_config.config_version = 0;
            s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));
            nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
            nvs_commit(handle);
        }

        // Load lifecycle metadata
        size_t l_sz = sizeof(NvsLifecycleMetadata);
        err = nvs_get_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, &l_sz);
        if (err != ESP_OK || l_sz != sizeof(NvsLifecycleMetadata) || !verify_lifecycle_meta_crc(&s_lifecycle_meta)) {
            memset(&s_lifecycle_meta, 0, sizeof(NvsLifecycleMetadata));
            s_lifecycle_meta.magic = NVS_LIFECYCLE_META_MAGIC;
            s_lifecycle_meta.schema_version = 1;
            s_lifecycle_meta.owner_epoch = 1;
            s_lifecycle_meta.reset_generation = 0;
            generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
            s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));
            nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
            nvs_commit(handle);
        } else {
            generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
            s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));
            nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
            nvs_commit(handle);
        }

        update_cached_config();
        nvs_erase_key(handle, NVS_KEY_LEGACY_BLOB);
        nvs_commit(handle);
    }

    nvs_close(handle);
    s_storage_initialized = true;
    xSemaphoreGive(s_storage_mutex);
    ESP_LOGI(TAG, "NVS Storage initialized. Node ID: %s, Room: %s, Epoch: %lu",
             s_cached_config.node_id, s_cached_config.room_id, (unsigned long)s_lifecycle_meta.owner_epoch);
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

    size_t sz = sizeof(NvsUserConfig);
    err = nvs_get_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, &sz);
    if (err == ESP_OK && sz == sizeof(NvsUserConfig) && verify_user_config_crc(&s_user_config)) {
        size_t f_sz = sizeof(NvsFactoryData);
        nvs_get_blob(handle, NVS_KEY_FACTORY_DATA, &s_factory_data, &f_sz);
        update_cached_config();
        *out_cfg = s_cached_config;
        nvs_close(handle);
        xSemaphoreGive(s_storage_mutex);
        return ESP_OK;
    }

    size_t leg_sz = sizeof(ActionBoxPersistentConfig);
    ActionBoxPersistentConfig leg;
    esp_err_t leg_err = nvs_get_blob(handle, NVS_KEY_LEGACY_BLOB, &leg, &leg_sz);
    if (leg_err == ESP_OK) {
        if (leg_sz != sizeof(ActionBoxPersistentConfig) || leg.config_version != CONFIG_MAGIC_VAL) {
            nvs_close(handle);
            xSemaphoreGive(s_storage_mutex);
            return ESP_ERR_INVALID_VERSION;
        }
        *out_cfg = leg;
        s_cached_config = leg;
        nvs_close(handle);
        xSemaphoreGive(s_storage_mutex);
        return ESP_OK;
    }

    if (sz == 4 || err == ESP_ERR_INVALID_SIZE) {
        nvs_close(handle);
        xSemaphoreGive(s_storage_mutex);
        return ESP_ERR_INVALID_VERSION;
    }

    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return (err == ESP_OK) ? ESP_ERR_INVALID_VERSION : err;
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

    s_user_config.magic = NVS_USER_CONFIG_MAGIC;
    s_user_config.schema_version = 1;
    strncpy(s_user_config.node_id, cfg->node_id, sizeof(s_user_config.node_id) - 1);
    strncpy(s_user_config.room_id, cfg->room_id, sizeof(s_user_config.room_id) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        strncpy(s_user_config.channel_names[i], cfg->channel_names[i], sizeof(s_user_config.channel_names[i]) - 1);
        s_user_config.startup_modes[i] = cfg->startup_modes[i];
        s_user_config.last_states[i]   = cfg->last_states[i];
        s_user_config.max_current_ma[i]= cfg->max_current_ma[i];
    }
    memcpy(s_user_config.assigned_subbox_mac, cfg->assigned_subbox_mac, 6);
    s_user_config.has_assigned_subbox = cfg->has_assigned_subbox;
    s_user_config.config_version = cfg->config_version;
    s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));

    err = nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
    if (err == ESP_OK) {
        err = nvs_commit(handle);
        if (err == ESP_OK) {
            update_cached_config();
            ESP_LOGI(TAG, "User configuration successfully saved to NVS.");
        }
    }
    nvs_close(handle);

    xSemaphoreGive(s_storage_mutex);
    return err;
}

esp_err_t nvs_storage_factory_reset(ActionBoxPersistentConfig *out_cfg) {
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    ESP_LOGW(TAG, "FACTORY RESET: Erasing user configuration, preserving factory calibration & UID...");
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    memset(&s_user_config, 0, sizeof(NvsUserConfig));
    s_user_config.magic = NVS_USER_CONFIG_MAGIC;
    s_user_config.schema_version = 1;
    strncpy(s_user_config.node_id, s_factory_data.device_uid, sizeof(s_user_config.node_id) - 1);
    strncpy(s_user_config.room_id, APP_DEFAULT_ROOM_ID, sizeof(s_user_config.room_id) - 1);
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        snprintf(s_user_config.channel_names[i], sizeof(s_user_config.channel_names[i]), "Relay Channel %u", i + 1);
        s_user_config.startup_modes[i] = STARTUP_MODE_ALWAYS_OFF;
        s_user_config.last_states[i]   = RELAY_STATE_OFF;
        s_user_config.max_current_ma[i]= SAFETY_DEFAULT_MAX_CURRENT_MA;
    }
    s_user_config.has_assigned_subbox = false;
    memset(s_user_config.assigned_subbox_mac, 0, 6);
    s_user_config.config_version = 0;
    s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));

    s_lifecycle_meta.owner_epoch++;
    s_lifecycle_meta.reset_generation++;
    generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
    s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));

    err = nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
    if (err == ESP_OK) {
        err = nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    update_cached_config();
    if (out_cfg) {
        *out_cfg = s_cached_config;
    }

    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return err;
}

esp_err_t nvs_storage_reset_network(void) {
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    ESP_LOGW(TAG, "NETWORK RESET: Unlinking SubBox, keeping room, channel names, and calibrations...");
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    s_user_config.has_assigned_subbox = false;
    memset(s_user_config.assigned_subbox_mac, 0, 6);
    s_user_config.crc32 = calculate_crc32((const uint8_t*)&s_user_config, offsetof(NvsUserConfig, crc32));

    err = nvs_set_blob(handle, NVS_KEY_USER_CONFIG, &s_user_config, sizeof(NvsUserConfig));
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    update_cached_config();
    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return err;
}

void nvs_storage_record_relay_state(uint8_t channel, RelayState state) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT) return;
    uint8_t idx = channel - 1;

    if (s_cached_config.startup_modes[idx] != STARTUP_MODE_RESTORE_LAST) {
        return;
    }

    if (s_cached_config.last_states[idx] == state) {
        return;
    }

    int64_t now_us = esp_timer_get_time();
    int64_t elapsed_ms = (now_us - s_last_relay_save_us) / 1000;
    if (elapsed_ms < 10000) {
        s_cached_config.last_states[idx] = state;
        s_user_config.last_states[idx] = state;
        return;
    }

    s_cached_config.last_states[idx] = state;
    s_user_config.last_states[idx] = state;
    s_last_relay_save_us = now_us;
    nvs_storage_save_config(&s_cached_config);
}

const ActionBoxPersistentConfig* nvs_storage_get_cached_config(void) {
    return &s_cached_config;
}

bool nvs_storage_is_claimed(void) {
    return s_cached_config.has_assigned_subbox;
}

esp_err_t nvs_storage_get_factory_data(NvsFactoryData *out_factory) {
    if (!out_factory) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
    *out_factory = s_factory_data;
    xSemaphoreGive(s_storage_mutex);
    return ESP_OK;
}

esp_err_t nvs_storage_get_lifecycle_metadata(NvsLifecycleMetadata *out_meta) {
    if (!out_meta) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
    *out_meta = s_lifecycle_meta;
    xSemaphoreGive(s_storage_mutex);
    return ESP_OK;
}

uint32_t nvs_storage_get_owner_epoch(void) {
    return s_lifecycle_meta.owner_epoch;
}

esp_err_t nvs_storage_increment_owner_epoch(void) {
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    s_lifecycle_meta.owner_epoch++;
    s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));
    err = nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return err;
}

void nvs_storage_generate_new_boot_id(void) {
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return;
    nvs_handle_t handle;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle) == ESP_OK) {
        generate_boot_id(s_lifecycle_meta.boot_id, sizeof(s_lifecycle_meta.boot_id));
        s_lifecycle_meta.crc32 = calculate_crc32((const uint8_t*)&s_lifecycle_meta, offsetof(NvsLifecycleMetadata, crc32));
        nvs_set_blob(handle, NVS_KEY_LIFECYCLE, &s_lifecycle_meta, sizeof(NvsLifecycleMetadata));
        nvs_commit(handle);
        nvs_close(handle);
    }
    xSemaphoreGive(s_storage_mutex);
}

esp_err_t nvs_storage_write_reset_intent(const ResetIntent *intent) {
    if (!intent) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    err = nvs_set_blob(handle, NVS_KEY_RESET_INTENT, intent, sizeof(ResetIntent));
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return err;
}

esp_err_t nvs_storage_read_reset_intent(ResetIntent *out_intent) {
    if (!out_intent) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    size_t sz = sizeof(ResetIntent);
    err = nvs_get_blob(handle, NVS_KEY_RESET_INTENT, out_intent, &sz);
    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);

    if (err == ESP_OK) {
        if (sz != sizeof(ResetIntent) || out_intent->magic != RESET_INTENT_MAGIC) {
            return ESP_ERR_INVALID_VERSION;
        }
        uint32_t expected_crc = calculate_crc32((const uint8_t*)out_intent, offsetof(ResetIntent, crc32));
        if (out_intent->crc32 != expected_crc) {
            return ESP_ERR_INVALID_CRC;
        }
    }
    return err;
}

esp_err_t nvs_storage_clear_reset_intent(void) {
    if (xSemaphoreTake(s_storage_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        xSemaphoreGive(s_storage_mutex);
        return err;
    }

    nvs_erase_key(handle, NVS_KEY_RESET_INTENT);
    err = nvs_commit(handle);
    nvs_close(handle);
    xSemaphoreGive(s_storage_mutex);
    return err;
}
