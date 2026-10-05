/*
 * T2 Zone Controller — Main Entry Point
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * ESP32-S3 N16R8 Zone Controller:
 *   - ESP-NOW Mesh Master (manages T1 Actuator Nodes)
 *   - MAX98357A I2S Speaker / DAC (TTS playback & local audio chimes)
 *   - Wi-Fi Station (connects to Home Network / Gateway)
 *   - MQTT Zone Gateway (subscribes to relay cmds, publishes states)
 *   - WebSocket Audio Proxy (relays T1 PCM to Gateway, plays TTS)
 *   - Zone Manager (maintains node table, heartbeats, online status)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "driver/uart.h"

#include "t2_config.h"
#include "esp_now_protocol.h"
#include "zone_manager.h"
#include "espnow_master.h"
#include "audio_proxy.h"
#include "mqtt_zone.h"
#include "audio_feedback.h"
#include "device_identity.h"
#include "ir_controller.h"

static const char *TAG = "T2_MAIN";

/* ─── State ──────────────────────────────────────────────────────────── */

static i2s_chan_handle_t s_spk_tx_handle = NULL;
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

/* ─── Speaker Enable / Disable (MAX98357A SD Pin) ─────────────────────── */

void speaker_enable(bool enable)
{
    gpio_set_level(SPK_SD_GPIO, enable ? 1 : 0);
    ESP_LOGD(TAG, "Speaker Amp %s (GPIO %d)", enable ? "ENABLED" : "MUTED", SPK_SD_GPIO);
}

/* ─── I2S Speaker Initialization ─────────────────────────────────────── */

static esp_err_t init_i2s_speaker(void)
{
    ESP_LOGI(TAG, "Initializing MAX98357A I2S Speaker DAC (BCLK:%d, WS:%d, DOUT:%d, SD:%d)...",
             SPK_I2S_GPIO_BCLK, SPK_I2S_GPIO_WS, SPK_I2S_GPIO_DOUT, SPK_SD_GPIO);

    /* Configure SD pin (shutdown / mute) */
    gpio_config_t sd_conf = {
        .pin_bit_mask = (1ULL << SPK_SD_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&sd_conf);
    gpio_set_level(SPK_SD_GPIO, 0); /* Start muted to avoid pop/hiss */

    i2s_chan_config_t chan_cfg = {
        .id = SPK_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    esp_err_t ret = i2s_new_channel(&chan_cfg, &s_spk_tx_handle, NULL);
    if (ret != ESP_OK) return ret;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SPK_I2S_GPIO_BCLK,
            .ws   = SPK_I2S_GPIO_WS,
            .dout = SPK_I2S_GPIO_DOUT,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    ret = i2s_channel_init_std_mode(s_spk_tx_handle, &std_cfg);
    if (ret != ESP_OK) return ret;

    return i2s_channel_enable(s_spk_tx_handle);
}

/* ─── Wi-Fi Event Handler ────────────────────────────────────────────── */

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected. Reconnecting in 3s...");
        xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "✅ Wi-Fi Connected! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        gpio_set_level(LED1_GPIO, 1);
    }
}

