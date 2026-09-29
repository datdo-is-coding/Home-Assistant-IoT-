/**
 * @file button_driver.cpp
 * @brief Non-blocking Push Button Driver Implementation
 */

#include "button_driver.h"
#include "board_pins.h"
#include "app_config.h"

#include <string.h>
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "BUTTON_DRIVER";

typedef enum {
    BTN_STATE_RELEASED = 0,
    BTN_STATE_DEBOUNCING_PRESS,
    BTN_STATE_PRESSED,
    BTN_STATE_DEBOUNCING_RELEASE
} BtnInternalState;

typedef struct {
    uint8_t          channel;
    gpio_num_t       gpio_pin;
    BtnInternalState state;
    int64_t          press_start_time_us;
    int64_t          last_transition_time_us;
    bool             long_press_dispatched;
    bool             factory_reset_dispatched;
} ButtonChannel;

static ButtonChannel s_buttons[BOARD_BUTTON_COUNT];
static button_event_cb_t s_event_callback = NULL;
static void *s_callback_user_data = NULL;
static bool s_initialized = false;

static gpio_num_t get_button_pin(uint8_t channel) {
    switch (channel) {
        case 1:  return BOARD_PIN_BUTTON_CH1;
        case 2:  return BOARD_PIN_BUTTON_CH2;
        default: return GPIO_NUM_NC;
    }
}

static inline bool read_pin_pressed(gpio_num_t pin) {
    int level = gpio_get_level(pin);
    return (level == BOARD_BUTTON_ACTIVE_LEVEL);
}

esp_err_t button_driver_init(void) {
    ESP_LOGI(TAG, "Initializing Button Driver (BUT1: GPIO %d, BUT2: GPIO %d)...",
             BOARD_PIN_BUTTON_CH1, BOARD_PIN_BUTTON_CH2);

    gpio_config_t io_conf = {};
    io_conf.mode = GPIO_MODE_INPUT;
    io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.intr_type = GPIO_INTR_DISABLE;

    uint64_t pin_mask = 0;
    pin_mask |= (1ULL << BOARD_PIN_BUTTON_CH1);
    pin_mask |= (1ULL << BOARD_PIN_BUTTON_CH2);
    io_conf.pin_bit_mask = pin_mask;

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure button GPIOs: %s", esp_err_to_name(err));
        return err;
    }

    for (uint8_t i = 0; i < BOARD_BUTTON_COUNT; i++) {
        uint8_t ch = i + 1;
        s_buttons[i].channel = ch;
        s_buttons[i].gpio_pin = get_button_pin(ch);
        s_buttons[i].state = BTN_STATE_RELEASED;
        s_buttons[i].press_start_time_us = 0;
        s_buttons[i].last_transition_time_us = 0;
        s_buttons[i].long_press_dispatched = false;
        s_buttons[i].factory_reset_dispatched = false;
    }

    s_initialized = true;
    ESP_LOGI(TAG, "Button Driver initialized successfully.");
    return ESP_OK;
}

esp_err_t button_register_callback(button_event_cb_t callback, void *user_data) {
    s_event_callback = callback;
    s_callback_user_data = user_data;
    return ESP_OK;
}

void button_driver_tick(void) {
    if (!s_initialized) return;

    int64_t now_us = esp_timer_get_time();

    for (uint8_t i = 0; i < BOARD_BUTTON_COUNT; i++) {
        ButtonChannel *btn = &s_buttons[i];
        bool is_pressed = read_pin_pressed(btn->gpio_pin);

        switch (btn->state) {
            case BTN_STATE_RELEASED:
                if (is_pressed) {
                    btn->state = BTN_STATE_DEBOUNCING_PRESS;
                    btn->last_transition_time_us = now_us;
                }
                break;

            case BTN_STATE_DEBOUNCING_PRESS:
                if (is_pressed) {
                    int64_t elapsed_ms = (now_us - btn->last_transition_time_us) / 1000;
                    if (elapsed_ms >= BUTTON_DEBOUNCE_TIME_MS) {
                        btn->state = BTN_STATE_PRESSED;
                        btn->press_start_time_us = now_us;
                        btn->long_press_dispatched = false;
                        btn->factory_reset_dispatched = false;
                        ESP_LOGD(TAG, "Ch%u Button Pressed", btn->channel);
                    }
                } else {
                    /* Glitch rejected */
                    btn->state = BTN_STATE_RELEASED;
                }
                break;

            case BTN_STATE_PRESSED:
                if (is_pressed) {
                    int64_t held_ms = (now_us - btn->press_start_time_us) / 1000;

                    if (held_ms >= BUTTON_HOLD_FACTORY_RESET_MS && !btn->factory_reset_dispatched) {
                        btn->factory_reset_dispatched = true;
                        ESP_LOGW(TAG, "Ch%u Button Held 10s: TRIGGERING FACTORY RESET EVENT", btn->channel);
                        if (s_event_callback) {
                            s_event_callback(btn->channel, BUTTON_EVENT_FACTORY_RST, s_callback_user_data);
                        }
                    } else if (held_ms >= BUTTON_LONG_PRESS_TIME_MS && !btn->long_press_dispatched && !btn->factory_reset_dispatched) {
                        btn->long_press_dispatched = true;
                        ESP_LOGI(TAG, "Ch%u Button Held 3s: LONG PRESS EVENT", btn->channel);
                        if (s_event_callback) {
                            s_event_callback(btn->channel, BUTTON_EVENT_LONG_PRESS, s_callback_user_data);
                        }
                    }
                } else {
                    btn->state = BTN_STATE_DEBOUNCING_RELEASE;
                    btn->last_transition_time_us = now_us;
                }
                break;

            case BTN_STATE_DEBOUNCING_RELEASE:
                if (!is_pressed) {
                    int64_t elapsed_ms = (now_us - btn->last_transition_time_us) / 1000;
                    if (elapsed_ms >= BUTTON_DEBOUNCE_TIME_MS) {
                        btn->state = BTN_STATE_RELEASED;
                        int64_t total_press_ms = (now_us - btn->press_start_time_us) / 1000;
                        ESP_LOGD(TAG, "Ch%u Button Released after %lld ms", btn->channel, total_press_ms);

                        if (!btn->long_press_dispatched && !btn->factory_reset_dispatched) {
                            /* Valid short press */
                            ESP_LOGI(TAG, "Ch%u Button SHORT PRESS -> Toggle Relay", btn->channel);
                            if (s_event_callback) {
                                s_event_callback(btn->channel, BUTTON_EVENT_SHORT_PRESS, s_callback_user_data);
                            }
                        } else {
                            if (s_event_callback) {
                                s_event_callback(btn->channel, BUTTON_EVENT_RELEASE, s_callback_user_data);
                            }
                        }
                    }
                } else {
                    /* Glitch back to pressed */
                    btn->state = BTN_STATE_PRESSED;
                }
                break;
        }
    }
}

bool button_is_pressed(uint8_t channel) {
    if (channel < 1 || channel > BOARD_BUTTON_COUNT) return false;
    return read_pin_pressed(get_button_pin(channel));
}
