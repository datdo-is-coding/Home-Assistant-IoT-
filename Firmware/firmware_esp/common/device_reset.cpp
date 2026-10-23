#include "device_reset.h"
#include "nvs_storage.h"
#include "board_pins.h"
#include "relay_driver.h"
#include "device_lifecycle.h"

#include <string.h>
#include <atomic>
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifndef ESP_PLATFORM
// For host testing / non-ESP build
extern "C" void esp_restart(void);
#else
#include "esp_system.h"
#endif

static const char *TAG = "DEVICE_RESET";

// Weak linkage hooks so host tests or configurations without voice/espnow don't fail linker
#ifdef __cplusplus
extern "C" {
#endif
__attribute__((weak)) void voice_capture_stop_streaming(void) {}
__attribute__((weak)) esp_err_t espnow_transport_clear_peers(void) { return ESP_OK; }
#ifdef __cplusplus
}
#endif

struct ArmedResetState {
    std::atomic<bool> armed{false};
    ResetKind kind{ResetKind::NONE};
    uint32_t owner_epoch{0};
    char operation_id[64]{0};
    uint64_t armed_at_ms{0};
};

static ArmedResetState s_armed_reset;
static std::atomic<bool> s_reset_locked{false};

bool is_reset_locked(void) {
    return s_reset_locked.load();
}

void cancel_armed_reset(void) {
    s_armed_reset.armed.store(false);
    s_armed_reset.kind = ResetKind::NONE;
    s_armed_reset.owner_epoch = 0;
    memset(s_armed_reset.operation_id, 0, sizeof(s_armed_reset.operation_id));
    s_armed_reset.armed_at_ms = 0;
}

esp_err_t prepare_reset(ResetKind kind, const char* operation_id, uint32_t owner_epoch) {
    if (kind == ResetKind::NONE) return ESP_ERR_INVALID_ARG;
    if (!operation_id || strlen(operation_id) == 0) return ESP_ERR_INVALID_ARG;

    uint32_t current_epoch = nvs_storage_get_owner_epoch();
    if (owner_epoch < current_epoch) {
        ESP_LOGW(TAG, "prepare_reset rejected: old epoch %lu < current %lu",
                 (unsigned long)owner_epoch, (unsigned long)current_epoch);
        return ESP_ERR_INVALID_VERSION;
    }

    s_armed_reset.kind = kind;
    s_armed_reset.owner_epoch = owner_epoch;
    strncpy(s_armed_reset.operation_id, operation_id, sizeof(s_armed_reset.operation_id) - 1);
    s_armed_reset.operation_id[sizeof(s_armed_reset.operation_id) - 1] = '\0';
    s_armed_reset.armed_at_ms = (uint64_t)(esp_timer_get_time() / 1000);
    s_armed_reset.armed.store(true);

    ESP_LOGI(TAG, "Reset prepared: kind=%d, op_id=%s, epoch=%lu",
             (int)kind, s_armed_reset.operation_id, (unsigned long)owner_epoch);
    return ESP_OK;
}

