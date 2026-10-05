/*
 * Telemetry Module — Implementation
 * DTV Smart Home — T1 Actuator Node
 */

#include "telemetry.h"
#include "t1_config.h"
#include "espnow_slave.h"
#include "relay_driver.h"
#include "esp_now_protocol.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#if HAS_PZEM
#include "driver/uart.h"
#endif

static const char *TAG = "T1_TELEMETRY";

#if HAS_PZEM
static void pzem_task(void *arg)
{
    ESP_LOGI(TAG, "PZEM-004T reader task running on UART %d (TX:%d, RX:%d)...",
             PZEM_UART_NUM, PZEM_UART_TX_GPIO, PZEM_UART_RX_GPIO);

    uart_config_t uart_config = {
        .baud_rate = PZEM_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    uart_param_config(PZEM_UART_NUM, &uart_config);
    uart_set_pin(PZEM_UART_NUM, PZEM_UART_TX_GPIO, PZEM_UART_RX_GPIO, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    uart_driver_install(PZEM_UART_NUM, 256, 0, 0, NULL, 0);

    /* PZEM-004T v3 Modbus RTU Read Command: Address 0x01, Function 0x04, Reg 0x0000, Count 0x000A */
    static const uint8_t pzem_read_cmd[] = {0x01, 0x04, 0x00, 0x00, 0x00, 0x0A, 0x70, 0x0D};

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(ESPNOW_TELE_INTERVAL_MS));

        /* Flush UART RX buffer */
        uart_flush(PZEM_UART_NUM);
        uart_write_bytes(PZEM_UART_NUM, (const char *)pzem_read_cmd, sizeof(pzem_read_cmd));

        uint8_t resp[25] = {0};
        int len = uart_read_bytes(PZEM_UART_NUM, resp, sizeof(resp), pdMS_TO_TICKS(200));

        if (len >= 25 && resp[0] == 0x01 && resp[1] == 0x04) {
            /* Decode 10 registers (20 bytes of data starting at index 3) */
            uint16_t raw_v = (resp[3] << 8) | resp[4];
            uint32_t raw_i = (resp[7] << 24) | (resp[8] << 16) | (resp[5] << 8) | resp[6];
            uint32_t raw_p = (resp[11] << 24) | (resp[12] << 16) | (resp[9] << 8) | resp[10];
            uint32_t raw_e = (resp[15] << 24) | (resp[16] << 16) | (resp[13] << 8) | resp[14];
            uint16_t raw_f = (resp[17] << 8) | resp[18];
            uint16_t raw_pf = (resp[19] << 8) | resp[20];

            esp_now_packet_t pkt = {0};
            pkt.msg_type = MSG_TYPE_RESP_POWER_STATUS;
            pkt.device_id = 1;
            pkt.voltage = raw_v * 0.1f;
            pkt.current = raw_i * 0.001f;
            pkt.power = raw_p * 0.1f;
            pkt.energy = raw_e * 1.0f;
            pkt.frequency = raw_f * 0.1f;
            pkt.pf = raw_pf * 0.01f;
            pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
            pkt.relay_state = (relay_driver_get(1) ? 1 : 0) | (relay_driver_get(2) ? 2 : 0);

            espnow_slave_send_telemetry(&pkt);
        }
    }
}
#endif

esp_err_t telemetry_init(void)
{
#if HAS_PZEM
    xTaskCreate(pzem_task, "t1_pzem", 3072, NULL, 4, NULL);
    ESP_LOGI(TAG, "PZEM telemetry initialized.");
#else
    ESP_LOGI(TAG, "PZEM telemetry disabled (HAS_PZEM=0).");
#endif
    return ESP_OK;
}

void telemetry_send_now(void)
{
    esp_now_packet_t pkt = {0};
    pkt.msg_type = MSG_TYPE_RESP_POWER_STATUS;
    pkt.device_id = 1;
    pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
    pkt.relay_state = (relay_driver_get(1) ? 1 : 0) | (relay_driver_get(2) ? 2 : 0);
    espnow_slave_send_telemetry(&pkt);
}
