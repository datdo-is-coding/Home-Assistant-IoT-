#pragma once
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t status_indicator_init(void);

void status_indicator_set_state(app_state_t state);

#ifdef __cplusplus
}
#endif