esp_err_t execute_confirmed_reset(ResetKind kind, const char* operation_id) {
    if (kind == ResetKind::NONE) return ESP_ERR_INVALID_ARG;

    uint32_t epoch = nvs_storage_get_owner_epoch();
    if (s_armed_reset.armed.load()) {
        if (s_armed_reset.kind != kind) {
            ESP_LOGE(TAG, "execute_confirmed_reset mismatch kind (%d != %d)",
                     (int)kind, (int)s_armed_reset.kind);
            return ESP_ERR_INVALID_STATE;
        }
        if (operation_id && strlen(operation_id) > 0 &&
            strcmp(s_armed_reset.operation_id, operation_id) != 0) {
            ESP_LOGE(TAG, "execute_confirmed_reset mismatch op_id (%s != %s)",
                     operation_id, s_armed_reset.operation_id);
            return ESP_ERR_INVALID_STATE;
        }
        epoch = s_armed_reset.owner_epoch;
        cancel_armed_reset();
    }

    ESP_LOGW(TAG, "=== EXECUTING SAFE RESET (kind=%d, op_id=%s, epoch=%lu) ===",
             (int)kind, operation_id ? operation_id : "none", (unsigned long)epoch);

    // 1. Record reset_intent into NVS (state = INTENT_RECORDED)
    ResetIntent intent{};
    intent.magic = RESET_INTENT_MAGIC;
    intent.state = (uint8_t)ResetIntentState::INTENT_RECORDED;
    intent.kind = (uint8_t)kind;
    intent.step = 1;
    intent.owner_epoch = epoch;
    if (operation_id) {
        strncpy(intent.operation_id, operation_id, sizeof(intent.operation_id) - 1);
    }
    intent.crc32 = calculate_crc32((const uint8_t*)&intent, offsetof(ResetIntent, crc32));
    esp_err_t err = nvs_storage_write_reset_intent(&intent);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to write reset intent to NVS: %d", err);
        return err;
    }

    // 2. Lock control commands, stop audio streaming
    s_reset_locked.store(true);
    voice_capture_stop_streaming();

    // 3. Force ALL relays to OFF (channel 1..BOARD_RELAY_CHANNEL_COUNT)
    // Ensures latching relay pulses complete before flash operations or reboot!
    for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ch++) {
        relay_off(ch);
    }

    // 4. Update reset_intent in NVS (state = RELAYS_OFF)
    intent.state = (uint8_t)ResetIntentState::RELAYS_OFF;
    intent.step = 4;
    intent.crc32 = calculate_crc32((const uint8_t*)&intent, offsetof(ResetIntent, crc32));
    err = nvs_storage_write_reset_intent(&intent);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to update reset intent in NVS: %d", err);
        return err;
    }

    // 5. Selective flash erase & peer RAM cleanup
    if (kind == ResetKind::REBOOT) {
        nvs_storage_generate_new_boot_id();
    } else if (kind == ResetKind::NETWORK_RESET) {
        espnow_transport_clear_peers();
        nvs_storage_reset_network();
    } else if (kind == ResetKind::FACTORY_RESET) {
        espnow_transport_clear_peers();
        nvs_storage_factory_reset(NULL);
    }

    // 6. Clear reset_intent from NVS, commit
    nvs_storage_clear_reset_intent();

    // 7. Delay 100ms then call esp_restart()
    vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();

    return ESP_OK;
}

bool resume_interrupted_reset(void) {
    ResetIntent intent{};
    esp_err_t err = nvs_storage_read_reset_intent(&intent);
    if (err != ESP_OK || intent.state == (uint8_t)ResetIntentState::NONE) {
        return false;
    }

    ESP_LOGW(TAG, "=== RESUMING INTERRUPTED RESET: state=%u, kind=%u, op_id=%s ===",
             intent.state, intent.kind, intent.operation_id);

    // Lock commands and stop streaming immediately
    s_reset_locked.store(true);
    voice_capture_stop_streaming();

    // Always ensure ALL relays are OFF
    for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ch++) {
        relay_off(ch);
    }

    // Complete selective reset
    ResetKind kind = (ResetKind)intent.kind;
    if (kind == ResetKind::REBOOT) {
        nvs_storage_generate_new_boot_id();
    } else if (kind == ResetKind::NETWORK_RESET) {
        espnow_transport_clear_peers();
        nvs_storage_reset_network();
    } else if (kind == ResetKind::FACTORY_RESET) {
        espnow_transport_clear_peers();
        nvs_storage_factory_reset(NULL);
    }

    // Clear reset intent
    nvs_storage_clear_reset_intent();
    s_reset_locked.store(false);

    ESP_LOGI(TAG, "Interrupted reset recovered and completed successfully.");
    return true;
}
