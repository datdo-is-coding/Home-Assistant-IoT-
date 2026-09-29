/**
 * @file main.cpp
 * @brief Production Entry Point for ESP32-S3 ActionBox Smart-Home Actuator Node
 * 
 * Hardware Role:
 * - Low-level actuator node (Relay control, Current sensing, Local buttons, Safety supervisor)
 * - FreeRTOS task model, ESP-NOW communication with SubBox, NVS storage
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"

#include "app_config.h"
#include "board_pins.h"
#include "nvs_storage.h"
#include "relay_driver.h"
#include "bl0942.h"
#include "button_driver.h"
#include "led_driver.h"
#include "actionbox_protocol.h"
#include "safety_supervisor.h"
#include "espnow_transport.h"
#include "device_manager.h"
#include "task_manager.h"
#include "voice_capture.h"

static const char *TAG = "ACTIONBOX_MAIN";

static void print_banner(void) {
    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);

    uint32_t flash_size = 0;
    esp_flash_get_size(NULL, &flash_size);

    uint8_t mac[6];
    espnow_transport_get_local_mac(mac);

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "  AETHERIA OS — ACTIONBOX ACTUATOR NODE (ESP32-S3)");
    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "  Firmware Name    : %s", APP_FW_NAME);
    ESP_LOGI(TAG, "  Firmware Version : %s", APP_FW_VERSION_STR);
    ESP_LOGI(TAG, "  Silicon Model    : ESP32-S3 (Rev %d, %d Cores)", chip_info.revision, chip_info.cores);
    ESP_LOGI(TAG, "  Flash Size       : %lu MB", (unsigned long)(flash_size / (1024 * 1024)));
    ESP_LOGI(TAG, "  Wi-Fi MAC        : %02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    ESP_LOGI(TAG, "  Relay Channels   : %d (RL1: IO%d, RL2: IO%d)",
             BOARD_RELAY_CHANNEL_COUNT, BOARD_PIN_RELAY_CH1, BOARD_PIN_RELAY_CH2);
    ESP_LOGI(TAG, "  Buttons          : BUT1: IO%d, BUT2: IO%d",
             BOARD_PIN_BUTTON_CH1, BOARD_PIN_BUTTON_CH2);
    ESP_LOGI(TAG, "  Current Sensor   : Dual BL0942 (TX: IO%d, RX1: IO%d, RX2: IO%d)",
             BOARD_PIN_BL0942_TX, BOARD_PIN_BL0942_RX_CH1, BOARD_PIN_BL0942_RX_CH2);
    ESP_LOGI(TAG, "  Microphone       : INMP441 (BCLK: IO%d, WS: IO%d, DIN: IO%d, VAD: Active)",
             BOARD_PIN_MIC_BCLK, BOARD_PIN_MIC_WS, BOARD_PIN_MIC_DIN);
    ESP_LOGI(TAG, "  Voice LED        : LED2 (IO%d) — Active on Voice Listening/Streaming",
             BOARD_PIN_LED_VOICE);
    ESP_LOGI(TAG, "  Speaker          : DISABLED (Hardware Shutdown on IO%d)", BOARD_PIN_SPEAKER_SD);
    ESP_LOGI(TAG, "===============================================================");
}

static void hardware_disable_speaker(void) {
    ESP_LOGI(TAG, "Speaker disabled by policy: Forcing MAX98357 amplifier into hardware shutdown (SP_SD: IO%d -> LOW)",
             BOARD_PIN_SPEAKER_SD);

    /* 1. Drive SP_SD (GPIO 2) LOW to force MAX98357 amplifier into shutdown */
    gpio_config_t sd_conf = {};
    sd_conf.mode = GPIO_MODE_OUTPUT;
    sd_conf.pin_bit_mask = (1ULL << BOARD_PIN_SPEAKER_SD);
    sd_conf.pull_down_en = GPIO_PULLDOWN_ENABLE;
    sd_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_config(&sd_conf);
    gpio_set_level(BOARD_PIN_SPEAKER_SD, 0);

    /* 2. Configure I2S audio lines (IO17, IO18, IO21) as floating/pull-down inputs so they consume 0 power */
    uint64_t i2s_mask = (1ULL << BOARD_PIN_SPEAKER_BCLK) |
                        (1ULL << BOARD_PIN_SPEAKER_LRC) |
                        (1ULL << BOARD_PIN_SPEAKER_DOUT);
    gpio_config_t i2s_conf = {};
    i2s_conf.mode = GPIO_MODE_INPUT;
    i2s_conf.pin_bit_mask = i2s_mask;
    i2s_conf.pull_down_en = GPIO_PULLDOWN_ENABLE;
    i2s_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_config(&i2s_conf);
}

extern "C" void app_main(void) {
    /* 0. Enforce hardware shutdown on speaker amplifier */
    hardware_disable_speaker();

    /* 1. Initialize Persistent Storage (NVS) */
    ESP_ERROR_CHECK(nvs_storage_init());

    /* 2. Initialize Protocol Layer & Idempotency Cache */
    protocol_init();

    /* 3. Initialize Hardware Drivers */
    ESP_ERROR_CHECK(relay_driver_init());
    ESP_ERROR_CHECK(bl0942_driver_init());
    ESP_ERROR_CHECK(button_driver_init());
    ESP_ERROR_CHECK(led_driver_init());

    /* 4. Initialize Local Safety Supervisor (Configures TWDT) */
    ESP_ERROR_CHECK(safety_supervisor_init());

    /* 5. Apply Startup Relay States (Restores last state or safe OFF from NVS) */
    safety_apply_startup_state();

    /* 6. Initialize Wi-Fi & ESP-NOW Network Transport */
    ESP_ERROR_CHECK(espnow_transport_init());

    /* 6.1 Initialize Voice Capture & VAD Subsystem (INMP441 I2S + 1.5s Silence VAD) */
    ESP_ERROR_CHECK(voice_capture_init());

    /* 7. Display System Banner */
    print_banner();

    /* 8. Initialize Device Manager Coordinator */
    ESP_ERROR_CHECK(device_manager_init());

    /* 9. Initialize FreeRTOS Task Architecture & Queues */
    ESP_ERROR_CHECK(task_manager_init());

    ESP_LOGI(TAG, "ActionBox system is fully operational. Awaiting commands / local button presses.");

    /* Main task can yield or sleep; background tasks handle all operational logic */
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        ESP_LOGD(TAG, "System heartbeat [Heap free: %lu bytes, Min: %lu bytes]",
                 (unsigned long)esp_get_free_heap_size(),
                 (unsigned long)esp_get_minimum_free_heap_size());
    }
}
