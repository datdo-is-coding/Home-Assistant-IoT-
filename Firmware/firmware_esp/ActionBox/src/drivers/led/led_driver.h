/**
 * @file led_driver.h
 * @brief Status LED Pattern Generator Driver for ActionBox
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    LED_PATTERN_OFF        = 0,
    LED_PATTERN_ON         = 1,
    LED_PATTERN_BLINK_SLOW = 2, /* 1 Hz: Waiting for network / pairing */
    LED_PATTERN_BLINK_FAST = 3, /* 5 Hz: Overcurrent / Hardware Fault */
    LED_PATTERN_PULSE_ONCE = 4  /* 100ms: Command ACK confirmation */
} LedPattern;

/**
 * @brief Initialize Status LED GPIOs and timer
 * @return ESP_OK on success
 */
esp_err_t led_driver_init(void);

/**
 * @brief Set visual pattern for a specific channel's LED
 * @param channel Channel ID (1 for LED1, 2 for LED2)
 * @param pattern Desired LedPattern
 */
void led_set_pattern(uint8_t channel, LedPattern pattern);

/**
 * @brief Non-blocking tick called periodically by FreeRTOS or esp_timer
 */
void led_driver_tick(void);

#ifdef __cplusplus
}
#endif