static esp_err_t init_wifi(void)
{
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = "XIAOMI",
            .password = "1234567890",
            .scan_method = WIFI_ALL_CHANNEL_SCAN,
            .sort_method = WIFI_CONNECT_AP_BY_SIGNAL,
            .threshold.authmode = WIFI_AUTH_WPA_WPA2_PSK,
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Lock channel for ESP-NOW compatibility */
    esp_wifi_set_channel(ESPNOW_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

    return ESP_OK;
}

/* ─── Interactive Serial CLI Task ────────────────────────────────────── */

static void t2_cli_task(void *arg)
{
    char line[128];
    int idx = 0;

    ESP_LOGI(TAG, "💻 Interactive Serial CLI active! Type 'help' for commands.");

    while (1) {
        int c = fgetc(stdin);
        if (c == EOF || c < 0) {
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        char ch = (char)c;
        if (ch == '\r' || ch == '\n') {
            if (idx > 0) {
                line[idx] = '\0';
                char *cmd = line;

                if (strcmp(cmd, "nodes") == 0) {
                    int count = 0;
                    zone_node_entry_t *nodes = zone_manager_get_all(&count);
                    ESP_LOGI(TAG, "--- Zone Nodes (%d registered) ---", count);
                    for (int i = 0; i < count; i++) {
                        ESP_LOGI(TAG, " [%d] ID=%s MAC=%02X:%02X:%02X:%02X:%02X:%02X RL1=%d RL2=%d Online=%d",
                                 i, nodes[i].device_id,
                                 nodes[i].mac[0], nodes[i].mac[1], nodes[i].mac[2],
                                 nodes[i].mac[3], nodes[i].mac[4], nodes[i].mac[5],
                                 nodes[i].rl1_state, nodes[i].rl2_state, nodes[i].is_online);
                    }
                } else if (strncmp(cmd, "r1 ", 3) == 0 || strncmp(cmd, "r2 ", 3) == 0) {
                    int ch_num = (cmd[1] == '1') ? 1 : 2;
                    uint8_t state = (strstr(cmd, "on") != NULL) ? 1 : 0;
                    int count = 0;
                    zone_node_entry_t *nodes = zone_manager_get_all(&count);
                    if (count > 0) {
                        ESP_LOGI(TAG, "⚡ Sending Relay CH%d=%d to node %s...", ch_num, state, nodes[0].device_id);
                        espnow_master_send_relay_cmd(nodes[0].mac, ch_num, state);
                    } else {
                        uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
                        ESP_LOGW(TAG, "No node registered, sending broadcast Relay CH%d=%d...", ch_num, state);
                        espnow_master_send_relay_cmd(bcast, ch_num, state);
                    }
                } else if (strncmp(cmd, "ir daikin", 9) == 0) {
                    ir_ac_cmd_t ac = {.brand = "daikin", .power = true, .temp_c = 24, .mode = 1, .fan = 0};
                    ir_send_ac(&ac);
                } else if (strncmp(cmd, "ir nec", 6) == 0) {
                    ir_send_nec(0x1234, 0x01);
                } else if (strcmp(cmd, "chime") == 0) {
                    audio_feedback_play(AUDIO_FB_SUCCESS);
                } else if (strcmp(cmd, "help") == 0) {
                    ESP_LOGI(TAG, "Available commands: 'nodes', 'r1 on', 'r1 off', 'r2 on', 'r2 off', 'ir daikin', 'ir nec', 'chime'");
                }
                idx = 0;
            }
        } else if (idx < (int)sizeof(line) - 1) {
            line[idx++] = ch;
        }
    }
}


/* ─── Main Application ───────────────────────────────────────────────── */

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(500));

    ESP_LOGI(TAG, "==========================================================");
    ESP_LOGI(TAG, "  DTV SMART HOME — T2 ZONE CONTROLLER (ESP32-S3 N16R8)   ");
    ESP_LOGI(TAG, "  Version: %d.%d.%d | Zone: %s                          ",
             FW_VERSION_MAJOR, FW_VERSION_MINOR, FW_VERSION_PATCH, DEFAULT_ZONE_NAME);
    ESP_LOGI(TAG, "==========================================================");

    /* 0. Status LEDs */
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

    /* 1. NVS Flash */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS flash...");
        nvs_flash_erase();
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS Flash Init failed: %s", esp_err_to_name(ret));
    }

    /* 2. Commercial Device Identity */
    device_identity_init();

    /* 3. Speaker I2S & Audio Feedback */
    esp_err_t spk_err = init_i2s_speaker();
    if (spk_err == ESP_OK) {
        ESP_LOGI(TAG, "Speaker ready. Playing bootup sound...");
        audio_feedback_init(s_spk_tx_handle);
        audio_feedback_play(AUDIO_FB_BOOTUP);
    } else {
        ESP_LOGW(TAG, "Speaker init failed: %s", esp_err_to_name(spk_err));
    }

    /* 4. Zone Manager */
    zone_manager_init(DEFAULT_ZONE_NAME);

    /* 5. Wi-Fi STA */
    init_wifi();

    /* 6. ESP-NOW Master Protocol */
    espnow_master_init();

    /* 7. Audio Proxy (WebSocket stream to Gateway + TTS playback) */
    char ws_uri[64];
    snprintf(ws_uri, sizeof(ws_uri), "ws://%s:%d", DEFAULT_GATEWAY_IP, DEFAULT_WS_PORT);
    audio_proxy_init(ws_uri, s_spk_tx_handle);

    /* 8. MQTT Zone Gateway (Subscribes to relay cmds, publishes states) */
    char mqtt_uri[64];
    snprintf(mqtt_uri, sizeof(mqtt_uri), "mqtt://%s:%d", DEFAULT_GATEWAY_IP, DEFAULT_MQTT_PORT);
    mqtt_zone_init(mqtt_uri, DEFAULT_MQTT_USER, DEFAULT_MQTT_PASS);

#if HAS_IR
    /* 9. Infrared Blaster & Receiver */
    ir_controller_init(IR_TX_GPIO, IR_RX_GPIO);
#endif

    /* 10. Memory Diagnostic */
    size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    size_t psram_free    = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "Free Internal RAM : %u KB", (unsigned)(internal_free / 1024));
    ESP_LOGI(TAG, "Free Octal PSRAM  : %u KB (%u MB)",
             (unsigned)(psram_free / 1024), (unsigned)(psram_free / (1024 * 1024)));

    /* 11. Interactive Serial CLI */
    xTaskCreate(t2_cli_task, "t2_cli", 3584, NULL, 3, NULL);

    ESP_LOGI(TAG, "🚀 T2 Zone Controller running! Listening for T1 mesh nodes and Gateway commands.");
}
