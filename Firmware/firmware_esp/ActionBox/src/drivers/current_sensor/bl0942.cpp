/**
 * @file bl0942.cpp
 * @brief Production BL0942 Energy Metering IC Driver Implementation
 */

#include "bl0942.h"
#include "board_pins.h"
#include "app_config.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "BL0942_DRIVER";

#define BL0942_PACKET_HEADER             0x55
#define BL0942_CMD_READ_ALL              0xAA
#define BL0942_CMD_HEADER_READ           0x58
#define BL0942_PACKET_LEN                23
#define BL0942_UART_BUF_SIZE             256

static SensorCalibration s_calibrations[BOARD_RELAY_CHANNEL_COUNT];
static CurrentMeasurement s_latest_measurements[BOARD_RELAY_CHANNEL_COUNT];
static SemaphoreHandle_t s_sensor_mutex = NULL;
static bool s_driver_initialized = false;

static esp_err_t init_channel_uart(uart_port_t port, gpio_num_t tx_pin, gpio_num_t rx_pin) {
    uart_config_t uart_config = {};
    uart_config.baud_rate = BOARD_BL0942_UART_BAUDRATE;
    uart_config.data_bits = UART_DATA_8_BITS;
    uart_config.parity    = UART_PARITY_DISABLE;
    uart_config.stop_bits = UART_STOP_BITS_1;
    uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    uart_config.rx_flow_ctrl_thresh = 0;
    uart_config.source_clk = UART_SCLK_DEFAULT;

    esp_err_t err = uart_param_config(port, &uart_config);
    if (err != ESP_OK) return err;

    err = uart_set_pin(port, tx_pin, rx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) return err;

    err = uart_driver_install(port, BL0942_UART_BUF_SIZE * 2, 0, 0, NULL, 0);
    return err;
}

esp_err_t bl0942_driver_init(void) {
    if (s_driver_initialized) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Initializing BL0942 Energy Metering Driver...");
    s_sensor_mutex = xSemaphoreCreateMutex();
    if (!s_sensor_mutex) {
        ESP_LOGE(TAG, "Failed to create BL0942 mutex!");
        return ESP_ERR_NO_MEM;
    }

    /* Initialize default calibration factors */
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        s_calibrations[i].current_factor = BL0942_DEFAULT_CAL_CURRENT;
        s_calibrations[i].voltage_factor = BL0942_DEFAULT_CAL_VOLTAGE;
        s_calibrations[i].power_factor   = BL0942_DEFAULT_CAL_POWER;

        memset(&s_latest_measurements[i], 0, sizeof(CurrentMeasurement));
        s_latest_measurements[i].validity = SENSOR_STATUS_UNINITIALIZED;
    }

    /* Channel 1 UART: TX=IO9, RX=IO10 */
    esp_err_t err = init_channel_uart(BOARD_BL0942_UART_NUM_CH1, BOARD_PIN_BL0942_TX, BOARD_PIN_BL0942_RX_CH1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init UART for Ch1: %s", esp_err_to_name(err));
        return err;
    }

    /* Channel 2 UART: TX=IO9 (shared), RX=IO11 */
    err = init_channel_uart(BOARD_BL0942_UART_NUM_CH2, GPIO_NUM_NC, BOARD_PIN_BL0942_RX_CH2);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init UART for Ch2: %s", esp_err_to_name(err));
        return err;
    }

    s_driver_initialized = true;
    ESP_LOGI(TAG, "BL0942 Driver successfully initialized (Ch1: RX=IO%d, Ch2: RX=IO%d, TX=IO%d).",
             BOARD_PIN_BL0942_RX_CH1, BOARD_PIN_BL0942_RX_CH2, BOARD_PIN_BL0942_TX);
    return ESP_OK;
}

static bool verify_checksum(const uint8_t *frame) {
    uint8_t sum = 0;
    for (int i = 0; i < BL0942_PACKET_LEN - 1; i++) {
        sum += frame[i];
    }
    uint8_t expected = (uint8_t)(~sum);
    return (frame[BL0942_PACKET_LEN - 1] == expected);
}

