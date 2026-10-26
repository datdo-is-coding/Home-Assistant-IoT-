#include "bl0942.h"
#include "board_pins.h"
#include "app_config.h"

#include <string.h>
#include <cmath>
#include <initializer_list>
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
// UART waits must not block telemetry snapshots on the other core.
static portMUX_TYPE s_cache_lock = portMUX_INITIALIZER_UNLOCKED;
static void cache_measurement(uint8_t idx, const CurrentMeasurement &measurement) {
    portENTER_CRITICAL(&s_cache_lock);
    s_latest_measurements[idx] = measurement;
    portEXIT_CRITICAL(&s_cache_lock);
}
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

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        s_calibrations[i].current_factor = BL0942_DEFAULT_CAL_CURRENT;
        s_calibrations[i].voltage_factor = BL0942_DEFAULT_CAL_VOLTAGE;
        s_calibrations[i].power_factor   = BL0942_DEFAULT_CAL_POWER;

        memset(&s_latest_measurements[i], 0, sizeof(CurrentMeasurement));
        s_latest_measurements[i].validity = SENSOR_STATUS_UNINITIALIZED;
    }

    esp_err_t err = init_channel_uart(BOARD_BL0942_UART_NUM_CH1, BOARD_PIN_BL0942_TX, BOARD_PIN_BL0942_RX_CH1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init UART for Ch1: %s", esp_err_to_name(err));
        return err;
    }

    gpio_set_pull_mode(BOARD_PIN_BL0942_TX, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode(BOARD_PIN_BL0942_RX_CH1, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode(BOARD_PIN_BL0942_RX_CH2, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode(BOARD_PIN_BL0942_RX_CH3, GPIO_PULLUP_ONLY);

#if !defined(BOARD_BL0942_MULTIPLEX_RX)

    err = init_channel_uart(BOARD_BL0942_UART_NUM_CH2, GPIO_NUM_NC, BOARD_PIN_BL0942_RX_CH2);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init UART for Ch2: %s", esp_err_to_name(err));
        return err;
    }
#endif

    s_driver_initialized = true;
    ESP_LOGI(TAG, "BL0942 Driver initialized (%d channels, TX=IO%d).",
             BOARD_RELAY_CHANNEL_COUNT, BOARD_PIN_BL0942_TX);
    return ESP_OK;
}

esp_err_t bl0942_read_channel(uint8_t channel, CurrentMeasurement *out_meas) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !out_meas) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_driver_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

#if defined(BOARD_BL0942_MULTIPLEX_RX)
    uart_port_t uart_port = BOARD_BL0942_UART_NUM_CH1;
    static const gpio_num_t rx_pins[] = {
        BOARD_PIN_BL0942_RX_CH1, BOARD_PIN_BL0942_RX_CH2, BOARD_PIN_BL0942_RX_CH3
    };
    static_assert(sizeof(rx_pins) / sizeof(rx_pins[0]) == BOARD_RELAY_CHANNEL_COUNT);
#else
    uart_port_t uart_port = (channel == 1) ? BOARD_BL0942_UART_NUM_CH1 : BOARD_BL0942_UART_NUM_CH2;
