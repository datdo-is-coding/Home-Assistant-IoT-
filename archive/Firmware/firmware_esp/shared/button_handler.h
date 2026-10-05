/*
 * Button Handler — Shared Hardware Abstraction
 * DTV Smart Home — Used by T1 Actuator Nodes
 *
 * Extracted from main.c button_monitor_task for reuse.
 * Features:
 *   - Short press: toggle relay
 *   - Long press 10s: factory reset (keeps device_id)
 *   - Configurable GPIO pins
 *   - Debounce with 50ms polling
 */

#ifndef BUTTON_HANDLER_H
#define BUTTON_HANDLER_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Default GPIO assignments — override in t1_config.h if different
 * Matches schematic: IO1 (BUT1), IO3 (BUT2), internal pull-up
 */
#ifndef BUT1_GPIO
#define BUT1_GPIO    1
#endif

#ifndef BUT2_GPIO
#define BUT2_GPIO    3
#endif

/**
 * @brief Callback type for button events.
 * @param channel  Button channel (1 or 2)
 * @param event    BUTTON_EVT_SHORT_PRESS or BUTTON_EVT_FACTORY_RESET
 */
typedef enum {
    BUTTON_EVT_SHORT_PRESS    = 0,  /* Short press (< 3s) */
    BUTTON_EVT_HOLD_3S        = 1,  /* Held for 3 seconds (warning) */
    BUTTON_EVT_HOLD_7S        = 2,  /* Held for 7 seconds (final warning) */
    BUTTON_EVT_FACTORY_RESET  = 3,  /* Held for 10 seconds (execute reset) */
} button_event_t;

typedef void (*button_event_cb_t)(int channel, button_event_t event);

/**
 * @brief Initialize button GPIOs and start monitoring task.
 * @param callback  Function to call on button events
 * @return ESP_OK on success
 */
esp_err_t button_handler_init(button_event_cb_t callback);

#ifdef __cplusplus
}
#endif

#endif /* BUTTON_HANDLER_H */