esp_err_t bl0942_read_channel(uint8_t channel, CurrentMeasurement *out_meas) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !out_meas) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_driver_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    uart_port_t uart_port = (channel == 1) ? BOARD_BL0942_UART_NUM_CH1 : BOARD_BL0942_UART_NUM_CH2;
    uint8_t idx = channel - 1;

    if (xSemaphoreTake(s_sensor_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    /* Allow short settle time and clear stale RX FIFO before polling */
    vTaskDelay(pdMS_TO_TICKS(10));
    uart_flush_input(uart_port);

    /* Broadcast read all registers command: 0x58 0xAA */
    const uint8_t query_cmd[2] = { BL0942_CMD_HEADER_READ, BL0942_CMD_READ_ALL };
    uart_write_bytes(BOARD_BL0942_UART_NUM_CH1, (const char*)query_cmd, 2);
    uart_wait_tx_done(BOARD_BL0942_UART_NUM_CH1, pdMS_TO_TICKS(20));

    /* Wait for 23-byte response frame (at 4800 baud, 23 bytes ~48ms) */
    uint8_t rx_buf[BL0942_PACKET_LEN];
    int bytes_read = uart_read_bytes(uart_port, rx_buf, BL0942_PACKET_LEN, pdMS_TO_TICKS(200));

    if (bytes_read < BL0942_PACKET_LEN) {
        s_latest_measurements[idx].validity = SENSOR_STATUS_TIMEOUT;
        *out_meas = s_latest_measurements[idx];
        xSemaphoreGive(s_sensor_mutex);
        ESP_LOGW(TAG, "Ch%u BL0942 Read timeout: received %d/23 bytes", channel, bytes_read);
        return ESP_ERR_TIMEOUT;
    }

    /* Verify packet preamble */
    if (rx_buf[0] != BL0942_PACKET_HEADER) {
        s_latest_measurements[idx].validity = SENSOR_STATUS_CHECKSUM_ERR;
        *out_meas = s_latest_measurements[idx];
        xSemaphoreGive(s_sensor_mutex);
        ESP_LOGW(TAG, "Ch%u BL0942 invalid header: 0x%02X (expected 0x55)", channel, rx_buf[0]);
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* Verify packet checksum: BL0942 computes ~(0x58 + sum(rx_buf[0..21])) */
    uint8_t sum = BL0942_CMD_HEADER_READ; /* 0x58 */
    for (int i = 0; i < BL0942_PACKET_LEN - 1; i++) {
        sum += rx_buf[i];
    }
    uint8_t expected = (uint8_t)(~sum);

    if (rx_buf[BL0942_PACKET_LEN - 1] != expected) {
        s_latest_measurements[idx].validity = SENSOR_STATUS_CHECKSUM_ERR;
        *out_meas = s_latest_measurements[idx];
        xSemaphoreGive(s_sensor_mutex);
        ESP_LOGW(TAG, "Ch%u BL0942 Checksum error! Got 0x%02X expected 0x%02X",
                 channel, rx_buf[BL0942_PACKET_LEN - 1], expected);
        return ESP_ERR_INVALID_CRC;
    }

    /* Unpack 24-bit Little Endian fields */
    uint32_t raw_i = (uint32_t)rx_buf[1] | ((uint32_t)rx_buf[2] << 8) | ((uint32_t)rx_buf[3] << 16);
    uint32_t raw_v = (uint32_t)rx_buf[4] | ((uint32_t)rx_buf[5] << 8) | ((uint32_t)rx_buf[6] << 16);
    
    int32_t raw_w = (int32_t)rx_buf[10] | ((int32_t)rx_buf[11] << 8) | ((int32_t)rx_buf[12] << 16);
    if (raw_w & 0x00800000) {
        raw_w |= 0xFF000000; /* Sign extension for active power */
    }
    
    uint32_t raw_cf = (uint32_t)rx_buf[13] | ((uint32_t)rx_buf[14] << 8) | ((uint32_t)rx_buf[15] << 16);

    /* Apply calibration */
    SensorCalibration cal = s_calibrations[idx];
    s_latest_measurements[idx].current_rms_ma = (uint32_t)((float)raw_i * cal.current_factor);
    s_latest_measurements[idx].voltage_rms_v  = (uint32_t)((float)raw_v * cal.voltage_factor);
    s_latest_measurements[idx].active_power_w = (int32_t)((float)raw_w * cal.power_factor);
    s_latest_measurements[idx].energy_wh      = raw_cf;
    s_latest_measurements[idx].validity       = SENSOR_STATUS_VALID;
    s_latest_measurements[idx].sample_count++;
    s_latest_measurements[idx].timestamp_ms   = (uint32_t)(esp_timer_get_time() / 1000);

    /* Periodic rate-limited console logging every 1s per channel */
    static uint32_t s_last_log_ms[BOARD_RELAY_CHANNEL_COUNT] = {0};
    if (s_latest_measurements[idx].timestamp_ms - s_last_log_ms[idx] >= 1000) {
        s_last_log_ms[idx] = s_latest_measurements[idx].timestamp_ms;
        ESP_LOGI(TAG, "Ch%u: I_RMS=%lu mA (raw_i=%lu, 0x%06lX), V_RMS=%lu V, P=%ld W",
                 (unsigned)channel,
                 (unsigned long)s_latest_measurements[idx].current_rms_ma,
                 (unsigned long)raw_i, (unsigned long)raw_i,
                 (unsigned long)s_latest_measurements[idx].voltage_rms_v,
                 (long)s_latest_measurements[idx].active_power_w);
    }

    /* Flag overcurrent if raw current exceeds threshold */
    s_latest_measurements[idx].overcurrent = 
        (s_latest_measurements[idx].current_rms_ma >= SAFETY_DEFAULT_MAX_CURRENT_MA);

    *out_meas = s_latest_measurements[idx];
    xSemaphoreGive(s_sensor_mutex);
    return ESP_OK;
}

esp_err_t bl0942_get_latest_measurement(uint8_t channel, CurrentMeasurement *out_meas) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !out_meas) {
        return ESP_ERR_INVALID_ARG;
    }
    if (xSemaphoreTake(s_sensor_mutex, pdMS_TO_TICKS(300)) == pdTRUE) {
        *out_meas = s_latest_measurements[channel - 1];
        xSemaphoreGive(s_sensor_mutex);
        return ESP_OK;
    }
    return ESP_ERR_TIMEOUT;
}

