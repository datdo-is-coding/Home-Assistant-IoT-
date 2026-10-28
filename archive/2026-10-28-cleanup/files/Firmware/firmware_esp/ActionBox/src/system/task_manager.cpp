#include "task_manager.h"
#include "app_config.h"
#include "board_pins.h"
#include "relay_driver.h"
#include "bl0942.h"
#include "button_driver.h"
#include "led_driver.h"
#include "safety_supervisor.h"
#include "device_manager.h"
#include "espnow_transport.h"
#include "nvs_storage.h"

#include <string.h>
#include <atomic>
#include "cJSON.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "TASK_MGR";
static std::atomic<int> s_upstream_error(3);

typedef struct {
    uint8_t            channel;
    CurrentMeasurement measurement;
} SensorQueueItem;

static QueueHandle_t s_cmd_queue = NULL;
static QueueHandle_t s_network_rx_queue = NULL;
static QueueHandle_t s_network_tx_queue = NULL;
static QueueHandle_t s_sensor_queue = NULL;

static TaskHandle_t s_relay_task_handle = NULL;
static TaskHandle_t s_sensor_task_handle = NULL;
static TaskHandle_t s_button_task_handle = NULL;
static TaskHandle_t s_network_task_handle = NULL;
static TaskHandle_t s_safety_task_handle = NULL;
static TaskHandle_t s_telemetry_task_handle = NULL;

