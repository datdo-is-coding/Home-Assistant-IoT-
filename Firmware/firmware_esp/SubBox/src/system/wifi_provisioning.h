#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t wifi_provisioning_start(void);

void wifi_provisioning_stop(void);

bool wifi_provisioning_is_active(void);

#ifdef __cplusplus
}
#endif
