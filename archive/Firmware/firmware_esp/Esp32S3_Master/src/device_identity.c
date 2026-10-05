/*
 * AETHERIA OS — Commercial Device Identity & Lifecycle Manager Implementation
 */

#include "device_identity.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "esp_system.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <string.h>
#include <stdio.h>

static const char *TAG = "DEVICE_IDENTITY";

#define NVS_HW_ID_NAMESPACE   "hw_id"
#define NVS_USER_ID_NAMESPACE "user_id"

static hardware_identity_t s_hw;
static user_identity_t s_user;
static device_lifecycle_state_t s_state = DEVICE_STATE_FACTORY_NEW;
static bool s_initialized = false;

/* ─── State String Mapping ────────────────────────────────────────────── */

const char *device_identity_state_str(device_lifecycle_state_t state)
{
    switch (state) {
        case DEVICE_STATE_FACTORY_NEW:  return "FACTORY_NEW";
        case DEVICE_STATE_PROVISIONING: return "PROVISIONING";
        case DEVICE_STATE_CLAIMED:      return "CLAIMED";
        case DEVICE_STATE_READY:        return "READY";
        case DEVICE_STATE_RECOVERY:     return "RECOVERY";
        default:                        return "UNKNOWN";
    }
}

device_lifecycle_state_t device_identity_get_state(void)
{
    return s_state;
}

void device_identity_set_state(device_lifecycle_state_t state)
{
    ESP_LOGI(TAG, "🔄 State Transition: %s -> %s",
             device_identity_state_str(s_state), device_identity_state_str(state));
    s_state = state;
}

const hardware_identity_t *device_identity_get_hardware(void)
{
    return &s_hw;
}

const user_identity_t *device_identity_get_user(void)
{
    return &s_user;
}

const char *device_identity_get_id(void)
{
    return s_hw.device_id;
}

/* ─── Initialization ──────────────────────────────────────────────────── */

