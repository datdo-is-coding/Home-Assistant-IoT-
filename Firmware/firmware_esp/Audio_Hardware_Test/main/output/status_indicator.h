#pragma once
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize status LEDs (LED1 on GPIO 48, LED2 on GPIO 47).
 */
esp_err_t status_indicator_init(void);

/**
 * @brief Update LED states based on application state.
 */
void status_indicator_set_state(app_state_t state);

#ifdef __cplusplus
}
#endif