static void button_task(void *pvParameters) {
    ESP_LOGI(TAG, "button_task started.");
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(10);

    while (1) {
        button_driver_tick();
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

static void sensor_task(void *pvParameters) {
    ESP_LOGI(TAG, "sensor_task started.");
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(SENSOR_SAMPLE_INTERVAL_MS);

    while (1) {
        for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ch++) {
            SensorQueueItem item;
            item.channel = ch;

            esp_err_t err = bl0942_read_channel(ch, &item.measurement);
            if (err == ESP_OK) {
                if (s_sensor_queue) {
                    xQueueSend(s_sensor_queue, &item, 0);
                }
            }
        }
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

static void safety_task(void *pvParameters) {
    ESP_LOGI(TAG, "safety_task started.");
    safety_register_calling_task_wdt();
    SensorQueueItem item;

    while (1) {
        if (xQueueReceive(s_sensor_queue, &item, pdMS_TO_TICKS(100)) == pdTRUE) {
            safety_process_measurement(item.channel, &item.measurement);
        }
        safety_check_sensor_timeouts();
        safety_feed_task_watchdog();
    }
}

static void relay_task(void *pvParameters) {
    ESP_LOGI(TAG, "relay_task started.");
    ActionBoxCommand cmd;

    while (1) {
        if (xQueueReceive(s_cmd_queue, &cmd, portMAX_DELAY) == pdTRUE) {
            ActionBoxResponse resp;
            device_manager_execute_command(&cmd, &resp);

            char resp_json[512];
            if (protocol_serialize_response(&resp, resp_json, sizeof(resp_json)) == ESP_OK) {
                task_manager_post_network_tx(NULL, (const uint8_t*)resp_json, strlen(resp_json));
            }
        }
    }
}

static void network_task(void *pvParameters) {
    ESP_LOGI(TAG, "network_task started.");
    NetworkPacket rx_pkt;
    NetworkPacket tx_pkt;

    while (1) {

        if (xQueueReceive(s_network_rx_queue, &rx_pkt, pdMS_TO_TICKS(50)) == pdTRUE) {
            static const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            if (memcmp(rx_pkt.mac, bcast, 6) == 0) {
                ESP_LOGW(TAG, "Dropped packet from broadcast MAC");
                continue;
            }

            char json_buf[512];
            size_t copy_len = (rx_pkt.len < sizeof(json_buf) - 1) ? rx_pkt.len : (sizeof(json_buf) - 1);
            memcpy(json_buf, rx_pkt.payload, copy_len);
            json_buf[copy_len] = '\0';

            if (strstr(json_buf, "\"heartbeat\"") != NULL || strstr(json_buf, "\"subbox_id\"") != NULL) {
                if (espnow_transport_is_paired()) {
                    uint8_t paired_mac[6] = {0};
                    if (espnow_transport_get_subbox_mac(paired_mac) && memcmp(rx_pkt.mac, paired_mac, 6) != 0) {
                        ESP_LOGW(TAG, "Heartbeat dropped from non-paired MAC %02X:%02X:%02X:%02X:%02X:%02X",
                                 rx_pkt.mac[0], rx_pkt.mac[1], rx_pkt.mac[2], rx_pkt.mac[3], rx_pkt.mac[4], rx_pkt.mac[5]);
                        continue;
                    }
                } else if (espnow_transport_is_pairing_mode()) {
                    ESP_LOGI(TAG, "Pairing mode active: pairing with SubBox MAC %02X:%02X:%02X:%02X:%02X:%02X",
                             rx_pkt.mac[0], rx_pkt.mac[1], rx_pkt.mac[2], rx_pkt.mac[3], rx_pkt.mac[4], rx_pkt.mac[5]);
                    espnow_transport_pair_subbox(rx_pkt.mac);
                    espnow_transport_set_pairing_mode(false);
                } else {
                    ESP_LOGD(TAG, "Heartbeat ignored: ActionBox not paired and pairing mode inactive");
                    continue;
                }
                safety_feed_network_watchdog();
                cJSON *hb_root = cJSON_Parse(json_buf);
                if (hb_root) {
                    const auto* wifi = cJSON_GetObjectItemCaseSensitive(hb_root, "wifi");
                    const auto* mqtt = cJSON_GetObjectItemCaseSensitive(hb_root, "mqtt");
                    s_upstream_error.store(!cJSON_IsTrue(wifi) ? 2 : (!cJSON_IsTrue(mqtt) ? 3 : 0));
                    cJSON *ch_item = cJSON_GetObjectItem(hb_root, "channel");
                    if (cJSON_IsNumber(ch_item) && ch_item->valueint >= 1 && ch_item->valueint <= 13) {
                        uint8_t cur_ch = 0;
                        wifi_second_chan_t sec;
                        esp_wifi_get_channel(&cur_ch, &sec);
                        if (cur_ch != (uint8_t)ch_item->valueint) {
                            ESP_LOGI(TAG, "Syncing Wi-Fi channel with SubBox: Ch%d -> Ch%d", cur_ch, ch_item->valueint);
                            esp_wifi_set_channel((uint8_t)ch_item->valueint, WIFI_SECOND_CHAN_NONE);
                        }
                    }
                    cJSON_Delete(hb_root);
                }
                continue;
            }

            ActionBoxCommand cmd;
            esp_err_t err = protocol_parse_command(json_buf, &cmd);
            if (err == ESP_OK) {
                bool requires_paired_subbox = (cmd.cmd == CMD_TYPE_TURN_ON || cmd.cmd == CMD_TYPE_TURN_OFF ||
                                              cmd.cmd == CMD_TYPE_TOGGLE || cmd.cmd == CMD_TYPE_SET_CONFIG ||
                                              cmd.cmd == CMD_TYPE_CLEAR_FAULT);
                if (requires_paired_subbox) {
                    uint8_t paired_mac[6] = {0};
                    if (!espnow_transport_is_paired() || !espnow_transport_get_subbox_mac(paired_mac)) {
                        ESP_LOGW(TAG, "Rejected control/config command: ActionBox is not paired with a trusted SubBox!");
                        continue;
                    }
                    if (memcmp(rx_pkt.mac, paired_mac, 6) != 0) {
                        ESP_LOGW(TAG, "Rejected control/config command from untrusted MAC %02X:%02X:%02X:%02X:%02X:%02X (expected %02X:%02X:%02X:%02X:%02X:%02X)!",
                                 rx_pkt.mac[0], rx_pkt.mac[1], rx_pkt.mac[2], rx_pkt.mac[3], rx_pkt.mac[4], rx_pkt.mac[5],
                                 paired_mac[0], paired_mac[1], paired_mac[2], paired_mac[3], paired_mac[4], paired_mac[5]);
                        continue;
                    }
                }
                safety_feed_network_watchdog();

                char cached_resp[512] = {0};
                if (protocol_is_duplicate_request(cmd.request_id, cmd.session_id, cached_resp, sizeof(cached_resp))) {
                    ESP_LOGD(TAG, "Duplicate request %lu detected. Returning cached response.", cmd.request_id);
                    espnow_transport_send_to(rx_pkt.mac, (const uint8_t*)cached_resp, strlen(cached_resp));
                } else {

                    ActionBoxResponse resp;
                    uint32_t cmd_time = (uint32_t)(esp_timer_get_time() / 1000);
                    device_manager_execute_command(&cmd, &resp);

                    char resp_json[512];
                    if (protocol_serialize_response(&resp, resp_json, sizeof(resp_json)) == ESP_OK) {
                        espnow_transport_send_to(rx_pkt.mac, (const uint8_t*)resp_json, strlen(resp_json));
                    }

                    if (resp.success && (cmd.cmd == CMD_TYPE_TURN_ON || cmd.cmd == CMD_TYPE_TURN_OFF)) {
                        uint32_t settle = (cmd.settle_ms >= 100 && cmd.settle_ms <= 2000) ? cmd.settle_ms : 500;
                        vTaskDelay(pdMS_TO_TICKS(settle));
                        CurrentMeasurement meas{};
                        bl0942_read_channel(cmd.channel, &meas);
                        char load_json[512];
                        if (protocol_serialize_load_report(&resp, cmd_time, &meas, load_json, sizeof(load_json)) == ESP_OK) {
                            espnow_transport_send_to(rx_pkt.mac, (const uint8_t*)load_json, strlen(load_json));
                        }
                    }
                }
            }
        }

        if (xQueueReceive(s_network_tx_queue, &tx_pkt, 0) == pdTRUE) {
            espnow_transport_send_to(tx_pkt.mac, tx_pkt.payload, tx_pkt.len);
        }
    }
}

static void telemetry_task(void *pvParameters) {
    ESP_LOGI(TAG, "telemetry_task started.");
    TickType_t xLastTelemetryTime = xTaskGetTickCount();
    const TickType_t xTelemetryPeriod = pdMS_TO_TICKS(TELEMETRY_REPORT_INTERVAL_MS);

    while (1) {

        bool fault = false;
        for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ch++) {
            if (relay_get_fault(ch) != RELAY_FAULT_NONE) {
                fault = true;
                break;
            }
        }

        ArmedKind armed = device_manager_get_armed_kind();
        bool is_claimed = device_manager_is_claimed();

        ::LedPattern p1;
        if (fault) {
            p1 = ::LedPattern::FAULT;
        } else if (armed == ArmedKind::FACTORY_RESET) {
            p1 = ::LedPattern::AWAITING_FACTORY_RESET;
        } else if (armed == ArmedKind::NETWORK_RESET) {
            p1 = ::LedPattern::AWAITING_NETWORK_RESET;
        } else if (!is_claimed) {
            p1 = ::LedPattern::UNCLAIMED;
        } else {
            const int code = (safety_is_network_timed_out() ? 1 : s_upstream_error.load());
            if (code == 0) {
                p1 = ::LedPattern::READY;
            } else {
                p1 = ::LedPattern::OFFLINE;
            }
        }

        led_set_pattern(1, p1);
        led_driver_tick();

        TickType_t now = xTaskGetTickCount();
        if ((now - xLastTelemetryTime) >= xTelemetryPeriod) {
            xLastTelemetryTime = now;

            if (safety_is_network_timed_out()) {
                espnow_transport_hop_channel();
            }

            char telem_json[768];
            if (protocol_serialize_telemetry(telem_json, sizeof(telem_json)) == ESP_OK) {
                espnow_transport_send((const uint8_t*)telem_json, strlen(telem_json));
                ESP_LOGD(TAG, "Telemetry: %s", telem_json);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

static void on_espnow_packet_received(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (!mac_addr || !data || len <= 0 || len > 250) return;
    static const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    if (memcmp(mac_addr, bcast, 6) == 0) return;
    task_manager_post_network_rx(mac_addr, data, (size_t)len);
}

esp_err_t task_manager_init(void) {
    ESP_LOGI(TAG, "Creating FreeRTOS inter-task communication queues...");

    s_cmd_queue        = xQueueCreate(QUEUE_CAPACITY_RELAY_CMD, sizeof(ActionBoxCommand));
    s_network_rx_queue = xQueueCreate(QUEUE_CAPACITY_NETWORK_RX, sizeof(NetworkPacket));
    s_network_tx_queue = xQueueCreate(QUEUE_CAPACITY_NETWORK_TX, sizeof(NetworkPacket));
    s_sensor_queue     = xQueueCreate(QUEUE_CAPACITY_SENSOR_DATA, sizeof(SensorQueueItem));

    if (!s_cmd_queue || !s_network_rx_queue || !s_network_tx_queue || !s_sensor_queue) {
        ESP_LOGE(TAG, "Failed to allocate FreeRTOS queues!");
        return ESP_ERR_NO_MEM;
    }

    espnow_transport_register_rx_callback(on_espnow_packet_received);

    const ActionBoxPersistentConfig *stored_cfg = nvs_storage_get_cached_config();
    if (!stored_cfg || !stored_cfg->has_assigned_subbox) {
        ESP_LOGI(TAG, "No assigned SubBox configured, enabling ESP-NOW pairing mode on boot.");
        espnow_transport_set_pairing_mode(true);
    }

    ESP_LOGI(TAG, "Spawning ActionBox FreeRTOS tasks...");

    xTaskCreate(safety_task,    "safety_task",    TASK_STACK_SIZE_SAFETY,    NULL, TASK_PRIORITY_SAFETY,    &s_safety_task_handle);
    xTaskCreate(relay_task,     "relay_task",     TASK_STACK_SIZE_RELAY,     NULL, TASK_PRIORITY_RELAY,     &s_relay_task_handle);
    xTaskCreate(button_task,    "button_task",    TASK_STACK_SIZE_BUTTON,    NULL, TASK_PRIORITY_BUTTON,    &s_button_task_handle);
    xTaskCreate(sensor_task,    "sensor_task",    TASK_STACK_SIZE_SENSOR,    NULL, TASK_PRIORITY_SENSOR,    &s_sensor_task_handle);
    xTaskCreate(network_task,   "network_task",   TASK_STACK_SIZE_NETWORK,   NULL, TASK_PRIORITY_NETWORK,   &s_network_task_handle);
    xTaskCreate(telemetry_task, "telemetry_task", TASK_STACK_SIZE_TELEMETRY, NULL, TASK_PRIORITY_TELEMETRY, &s_telemetry_task_handle);

    ESP_LOGI(TAG, "All FreeRTOS tasks successfully spawned.");
    return ESP_OK;
}

esp_err_t task_manager_post_command(const ActionBoxCommand *cmd) {
    if (!cmd || !s_cmd_queue) return ESP_ERR_INVALID_ARG;
    if (xQueueSend(s_cmd_queue, cmd, pdMS_TO_TICKS(50)) != pdTRUE) {
        ESP_LOGW(TAG, "Command queue full!");
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

esp_err_t task_manager_post_network_rx(const uint8_t *src_mac, const uint8_t *data, size_t len) {
    if (!src_mac || !data || len == 0 || !s_network_rx_queue) return ESP_ERR_INVALID_ARG;

    NetworkPacket pkt;
    memcpy(pkt.mac, src_mac, 6);
    if (len > sizeof(pkt.payload)) return ESP_ERR_INVALID_SIZE;
    pkt.len = len;
    memcpy(pkt.payload, data, pkt.len);

    if (xQueueSend(s_network_rx_queue, &pkt, 0) != pdTRUE) {
        ESP_LOGD(TAG, "Network RX queue full, dropped packet.");
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

esp_err_t task_manager_post_network_tx(const uint8_t *dest_mac, const uint8_t *data, size_t len) {
    if (!data || len == 0 || !s_network_tx_queue) return ESP_ERR_INVALID_ARG;

    NetworkPacket pkt;
    if (dest_mac) {
        memcpy(pkt.mac, dest_mac, 6);
    } else {
        memset(pkt.mac, 0xFF, 6);
    }
    if (len > sizeof(pkt.payload)) return ESP_ERR_INVALID_SIZE;
    pkt.len = len;
    memcpy(pkt.payload, data, pkt.len);

    if (xQueueSend(s_network_tx_queue, &pkt, pdMS_TO_TICKS(50)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}
