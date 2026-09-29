/**
 * @file button_driver.h
 * @brief Non-blocking Physical Push Button Driver with Debounce & Long-Press Detection
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BUTTON_EVENT_NONE        = 0,
    BUTTON_EVENT_SHORT_PRESS = 1,
    BUTTON_EVENT_LONG_PRESS  = 2,
    BUTTON_EVENT_RELEASE     = 3,
    BUTTON_EVENT_FACTORY_RST = 4
} ButtonEvent;

/**
 * @brief Button event callback prototype
 * @param channel Channel ID (1 for BUT1, 2 for BUT2)
 * @param event ButtonEvent type
 * @param user_data Optional user context pointer
 */
typedef void (*button_event_cb_t)(uint8_t channel, ButtonEvent event, void *user_data);

/**
 * @brief Initialize Button GPIOs (pull-ups, non-blocking scan timer)
 * @return ESP_OK on success
 */
esp_err_t button_driver_init(void);

/**
 * @brief Register an application callback for button events
 * @param callback Callback function pointer
 * @param user_data User context pointer
 * @return ESP_OK on success
 */
esp_err_t button_register_callback(button_event_cb_t callback, void *user_data);

/**
 * @brief Non-blocking periodic tick called by button_task or esp_timer
 * Updates debounce state machine and dispatches events.
 */
void button_driver_tick(void);

/**
 * @brief Direct raw read of button electrical level (for diagnostics)
 * @param channel Channel ID (1 or 2)
 * @return true if currently pressed, false otherwise
 */
bool button_is_pressed(uint8_t channel);

#ifdef __cplusplus
}
#endif