esp_err_t device_identity_init(void)
{
    if (s_initialized) {
        return ESP_OK;
    }

    memset(&s_hw, 0, sizeof(s_hw));
    memset(&s_user, 0, sizeof(s_user));

    /* 1. Read silicon eFuse MAC address (Globally Unique) */
    esp_read_mac(s_hw.mac_raw, ESP_MAC_WIFI_STA);
    snprintf(s_hw.mac_str, sizeof(s_hw.mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
             s_hw.mac_raw[0], s_hw.mac_raw[1], s_hw.mac_raw[2],
             s_hw.mac_raw[3], s_hw.mac_raw[4], s_hw.mac_raw[5]);

    /* 2. Load or generate Hardware Identity (stored in protected namespace "hw_id") */
    nvs_handle_t hw_handle;
    esp_err_t err = nvs_open(NVS_HW_ID_NAMESPACE, NVS_READWRITE, &hw_handle);
    if (err == ESP_OK) {
        size_t id_len = sizeof(s_hw.device_id);
        size_t ser_len = sizeof(s_hw.serial);
        size_t hw_len = sizeof(s_hw.hardware);

        bool need_save = false;
        if (nvs_get_str(hw_handle, "dev_id", s_hw.device_id, &id_len) != ESP_OK || strlen(s_hw.device_id) == 0) {
            /* Generate unique device_id from lower 4 bytes of silicon MAC */
            snprintf(s_hw.device_id, sizeof(s_hw.device_id), "node_%02x%02x%02x%02x",
                     s_hw.mac_raw[2], s_hw.mac_raw[3], s_hw.mac_raw[4], s_hw.mac_raw[5]);
            nvs_set_str(hw_handle, "dev_id", s_hw.device_id);
            need_save = true;
        }

        if (nvs_get_str(hw_handle, "serial", s_hw.serial, &ser_len) != ESP_OK || strlen(s_hw.serial) == 0) {
            /* Generate commercial serial: S3-2026-XXXXXX */
            uint32_t ser_num = ((uint32_t)s_hw.mac_raw[3] << 16) |
                               ((uint32_t)s_hw.mac_raw[4] << 8) |
                               ((uint32_t)s_hw.mac_raw[5]);
            snprintf(s_hw.serial, sizeof(s_hw.serial), "S3-2026-%06lu", (unsigned long)(ser_num % 1000000));
            nvs_set_str(hw_handle, "serial", s_hw.serial);
            need_save = true;
        }

        if (nvs_get_str(hw_handle, "hardware", s_hw.hardware, &hw_len) != ESP_OK || strlen(s_hw.hardware) == 0) {
            strncpy(s_hw.hardware, "esp32s3", sizeof(s_hw.hardware) - 1);
            nvs_set_str(hw_handle, "hardware", s_hw.hardware);
            need_save = true;
        }

        if (need_save) {
            nvs_commit(hw_handle);
            ESP_LOGI(TAG, "🆕 Generated & Saved new Hardware Identity in NVS");
        }
        nvs_close(hw_handle);
    } else {
        /* Fallback if NVS error */
        snprintf(s_hw.device_id, sizeof(s_hw.device_id), "node_%02x%02x%02x%02x",
                 s_hw.mac_raw[2], s_hw.mac_raw[3], s_hw.mac_raw[4], s_hw.mac_raw[5]);
        snprintf(s_hw.serial, sizeof(s_hw.serial), "S3-2026-000183");
        strncpy(s_hw.hardware, "esp32s3", sizeof(s_hw.hardware) - 1);
    }

    ESP_LOGI(TAG, "🏭 ================= HARDWARE IDENTITY =================");
    ESP_LOGI(TAG, "🏭 Device ID: %s", s_hw.device_id);
    ESP_LOGI(TAG, "🏭 Hardware:  %s", s_hw.hardware);
    ESP_LOGI(TAG, "🏭 Serial:    %s", s_hw.serial);
    ESP_LOGI(TAG, "🏭 MAC:       %s", s_hw.mac_str);
    ESP_LOGI(TAG, "🏭 =====================================================");

    /* 3. Load User Identity (stored in user-modifiable namespace "user_id") */
    nvs_handle_t usr_handle;
    err = nvs_open(NVS_USER_ID_NAMESPACE, NVS_READONLY, &usr_handle);
    if (err == ESP_OK) {
        uint8_t prov = 0;
        nvs_get_u8(usr_handle, "prov", &prov);

        size_t len;
        len = sizeof(s_user.name);
        nvs_get_str(usr_handle, "name", s_user.name, &len);

        len = sizeof(s_user.room);
        nvs_get_str(usr_handle, "room", s_user.room, &len);

        len = sizeof(s_user.location);
        nvs_get_str(usr_handle, "location", s_user.location, &len);

        len = sizeof(s_user.description);
        nvs_get_str(usr_handle, "desc", s_user.description, &len);

        len = sizeof(s_user.rl1_name);
        nvs_get_str(usr_handle, "rl1", s_user.rl1_name, &len);

        len = sizeof(s_user.rl2_name);
        nvs_get_str(usr_handle, "rl2", s_user.rl2_name, &len);

        uint32_t ver = 0;
        nvs_get_u32(usr_handle, "cfg_ver", &ver);
        s_user.cfg_version = ver;

        s_user.is_provisioned = (prov == 1 && strlen(s_user.name) > 0);
        nvs_close(usr_handle);
    }

    if (s_user.is_provisioned) {
        s_state = DEVICE_STATE_READY;
        ESP_LOGI(TAG, "👤 User Identity [CLAIMED / READY]: Name='%s', Room='%s', Loc='%s', Ver=%lu",
                 s_user.name, s_user.room, s_user.location, (unsigned long)s_user.cfg_version);
    } else {
        s_state = DEVICE_STATE_FACTORY_NEW;
        strncpy(s_user.name, "ESP32-S3 Voice Node", sizeof(s_user.name) - 1);
        strncpy(s_user.room, "unassigned", sizeof(s_user.room) - 1);
        strncpy(s_user.location, "Chưa gán vị trí", sizeof(s_user.location) - 1);
        strncpy(s_user.description, "Voice node", sizeof(s_user.description) - 1);
        strncpy(s_user.rl1_name, "light", sizeof(s_user.rl1_name) - 1);
        strncpy(s_user.rl2_name, "fan", sizeof(s_user.rl2_name) - 1);
        s_user.cfg_version = 0;
        ESP_LOGW(TAG, "📦 Device State: [FACTORY_NEW] — Awaiting Gateway Claiming");
    }

    s_initialized = true;
    return ESP_OK;
}

/* ─── Save User Configuration ─────────────────────────────────────────── */

esp_err_t device_identity_save_user_config(const user_identity_t *config)
{
    if (!config) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_USER_ID_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace '%s': %s", NVS_USER_ID_NAMESPACE, esp_err_to_name(err));
        return err;
    }

    nvs_set_u8(h, "prov", 1);
    nvs_set_str(h, "name", config->name);
    nvs_set_str(h, "room", config->room);
    nvs_set_str(h, "location", config->location);
    nvs_set_str(h, "desc", config->description);
    nvs_set_str(h, "rl1", config->rl1_name);
    nvs_set_str(h, "rl2", config->rl2_name);
    nvs_set_u32(h, "cfg_ver", config->cfg_version);

    err = nvs_commit(h);
    nvs_close(h);

    if (err == ESP_OK) {
        memcpy(&s_user, config, sizeof(s_user));
        s_user.is_provisioned = true;
        device_identity_set_state(DEVICE_STATE_READY);
        ESP_LOGI(TAG, "✨ Saved User Identity & Promoted to READY: Name='%s', Room='%s', Loc='%s'",
                 s_user.name, s_user.room, s_user.location);
    }
    return err;
}

