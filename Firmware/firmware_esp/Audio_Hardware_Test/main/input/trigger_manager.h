#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize hardware buttons (BUT1, BOOT) and USB command listener.
 */
esp_err_t trigger_manager_init(void);

/**
 * @brief Poll buttons and USB commands to see if a start-record trigger occurred.
 *
 * @return trigger_source_t TRIGGER_NONE, TRIGGER_BUTTON, or TRIGGER_USB_CMD.
 */
trigger_source_t trigger_manager_poll(void);

/**
 * @brief Check if the stop command was requested via USB or button.
 *
 * @return true if stop requested.
 */
bool trigger_manager_poll_stop(void);

/**
 * @brief Check if BUT1 or BOOT is currently held down.
 */
bool trigger_manager_is_button_down(void);

#ifdef __cplusplus
}
#endif
