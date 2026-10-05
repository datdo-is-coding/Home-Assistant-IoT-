/*
 * Relay Driver — Implementation
 * DTV Smart Home — Shared between T1 Actuator Nodes
 *
 * Controls 2-channel relay via GPIO with Active-LOW optocoupler (PC817).
 * Extracted from mqtt_relay.c for clean reuse in 3-tier architecture.
 */

#include "relay_driver.h"

#include <string.h>
#include "esp_log.h"
#include "driver/gpio.h"

static const char *TAG = "RELAY_DRV";

static const int relay_gpio[2] = {RELAY_CH1_GPIO, RELAY_CH2_GPIO};
static volatile bool relay_state[2] = {false, false};

esp_err_t relay_driver_init(void)
{
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = (1ULL << RELAY_CH1_GPIO) | (1ULL << RELAY_CH2_GPIO),
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure relay GPIOs: %s", esp_err_to_name(err));
        return err;
    }

    /* Set both relays to OFF (Active-LOW: OFF = GPIO HIGH) */
    for (int i = 0; i < 2; i++) {
#if RELAY_ACTIVE_LOW
        gpio_set_level(relay_gpio[i], 1);  /* HIGH = OFF for Active-LOW */
#else
        gpio_set_level(relay_gpio[i], 0);  /* LOW = OFF for Active-HIGH */
#endif
        relay_state[i] = false;
    }

    ESP_LOGI(TAG, "Relay driver initialized: CH1=GPIO%d, CH2=GPIO%d, Active-LOW=%s",
             RELAY_CH1_GPIO, RELAY_CH2_GPIO, RELAY_ACTIVE_LOW ? "YES" : "NO");
    return ESP_OK;
}

void relay_driver_set(int channel, bool on)
{
    if (channel < 1 || channel > 2) {
        ESP_LOGW(TAG, "Invalid relay channel: %d (must be 1 or 2)", channel);
        return;
    }

    int idx = channel - 1;
    relay_state[idx] = on;

#if RELAY_ACTIVE_LOW
    /* Active-LOW: ON=GPIO LOW (0), OFF=GPIO HIGH (1) */
    gpio_set_level(relay_gpio[idx], on ? 0 : 1);
#else
    gpio_set_level(relay_gpio[idx], on ? 1 : 0);
#endif

    ESP_LOGI(TAG, "Relay CH%d (GPIO%d) → %s", channel, relay_gpio[idx], on ? "ON" : "OFF");
}

bool relay_driver_get(int channel)
{
    if (channel < 1 || channel > 2) return false;
    return relay_state[channel - 1];
}

bool relay_driver_toggle(int channel)
{
    if (channel < 1 || channel > 2) return false;
    bool new_state = !relay_state[channel - 1];
    relay_driver_set(channel, new_state);
    return new_state;
}

uint8_t relay_driver_get_bitmask(void)
{
    uint8_t mask = 0;
    if (relay_state[0]) mask |= (1 << 0);
    if (relay_state[1]) mask |= (1 << 1);
    return mask;
}
