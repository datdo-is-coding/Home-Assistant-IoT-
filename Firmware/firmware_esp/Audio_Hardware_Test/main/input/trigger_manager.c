#include "trigger_manager.h"
#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"

#include "../output/usb_stream.h"

static const char *TAG = "TRIGGER_MGR";

static bool s_last_but1_state = true;
static bool s_last_boot_state = true;
static int64_t s_last_press_time = 0;

esp_err_t trigger_manager_init(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << BUT1_GPIO) | (1ULL << BOOT_GPIO),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "✅ Buttons configured: BUT1 (GPIO%d), BOOT (GPIO%d) with pullup", BUT1_GPIO, BOOT_GPIO);
    }
    s_last_but1_state = gpio_get_level(BUT1_GPIO);
    s_last_boot_state = gpio_get_level(BOOT_GPIO);
    s_last_press_time = esp_timer_get_time();
    return err;
}

trigger_source_t trigger_manager_poll(void)
{
    /* 1. Check USB incoming command */
    char cmd = usb_stream_poll_cmd();
    if (cmd == 'r' || cmd == 'R') {
        ESP_LOGI(TAG, "📩 USB Command: START RECORDING ('%c')", cmd);
        return TRIGGER_USB_CMD;
    }

    /* 2. Check Physical Buttons with debounce (200ms) */
    int64_t now = esp_timer_get_time();
    bool cur_but1 = (gpio_get_level(BUT1_GPIO) == 0);
    bool cur_boot = (gpio_get_level(BOOT_GPIO) == 0);

    bool triggered = false;
    if ((cur_but1 && !s_last_but1_state) || (cur_boot && !s_last_boot_state)) {
        if ((now - s_last_press_time) > 200000) { /* 200ms debounce */
            triggered = true;
            s_last_press_time = now;
        }
    }

    s_last_but1_state = cur_but1;
    s_last_boot_state = cur_boot;

    if (triggered) {
        return TRIGGER_BUTTON;
    }

    return TRIGGER_NONE;
}

bool trigger_manager_poll_stop(void)
{
    char cmd = usb_stream_poll_cmd();
    if (cmd == 's' || cmd == 'S') {
        ESP_LOGI(TAG, "📩 USB Command: STOP RECORDING ('%c')", cmd);
        return true;
    }

    /* Check if button pressed again to stop */
    int64_t now = esp_timer_get_time();
    bool cur_but1 = (gpio_get_level(BUT1_GPIO) == 0);
    bool cur_boot = (gpio_get_level(BOOT_GPIO) == 0);

    bool pressed_again = false;
    if ((cur_but1 && !s_last_but1_state) || (cur_boot && !s_last_boot_state)) {
        if ((now - s_last_press_time) > 400000) { /* 400ms after start */
            pressed_again = true;
            s_last_press_time = now;
        }
    }

    s_last_but1_state = cur_but1;
    s_last_boot_state = cur_boot;

    return pressed_again;
}

bool trigger_manager_is_button_down(void)
{
    return (gpio_get_level(BUT1_GPIO) == 0 || gpio_get_level(BOOT_GPIO) == 0);
}
