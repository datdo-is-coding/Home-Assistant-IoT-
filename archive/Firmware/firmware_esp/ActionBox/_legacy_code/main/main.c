#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "driver/gpio.h"

#include "t1_config.h"
#include "esp_now_protocol.h"
#include "espnow_slave.h"
#include "voice_capture.h"
#include "telemetry.h"
#include "relay_driver.h"
#include "button_handler.h"
#include "device_identity.h"

static const char *TAG = "T1_MAIN";

static void init_leds(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << LED1_GPIO) | (1ULL << LED2_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);
    gpio_set_level(LED1_GPIO, 0);
    gpio_set_level(LED2_GPIO, 0);
}

static void on_button_event(int channel, button_event_t event)
{
    switch (event) {
    case BUTTON_EVT_SHORT_PRESS: {
#if HAS_RELAY
        bool new_state = relay_driver_toggle(channel);
        ESP_LOGI(TAG, "🔘 Button %d pressed -> Relay CH%d toggled to %s",
                 channel, channel, new_state ? "ON" : "OFF");

        gpio_set_level(LED2_GPIO, 1);
        vTaskDelay(pdMS_TO_TICKS(100));
        gpio_set_level(LED2_GPIO, 0);

        telemetry_send_now();
#endif
        break;
    }

    case BUTTON_EVT_HOLD_3S:
        ESP_LOGW(TAG, "⚠️ Button %d held 3s... Continue holding to 10s for Factory Reset", channel);
        gpio_set_level(LED2_GPIO, 1);
        break;

    case BUTTON_EVT_HOLD_7S:
        ESP_LOGW(TAG, "⚠️ Button %d held 7s... Release in 3s will execute Factory Reset!", channel);
        gpio_set_level(LED1_GPIO, 1);
        gpio_set_level(LED2_GPIO, 1);
        break;

    case BUTTON_EVT_FACTORY_RESET:
        ESP_LOGW(TAG, "⚠️ Button %d held 10s! Executing Commercial Factory Reset...", channel);
        gpio_set_level(LED1_GPIO, 0);
        gpio_set_level(LED2_GPIO, 0);
        device_identity_factory_reset();
        break;
    }
}

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(500));

    ESP_LOGI(TAG, "==========================================================");
    ESP_LOGI(TAG, "  DTV SMART HOME — T1 ACTUATOR NODE (ESP32-S3)           ");
    ESP_LOGI(TAG, "  Version: %d.%d.%d | Capabilities: 0x%02X              ",
             FW_VERSION_MAJOR, FW_VERSION_MINOR, FW_VERSION_PATCH, T1_CAPABILITIES);
    ESP_LOGI(TAG, "==========================================================");

    init_leds();
    gpio_set_level(LED1_GPIO, 1);

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS flash due to version mismatch...");
        nvs_flash_erase();
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS Flash Init failed: %s", esp_err_to_name(ret));
    }

    device_identity_init();

#if HAS_RELAY
    relay_driver_init();
    ESP_LOGI(TAG, "Relay Driver initialized (CH1=GPIO%d, CH2=GPIO%d, Active-LOW)",
             RELAY_CH1_GPIO, RELAY_CH2_GPIO);
#endif

    button_handler_init(on_button_event);

    espnow_slave_init();

#if HAS_MIC
    voice_capture_init();
#endif

    telemetry_init();

    size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    size_t psram_free    = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "Free Internal RAM : %u KB", (unsigned)(internal_free / 1024));
    ESP_LOGI(TAG, "Free PSRAM        : %u KB (%u MB)",
             (unsigned)(psram_free / 1024), (unsigned)(psram_free / (1024 * 1024)));

    ESP_LOGI(TAG, "🚀 T1 Actuator Node ready. Waiting for T2 Zone Controller or Wake Word...");
}
