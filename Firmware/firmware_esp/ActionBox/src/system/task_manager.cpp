/**
 * @file task_manager.cpp
 * @brief Production FreeRTOS Task Architecture Implementation
 */

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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "TASK_MGR";

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

/* ========================================================================= */
/*                              TASK IMPLEMENTATIONS                         */
/* ========================================================================= */

/**
 * @brief Task: button_task (Scans buttons non-blocking every 10ms)
 */
static void button_task(void *pvParameters) {
    ESP_LOGI(TAG, "button_task started.");
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(10);

    while (1) {
        button_driver_tick();
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
    }
}

/**
 * @brief Task: sensor_task (Continuously polls BL0942 UART every 100ms)
 */
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

/**
 * @brief Task: safety_task (Highest priority: Evaluates measurements & limits)
 */
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

/**
 * @brief Task: relay_task (Processes actuation commands from queue)
 */
static void relay_task(void *pvParameters) {
    ESP_LOGI(TAG, "relay_task started.");
    ActionBoxCommand cmd;

    while (1) {
        if (xQueueReceive(s_cmd_queue, &cmd, portMAX_DELAY) == pdTRUE) {
            ActionBoxResponse resp;
            device_manager_execute_command(&cmd, &resp);

            /* If command was initiated over network, serialize response and transmit */
            char resp_json[512];
            if (protocol_serialize_response(&resp, resp_json, sizeof(resp_json)) == ESP_OK) {
                task_manager_post_network_tx(NULL, (const uint8_t*)resp_json, strlen(resp_json));
            }
        }
    }
}

/**
 * @brief Task: network_task (Handles inbound & outbound ESP-NOW packets)
 */
static void network_task(void *pvParameters) {
    ESP_LOGI(TAG, "network_task started.");
    NetworkPacket rx_pkt;
    NetworkPacket tx_pkt;

    while (1) {
        /* Check for inbound packet from SubBox */
        if (xQueueReceive(s_network_rx_queue, &rx_pkt, pdMS_TO_TICKS(50)) == pdTRUE) {

            /* Null-terminate payload for JSON parsing */
            char json_buf[512];
            size_t copy_len = (rx_pkt.len < sizeof(json_buf) - 1) ? rx_pkt.len : (sizeof(json_buf) - 1);
            memcpy(json_buf, rx_pkt.payload, copy_len);
            json_buf[copy_len] = '\0';

            ActionBoxCommand cmd;
            esp_err_t err = protocol_parse_command(json_buf, &cmd);
            if (err == ESP_OK) {
                safety_feed_network_watchdog();
                /* 1. Idempotency check: duplicate packet retransmission detection */
                char cached_resp[512] = {0};
                if (protocol_is_duplicate_request(cmd.request_id, cmd.session_id, cached_resp, sizeof(cached_resp))) {
                    ESP_LOGD(TAG, "Duplicate request %lu detected. Returning cached response.", cmd.request_id);
                    espnow_transport_send_to(rx_pkt.mac, (const uint8_t*)cached_resp, strlen(cached_resp));
                } else {
                    /* Fresh request: execute directly and report ACK */
                    ActionBoxResponse resp;
                    uint32_t cmd_time = (uint32_t)(esp_timer_get_time() / 1000);
                    device_manager_execute_command(&cmd, &resp);

                    char resp_json[512];
                    if (protocol_serialize_response(&resp, resp_json, sizeof(resp_json)) == ESP_OK) {
                        espnow_transport_send_to(rx_pkt.mac, (const uint8_t*)resp_json, strlen(resp_json));
                    }

                    /* After GPIO ACK, wait settle_ms, read BL0942 power and transmit LOAD_REPORT */
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

                /* If SubBox was unpaired, pair with this sender */
                if (!espnow_transport_is_paired()) {
                    espnow_transport_pair_subbox(rx_pkt.mac);
                }
            }
        }

        /* Check for outbound packets waiting to be sent */
        if (xQueueReceive(s_network_tx_queue, &tx_pkt, 0) == pdTRUE) {
            espnow_transport_send_to(tx_pkt.mac, tx_pkt.payload, tx_pkt.len);
        }
    }
}

/**
 * @brief Task: telemetry_task (Periodic heartbeat reporting and LED animation)
 */
static void telemetry_task(void *pvParameters) {
    ESP_LOGI(TAG, "telemetry_task started.");
    TickType_t xLastTelemetryTime = xTaskGetTickCount();
    const TickType_t xTelemetryPeriod = pdMS_TO_TICKS(TELEMETRY_REPORT_INTERVAL_MS);

    while (1) {
        /* Run LED animation tick non-blocking */
        led_driver_tick();

        TickType_t now = xTaskGetTickCount();
        if ((now - xLastTelemetryTime) >= xTelemetryPeriod) {
            xLastTelemetryTime = now;

            /* Check if network is disconnected / timed out (>10s): scan channels 1-13 */
            if (safety_is_network_timed_out() && espnow_transport_is_paired()) {
                ESP_LOGW(TAG, "SubBox communication heartbeat timeout (>10s). Scanning Wi-Fi channels 1-13...");
                espnow_transport_scan_channels();
            }

            /* Serialize and send periodic telemetry */
            char telem_json[768];
            if (protocol_serialize_telemetry(telem_json, sizeof(telem_json)) == ESP_OK) {
                espnow_transport_send((const uint8_t*)telem_json, strlen(telem_json));
                ESP_LOGI(TAG, "Telemetry: %s", telem_json);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

/* Callback from ESP-NOW driver when packet arrives */
static void on_espnow_packet_received(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (!data || len <= 0 || len > 250) return;
    task_manager_post_network_rx(mac_addr, data, (size_t)len);
}

/* ========================================================================= */
/*                         PUBLIC INITIALIZATION API                         */
/* ========================================================================= */

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

    /* Hook ESP-NOW receive callback to task_manager queue */
    espnow_transport_register_rx_callback(on_espnow_packet_received);

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
