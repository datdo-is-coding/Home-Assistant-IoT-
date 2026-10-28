#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
#include "common/device_lifecycle.h"
extern "C" {
#endif

typedef enum {
    LED_PATTERN_OFF        = 0,
    LED_PATTERN_ON         = 1,
    LED_PATTERN_BLINK_SLOW = 2,
    LED_PATTERN_BLINK_FAST = 3,
    LED_PATTERN_BLINK_2S   = 4,
    LED_PATTERN_PULSE_ONCE = 5,
    LED_PATTERN_ERROR_1    = 6,
    LED_PATTERN_ERROR_2    = 7,
    LED_PATTERN_ERROR_3    = 8,
    LED_PATTERN_ERROR_4    = 9
} LedDriverPattern;

esp_err_t led_driver_init(void);

void led_set_pattern(uint8_t channel, LedDriverPattern pattern);

void led_driver_tick(void);

#ifdef __cplusplus
}

void led_set_pattern(uint8_t channel, ::LedPattern pattern);

#endif
