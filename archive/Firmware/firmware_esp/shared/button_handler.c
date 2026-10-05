/*
 * Button Handler — Implementation
 * DTV Smart Home — Shared between T1 Actuator Nodes
 *
 * FreeRTOS task that monitors physical push buttons with debounce.
 * Extracted from Esp32S3_Master/main.c button_monitor_task.
 *
 * BUT1 (GPIO 1): Short press → toggle RL1, Hold 10s → factory reset
 * BUT2 (GPIO 3): Short press → toggle RL2
 */

#include "button_handler.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/gpio.h"

static const char *TAG = "BUTTON";

static button_event_cb_t s_callback = NULL;

static void button_monitor_task(void *arg)
{
    /* Configure button GPIOs as input with internal pull-up */
    gpio_config_t btn_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_INPUT,
        .pin_bit_mask = (1ULL << BUT1_GPIO) | (1ULL << BUT2_GPIO),
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
    };
    gpio_config(&btn_conf);
    ESP_LOGI(TAG, "Button monitor started (BUT1=GPIO%d, BUT2=GPIO%d)", BUT1_GPIO, BUT2_GPIO);

    int prev_b1 = 1, prev_b2 = 1;
    int b1_hold_ms = 0;

    while (1) {
        int b1 = gpio_get_level(BUT1_GPIO);
        int b2 = gpio_get_level(BUT2_GPIO);

        /* ── BUT1: supports short press + long hold factory reset ── */
        if (b1 == 0) {
            b1_hold_ms += 50;

            if (b1_hold_ms == 3000 && s_callback) {
                ESP_LOGW(TAG, "⚠️ BUT1 held 3s — continue to 10s for factory reset");
                s_callback(1, BUTTON_EVT_HOLD_3S);
            } else if (b1_hold_ms == 7000 && s_callback) {
                ESP_LOGW(TAG, "⚠️ BUT1 held 7s — releasing in 3s will factory reset!");
                s_callback(1, BUTTON_EVT_HOLD_7S);
            } else if (b1_hold_ms >= 10000 && s_callback) {
                ESP_LOGW(TAG, "⚠️ BUT1 held 10s! Triggering factory reset...");
                s_callback(1, BUTTON_EVT_FACTORY_RESET);
                /* Prevent re-triggering until released */
                while (gpio_get_level(BUT1_GPIO) == 0) {
                    vTaskDelay(pdMS_TO_TICKS(50));
                }
                b1_hold_ms = 0;
            }
        } else {
            /* Button released — check for short press */
            if (prev_b1 == 0 && b1_hold_ms < 3000 && b1_hold_ms > 50) {
                ESP_LOGI(TAG, "🔘 BUT1 short press detected");
                if (s_callback) s_callback(1, BUTTON_EVT_SHORT_PRESS);
            }
            b1_hold_ms = 0;
        }

        /* ── BUT2: short press only ── */
        if (prev_b2 == 1 && b2 == 0) {
            ESP_LOGI(TAG, "🔘 BUT2 pressed");
            if (s_callback) s_callback(2, BUTTON_EVT_SHORT_PRESS);
        }

        prev_b1 = b1;
        prev_b2 = b2;
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

esp_err_t button_handler_init(button_event_cb_t callback)
{
    s_callback = callback;

    BaseType_t ret = xTaskCreate(
        button_monitor_task,
        "btn_monitor",
        3072,
        NULL,
        3,
        NULL
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create button monitor task");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Button handler initialized");
    return ESP_OK;
}