#endif
    uint8_t idx = channel - 1;

    if (xSemaphoreTake(s_sensor_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        *out_meas = {};
        out_meas->validity = SENSOR_STATUS_TIMEOUT;
        return ESP_ERR_TIMEOUT;
    }

    CurrentMeasurement measurement{};
    bl0942_get_latest_measurement(channel, &measurement);
#if defined(BOARD_BL0942_MULTIPLEX_RX)

    esp_err_t route_err = uart_set_pin(uart_port, UART_PIN_NO_CHANGE, rx_pins[idx],
                                      UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (route_err != ESP_OK) {
        measurement.validity = SENSOR_STATUS_UNINITIALIZED;
        *out_meas = measurement;
        cache_measurement(idx, measurement);
        xSemaphoreGive(s_sensor_mutex);
        return route_err;
    }
#endif

    vTaskDelay(pdMS_TO_TICKS(10));
    uart_flush_input(uart_port);

    const uint8_t query_cmd[2] = { BL0942_CMD_HEADER_READ, BL0942_CMD_READ_ALL };
    int sent = uart_write_bytes(BOARD_BL0942_UART_NUM_CH1, (const char*)query_cmd, 2);
    esp_err_t tx_err = uart_wait_tx_done(BOARD_BL0942_UART_NUM_CH1, pdMS_TO_TICKS(20));
    if (sent != 2 || tx_err != ESP_OK) {
        measurement.validity = SENSOR_STATUS_TIMEOUT;
        *out_meas = measurement;

        vTaskDelay(pdMS_TO_TICKS(60));
        cache_measurement(idx, measurement);
        xSemaphoreGive(s_sensor_mutex);
        return tx_err != ESP_OK ? tx_err : ESP_FAIL;
    }

    uint8_t rx_raw[64];
    int bytes_read = uart_read_bytes(uart_port, rx_raw, sizeof(rx_raw), pdMS_TO_TICKS(200));

    if (bytes_read < BL0942_PACKET_LEN) {
        measurement.validity = SENSOR_STATUS_TIMEOUT;
        *out_meas = measurement;
        cache_measurement(idx, measurement);
        xSemaphoreGive(s_sensor_mutex);
        if (bytes_read > 0) {
            char hex[80] = {0};
            for (int b = 0; b < bytes_read && b < 16; b++) {
                snprintf(hex + strlen(hex), sizeof(hex) - strlen(hex), "%02X ", rx_raw[b]);
            }
            ESP_LOGW(TAG, "Ch%u BL0942 Short read: received %d/23 bytes: [%s]", channel, bytes_read, hex);
        } else {
            ESP_LOGW(TAG, "Ch%u BL0942 Read timeout: received 0/23 bytes", channel);
        }
        return ESP_ERR_TIMEOUT;
    }

    int frame_start = -1;
    bool saw_header = false;
    for (int offset = 0; offset <= bytes_read - BL0942_PACKET_LEN; offset++) {
        if (rx_raw[offset] == BL0942_PACKET_HEADER) {
            saw_header = true;
            uint8_t sum = BL0942_CMD_HEADER_READ;
            for (int i = 0; i < BL0942_PACKET_LEN - 1; i++) {
                sum += rx_raw[offset + i];
            }
            uint8_t expected = (uint8_t)(~sum);
            if (rx_raw[offset + BL0942_PACKET_LEN - 1] == expected) {
                frame_start = offset;
                break;
            }
        }
    }

    if (frame_start < 0) {
        measurement.validity = SENSOR_STATUS_CHECKSUM_ERR;
        *out_meas = measurement;
        cache_measurement(idx, measurement);
        xSemaphoreGive(s_sensor_mutex);
        char hex[160] = {0};
        for (int b = 0; b < bytes_read && b < 28; b++) {
            snprintf(hex + strlen(hex), sizeof(hex) - strlen(hex), "%02X ", rx_raw[b]);
        }
        ESP_LOGW(TAG, "Ch%u BL0942 frame sync failed (received %d bytes). Raw: [%s]", channel, bytes_read, hex);
        return saw_header ? ESP_ERR_INVALID_CRC : ESP_ERR_INVALID_RESPONSE;
    }

    const uint8_t *rx_buf = &rx_raw[frame_start];
    if (frame_start > 0) {
        ESP_LOGD(TAG, "Ch%u BL0942 frame synced at offset +%d", channel, frame_start);
    }

    uint32_t raw_i = (uint32_t)rx_buf[1] | ((uint32_t)rx_buf[2] << 8) | ((uint32_t)rx_buf[3] << 16);
    uint32_t raw_v = (uint32_t)rx_buf[4] | ((uint32_t)rx_buf[5] << 8) | ((uint32_t)rx_buf[6] << 16);

    int32_t raw_w = (int32_t)rx_buf[10] | ((int32_t)rx_buf[11] << 8) | ((int32_t)rx_buf[12] << 16);
    if (raw_w & 0x00800000) {
        raw_w |= 0xFF000000;
    }

    uint32_t raw_cf = (uint32_t)rx_buf[13] | ((uint32_t)rx_buf[14] << 8) | ((uint32_t)rx_buf[15] << 16);

    SensorCalibration cal = s_calibrations[idx];
    measurement.current_rms_ma = (uint32_t)((float)raw_i * cal.current_factor);
    measurement.voltage_rms_v  = (uint32_t)((float)raw_v * cal.voltage_factor);
    measurement.active_power_w = (int32_t)((float)raw_w * cal.power_factor);
    measurement.energy_wh      = raw_cf;
    measurement.validity       = SENSOR_STATUS_VALID;
    measurement.sample_count++;
    measurement.timestamp_ms   = (uint32_t)(esp_timer_get_time() / 1000);

    static uint32_t s_last_log_ms[BOARD_RELAY_CHANNEL_COUNT] = {0};
    if (measurement.timestamp_ms - s_last_log_ms[idx] >= 10000) {
        s_last_log_ms[idx] = measurement.timestamp_ms;
        ESP_LOGI(TAG, "Ch%u: I_RMS=%lu mA raw_i=%lu K_I=%.7f raw_v=%lu",
                 (unsigned)channel,
                 (unsigned long)measurement.current_rms_ma,
                 (unsigned long)raw_i, (double)cal.current_factor,
                 (unsigned long)raw_v);
    }

    measurement.overcurrent =
        (measurement.current_rms_ma >= SAFETY_DEFAULT_MAX_CURRENT_MA);

    *out_meas = measurement;
    cache_measurement(idx, measurement);
    xSemaphoreGive(s_sensor_mutex);
    return ESP_OK;
}

esp_err_t bl0942_get_latest_measurement(uint8_t channel, CurrentMeasurement *out_meas) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !out_meas) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_driver_initialized) {
        *out_meas = {};
        out_meas->validity = SENSOR_STATUS_UNINITIALIZED;
        return ESP_ERR_INVALID_STATE;
    }
    portENTER_CRITICAL(&s_cache_lock);
    *out_meas = s_latest_measurements[channel - 1];
    portEXIT_CRITICAL(&s_cache_lock);
    return ESP_OK;
}

esp_err_t bl0942_set_calibration(uint8_t channel, const SensorCalibration *cal) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !cal) {
        return ESP_ERR_INVALID_ARG;
    }

    // Bound 24-bit raw conversions to their 32-bit measurement fields.
    for (float factor : {cal->current_factor, cal->voltage_factor, cal->power_factor}) {
        if (!std::isfinite(factor) || factor <= 0 || factor > 255.0f) return ESP_ERR_INVALID_ARG;
    }
    if (!s_driver_initialized) return ESP_ERR_INVALID_STATE;

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
