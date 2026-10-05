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
    LED_PATTERN_ON         = 1, /* Solid ON: Fault / Error alert */
    LED_PATTERN_BLINK_SLOW = 2, /* 500ms ON / 500ms OFF */
    LED_PATTERN_BLINK_FAST = 3, /* 100ms ON / 100ms OFF: Connected to system (nháy liên tục) */
    LED_PATTERN_BLINK_2S   = 4, /* 1000ms ON / 1000ms OFF: Disconnected from SubBox (nháy từ từ 2s 1 lần) */
    LED_PATTERN_ERROR_1 = 6,
    LED_PATTERN_ERROR_2 = 7,
    LED_PATTERN_ERROR_3 = 8,
    LED_PATTERN_ERROR_4 = 9,
    LED_PATTERN_PULSE_ONCE = 5  /* 100ms: Command ACK confirmation */
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
