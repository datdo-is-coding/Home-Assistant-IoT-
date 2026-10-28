#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#include "common/device_lifecycle.h"

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

#ifdef __cplusplus
}
typedef void (*button_event_cb_t)(uint8_t channel, ButtonAction action, void *user_data);
extern "C" {
#else
typedef void (*button_event_cb_t)(uint8_t channel, uint8_t action, void *user_data);
#endif

esp_err_t button_driver_init(void);

esp_err_t button_register_callback(button_event_cb_t callback, void *user_data);

void button_driver_tick(void);

bool button_is_pressed(uint8_t channel);

#ifdef __cplusplus
}
#endif
