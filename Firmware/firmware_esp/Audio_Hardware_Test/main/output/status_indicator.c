#include "status_indicator.h"
#include "../app_config.h"

#include "driver/gpio.h"

esp_err_t status_indicator_init(void)
{
    gpio_config_t led_cfg = {
        .pin_bit_mask = (1ULL << LED1_GPIO) | (1ULL << LED2_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&led_cfg);

    gpio_set_level(LED1_GPIO, 1);
    gpio_set_level(LED2_GPIO, 0);

    return ESP_OK;
}

void status_indicator_set_state(app_state_t state)
{
    switch (state) {
    case STATE_IDLE:
        gpio_set_level(LED1_GPIO, 1);
        gpio_set_level(LED2_GPIO, 0);
        break;

    case STATE_RECORDING:
        gpio_set_level(LED1_GPIO, 1);
        gpio_set_level(LED2_GPIO, 1);
        break;

    case STATE_FINALIZE:
    case STATE_PLAYING:
        gpio_set_level(LED1_GPIO, 0);
        gpio_set_level(LED2_GPIO, 1);
        break;
    }
}
