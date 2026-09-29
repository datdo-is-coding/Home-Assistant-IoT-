/**
 * @file led_driver.cpp
 * @brief Status LED Pattern Generator Implementation
 */

#include "led_driver.h"
#include "board_pins.h"

#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "LED_DRIVER";

typedef struct {
    uint8_t    channel;
    gpio_num_t pin;
    LedPattern pattern;
    int64_t    last_toggle_us;
    bool       current_level;
    int64_t    pulse_start_us;
} LedState;

static LedState s_leds[BOARD_RELAY_CHANNEL_COUNT];

static gpio_num_t get_led_pin(uint8_t channel) {
    switch (channel) {
        case 1:  return BOARD_PIN_LED_CH1;
        case 2:  return BOARD_PIN_LED_CH2;
        default: return GPIO_NUM_NC;
    }
}

static void apply_led_level(gpio_num_t pin, bool on) {
    int level = on ? BOARD_LED_ACTIVE_LEVEL : !BOARD_LED_ACTIVE_LEVEL;
    gpio_set_level(pin, level);
}

esp_err_t led_driver_init(void) {
    ESP_LOGI(TAG, "Initializing Status LEDs (LED1: GPIO %d, LED2: GPIO %d)...",
             BOARD_PIN_LED_CH1, BOARD_PIN_LED_CH2);

    gpio_config_t io_conf = {};
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.intr_type = GPIO_INTR_DISABLE;

    uint64_t pin_mask = 0;
    pin_mask |= (1ULL << BOARD_PIN_LED_CH1);
    pin_mask |= (1ULL << BOARD_PIN_LED_CH2);
    io_conf.pin_bit_mask = pin_mask;

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) return err;

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        uint8_t ch = i + 1;
        s_leds[i].channel = ch;
        s_leds[i].pin = get_led_pin(ch);
        s_leds[i].pattern = LED_PATTERN_OFF;
        s_leds[i].last_toggle_us = 0;
        s_leds[i].current_level = false;
        s_leds[i].pulse_start_us = 0;

        apply_led_level(s_leds[i].pin, false);
    }

    return ESP_OK;
}

void led_set_pattern(uint8_t channel, LedPattern pattern) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT) return;
    uint8_t idx = channel - 1;

    s_leds[idx].pattern = pattern;
    if (pattern == LED_PATTERN_OFF) {
        s_leds[idx].current_level = false;
        apply_led_level(s_leds[idx].pin, false);
    } else if (pattern == LED_PATTERN_ON) {
        s_leds[idx].current_level = true;
        apply_led_level(s_leds[idx].pin, true);
    } else if (pattern == LED_PATTERN_PULSE_ONCE) {
        s_leds[idx].current_level = true;
        s_leds[idx].pulse_start_us = esp_timer_get_time();
        apply_led_level(s_leds[idx].pin, true);
    }
}

void led_driver_tick(void) {
    int64_t now_us = esp_timer_get_time();

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        LedState *led = &s_leds[i];

        switch (led->pattern) {
            case LED_PATTERN_OFF:
            case LED_PATTERN_ON:
                /* Static, nothing to tick */
                break;

            case LED_PATTERN_BLINK_SLOW:
            case LED_PATTERN_BLINK_FAST: {
                /* Slow: 500ms per level; fast: 100ms per level. */
                const int64_t interval_ms =
                    (led->pattern == LED_PATTERN_BLINK_SLOW) ? 500 : 100;
                int64_t elapsed_ms = (now_us - led->last_toggle_us) / 1000;
                if (elapsed_ms >= interval_ms) {
                    led->current_level = !led->current_level;
                    led->last_toggle_us = now_us;
                    apply_led_level(led->pin, led->current_level);
                }
                break;
            }

            case LED_PATTERN_PULSE_ONCE: {
                int64_t elapsed_ms = (now_us - led->pulse_start_us) / 1000;
                if (elapsed_ms >= 120) {
                    /* Pulse complete, return to OFF or ON based on relay */
                    led->pattern = LED_PATTERN_OFF;
                    led->current_level = false;
                    apply_led_level(led->pin, false);
                }
                break;
            }
        }
    }
}
