#ifndef BUTTON_HANDLER_H
#define BUTTON_HANDLER_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef BUT1_GPIO
#define BUT1_GPIO    1
#endif

#ifndef BUT2_GPIO
#define BUT2_GPIO    3
#endif

typedef enum {
    BUTTON_EVT_SHORT_PRESS    = 0,
    BUTTON_EVT_HOLD_3S        = 1,
    BUTTON_EVT_HOLD_7S        = 2,
    BUTTON_EVT_FACTORY_RESET  = 3,
} button_event_t;

typedef void (*button_event_cb_t)(int channel, button_event_t event);

esp_err_t button_handler_init(button_event_cb_t callback);

#ifdef __cplusplus
}
#endif

#endif
