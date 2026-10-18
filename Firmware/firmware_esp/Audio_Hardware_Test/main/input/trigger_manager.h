#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t trigger_manager_init(void);

trigger_source_t trigger_manager_poll(void);

bool trigger_manager_poll_stop(void);

bool trigger_manager_is_button_down(void);

#ifdef __cplusplus
}
#endif
