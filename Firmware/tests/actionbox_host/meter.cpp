#include "host_idf.h"
#include "bl0942.h"
#include <vector>

static int rx_pin = -1, installed = 0;
static bool flushed = false, timeout_rx = false, bad_crc = false;
static std::vector<int> queried;
esp_err_t uart_param_config(int port, const uart_config_t* config) {
    assert(port == 1 && config->baud_rate == 4800);
    return ESP_OK;
}
esp_err_t uart_set_pin(int port, int tx, int rx, int, int) {
    assert(port == 1 && (tx == 9 || tx == UART_PIN_NO_CHANGE));
    assert(rx >= 10 && rx <= 12);
    rx_pin = rx;
    flushed = false;
    return ESP_OK;
}
esp_err_t uart_driver_install(int port, int, int, int, void*, int) {
    assert(port == 1); ++installed; return ESP_OK;
}
esp_err_t uart_driver_delete(int) { return ESP_OK; }
esp_err_t uart_flush_input(int port) { assert(port == 1); flushed = true; return ESP_OK; }
int uart_write_bytes(int port, const void* bytes, size_t len) {
    assert(port == 1 && flushed);
    const auto* p = static_cast<const uint8_t*>(bytes);
    assert(len == 2 && p[0] == 0x58 && p[1] == 0xaa);
    queried.push_back(rx_pin);
    return 2;
}
esp_err_t uart_wait_tx_done(int port, TickType_t) { assert(port == 1); return ESP_OK; }
int uart_read_bytes(int port, void* bytes, uint32_t len, TickType_t) {
    assert(port == 1 && len == 23);
    if (timeout_rx) return 0;
    auto* frame = static_cast<uint8_t*>(bytes);
    memset(frame, 0, len);
    frame[0] = 0x55;
    frame[1] = rx_pin; // distinguish each physical input after calibration
    uint8_t sum = 0x58;
    for (int i = 0; i < 22; ++i) sum += frame[i];
    frame[22] = bad_crc ? 0 : uint8_t(~sum);
    return len;
}
int main() {
    assert(bl0942_driver_init() == ESP_OK);
    assert(installed == 1 && "V2 must leave UART0/debug available");
    for (int ch : {3, 1, 2, 3}) {
        SensorCalibration cal{1, 1, 1};
        bl0942_set_calibration(ch, &cal);
        CurrentMeasurement sample{};
        assert(bl0942_read_channel(ch, &sample) == ESP_OK);
        assert(sample.validity == SENSOR_STATUS_VALID && sample.current_rms_ma == unsigned(ch + 9));
    }
    assert((queried == std::vector<int>{12, 10, 11, 12}));
    CurrentMeasurement sample{};
    timeout_rx = true;
    assert(bl0942_read_channel(3, &sample) == ESP_ERR_TIMEOUT);
    assert(sample.validity == SENSOR_STATUS_TIMEOUT);
    timeout_rx = false; bad_crc = true;
    assert(bl0942_read_channel(3, &sample) == ESP_ERR_INVALID_CRC);
    assert(sample.validity == SENSOR_STATUS_CHECKSUM_ERR);
    assert(bl0942_read_channel(4, &sample) == ESP_ERR_INVALID_ARG);
}
