#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the OTA subsystem.
 * Confirms boot integrity (cancels rollback if app was in test/pending-verify state).
 * Logs running and next OTA partitions.
 *
 * @return ESP_OK on success.
 */
esp_err_t ota_updater_init(void);

/**
 * @brief Start a background OTA firmware update by pulling from a Gateway HTTP URL.
 * Spawns a dedicated FreeRTOS task with 8KB+ stack.
 *
 * @param download_url  Full HTTP URL (e.g. "http://192.168.1.50:8000/api/ota/download/firmware.bin")
 * @param expected_size Expected binary size in bytes (0 if unknown)
 * @param expected_md5  Expected 32-char hex MD5 string (NULL if not verified)
 * @return ESP_OK if task was spawned successfully, or ESP_ERR_INVALID_STATE if already running.
 */
esp_err_t ota_updater_start_http_pull(const char *download_url, size_t expected_size, const char *expected_md5);

/**
 * @brief Check if an OTA update is currently in progress.
 *
 * @return true if OTA task is actively downloading or flashing.
 */
bool ota_updater_is_in_progress(void);

#ifdef __cplusplus
}
#endif
