#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t ota_updater_init(void);

esp_err_t ota_updater_start_http_pull(const char *download_url, size_t expected_size, const char *expected_md5);

bool ota_updater_is_in_progress(void);

#ifdef __cplusplus
}
#endif