/* ─── Factory Reset ───────────────────────────────────────────────────── */

esp_err_t device_identity_factory_reset(void)
{
    ESP_LOGW(TAG, "⚠️ =========================================================");
    ESP_LOGW(TAG, "⚠️ FACTORY RESET TRIGGERED!");
    ESP_LOGW(TAG, "⚠️ Erasing User Identity, Wi-Fi & Gateway Bindings...");
    ESP_LOGW(TAG, "⚠️ KEEPING Hardware Identity: '%s' (Serial: %s)", s_hw.device_id, s_hw.serial);
    ESP_LOGW(TAG, "⚠️ =========================================================");

    /* 1. Erase user_id namespace */
    nvs_handle_t h;
    if (nvs_open(NVS_USER_ID_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
    }

    /* 2. Erase legacy nvs_relay namespace if present */
    if (nvs_open("nvs_relay", NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
    }

    device_identity_set_state(DEVICE_STATE_FACTORY_NEW);

    /* 3. Delay and restart */
    vTaskDelay(pdMS_TO_TICKS(1200));
    esp_restart();
    return ESP_OK;
}

/* ─── Export JSON ─────────────────────────────────────────────────────── */

char *device_identity_export_json(void)
{
    cJSON *root = cJSON_CreateObject();
    if (!root) return NULL;

    cJSON *hw = cJSON_CreateObject();
    cJSON_AddStringToObject(hw, "device_id", s_hw.device_id);
    cJSON_AddStringToObject(hw, "hardware", s_hw.hardware);
    cJSON_AddStringToObject(hw, "serial", s_hw.serial);
    cJSON_AddStringToObject(hw, "mac", s_hw.mac_str);
    cJSON_AddItemToObject(root, "hardware_identity", hw);

    cJSON *user = cJSON_CreateObject();
    cJSON_AddStringToObject(user, "name", s_user.name);
    cJSON_AddStringToObject(user, "room", s_user.room);
    cJSON_AddStringToObject(user, "location", s_user.location);
    cJSON_AddStringToObject(user, "description", s_user.description);
    cJSON_AddStringToObject(user, "rl1", s_user.rl1_name);
    cJSON_AddStringToObject(user, "rl2", s_user.rl2_name);
    cJSON_AddItemToObject(root, "user_identity", user);

    cJSON_AddStringToObject(root, "state", device_identity_state_str(s_state));
    cJSON_AddNumberToObject(root, "cfg_version", s_user.cfg_version);

    char *json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return json_str;
}