esp_err_t bl0942_set_calibration(uint8_t channel, const SensorCalibration *cal) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !cal) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_sensor_mutex, portMAX_DELAY) == pdTRUE) {
        s_calibrations[channel - 1] = *cal;
        ESP_LOGI(TAG, "Calibration updated for Ch%u: K_I=%f, K_V=%f, K_P=%f",
                 channel, cal->current_factor, cal->voltage_factor, cal->power_factor);
        xSemaphoreGive(s_sensor_mutex);
        return ESP_OK;
    }
    return ESP_ERR_TIMEOUT;
}

esp_err_t bl0942_get_calibration(uint8_t channel, SensorCalibration *out_cal) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !out_cal) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_sensor_mutex, portMAX_DELAY) == pdTRUE) {
        *out_cal = s_calibrations[channel - 1];
        xSemaphoreGive(s_sensor_mutex);
        return ESP_OK;
    }
    return ESP_ERR_TIMEOUT;
}

static const ICurrentSensorDriver s_bl0942_driver_interface = {
    .init            = bl0942_driver_init,
    .read            = bl0942_read_channel,
    .set_calibration = bl0942_set_calibration,
    .get_calibration = bl0942_get_calibration,
};

const ICurrentSensorDriver* bl0942_get_driver(void) {
    return &s_bl0942_driver_interface;
}
