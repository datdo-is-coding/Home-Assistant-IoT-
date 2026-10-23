#pragma once

#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>

using esp_err_t = int;
constexpr int ESP_OK = 0, ESP_FAIL = -1, ESP_ERR_INVALID_ARG = 1,
    ESP_ERR_NO_MEM = 2, ESP_ERR_TIMEOUT = 3, ESP_ERR_INVALID_STATE = 4,
    ESP_ERR_INVALID_RESPONSE = 5, ESP_ERR_INVALID_CRC = 6,
    ESP_ERR_INVALID_SIZE = 7, ESP_ERR_NOT_FOUND = 8, ESP_ERR_INVALID_VERSION = 9, ESP_ERR_NOT_SUPPORTED = 10;
#define ESP_ERROR_CHECK(x) assert((x) == ESP_OK)
inline const char* esp_err_to_name(int) { return "host error"; }
#define ESP_LOGI(...)
#define ESP_LOGD(...)
#define ESP_LOGW(...)
#define ESP_LOGE(...)
#define IRAM_ATTR
using TickType_t = uint32_t;
using BaseType_t = int;
constexpr int pdTRUE = 1, pdFALSE = 0;
constexpr TickType_t portMAX_DELAY = UINT32_MAX;
#define pdMS_TO_TICKS(ms) (ms)
#define configMAX_PRIORITIES 25
#define tskIDLE_PRIORITY 0
#define CONFIG_ESP_TIMER_SUPPORTS_ISR_DISPATCH_METHOD 1
#define CONFIG_ACTIONBOX_ESPNOW_CHANNEL 11
using portMUX_TYPE = std::mutex;
#define portMUX_INITIALIZER_UNLOCKED {}
#define portENTER_CRITICAL(mux) (mux)->lock()
#define portEXIT_CRITICAL(mux) (mux)->unlock()
inline int64_t esp_timer_get_time() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline void vTaskDelay(TickType_t ticks) { std::this_thread::sleep_for(std::chrono::milliseconds(ticks)); }
struct HostSemaphore {
    std::mutex mutex;
    std::condition_variable ready;
    bool available;
};
using SemaphoreHandle_t = HostSemaphore*;
inline thread_local bool defer_next_take = false;
inline std::atomic<bool> deferred_take_entered{false}, hold_deferred_take{false};
inline SemaphoreHandle_t xSemaphoreCreateMutex() { return new HostSemaphore{{}, {}, true}; }
inline SemaphoreHandle_t xSemaphoreCreateBinary() { return new HostSemaphore{{}, {}, false}; }
inline int xSemaphoreTake(SemaphoreHandle_t s, TickType_t timeout) {
    assert(s);
    if (defer_next_take) {
        defer_next_take = false;
        deferred_take_entered = true;
        while (hold_deferred_take) vTaskDelay(1);
    }
    std::unique_lock<std::mutex> lock(s->mutex);
    if (timeout == portMAX_DELAY) s->ready.wait(lock, [&]{ return s->available; });
    else if (!s->ready.wait_for(lock, std::chrono::milliseconds(timeout), [&]{ return s->available; })) return pdFALSE;
    s->available = false;
    return pdTRUE;
}
inline int xSemaphoreGive(SemaphoreHandle_t s) {
    std::lock_guard<std::mutex> lock(s->mutex);
    s->available = true;
    s->ready.notify_one();
    return pdTRUE;
}
inline int xSemaphoreGiveFromISR(SemaphoreHandle_t s, BaseType_t* woken) {
    *woken = pdTRUE;
    return xSemaphoreGive(s);
}
inline void vSemaphoreDelete(SemaphoreHandle_t s) { delete s; }
enum esp_timer_dispatch_t { ESP_TIMER_TASK, ESP_TIMER_ISR };
struct esp_timer_create_args_t {
    void (*callback)(void*);
    void* arg;
    esp_timer_dispatch_t dispatch_method;
    const char* name;
    bool skip_unhandled_events;
};
using esp_timer_handle_t = esp_timer_create_args_t*;
inline std::atomic<bool> fail_timer_start{false};
inline std::atomic<uint64_t> last_timer_duration{0};
inline esp_err_t esp_timer_create(const esp_timer_create_args_t* args, esp_timer_handle_t* out) {
    *out = new esp_timer_create_args_t(*args);
    return ESP_OK;
}
inline esp_err_t esp_timer_start_once(esp_timer_handle_t timer, uint64_t us) {
    if (fail_timer_start.exchange(false)) return ESP_FAIL;
    last_timer_duration = us;
    auto copy = *timer;
    std::thread([copy, us] {
        std::this_thread::sleep_for(std::chrono::microseconds(us));
        copy.callback(copy.arg);
    }).detach();
    return ESP_OK;
}
inline void esp_timer_isr_dispatch_need_yield() {}
inline esp_err_t esp_timer_delete(esp_timer_handle_t timer) { delete timer; return ESP_OK; }

using gpio_num_t = int;
constexpr int GPIO_NUM_NC = -1;

constexpr int GPIO_MODE_INPUT = 1, GPIO_MODE_OUTPUT = 2,
    GPIO_PULLDOWN_DISABLE = 0, GPIO_PULLDOWN_ENABLE = 1,
    GPIO_PULLUP_DISABLE = 0, GPIO_PULLUP_ENABLE = 1, GPIO_INTR_DISABLE = 0,
    GPIO_PULLUP_ONLY = 0, GPIO_PULLDOWN_ONLY = 1, GPIO_FLOATING = 2;
using gpio_pull_mode_t = int;
inline esp_err_t gpio_set_pull_mode(gpio_num_t, int) { return ESP_OK; }
struct gpio_config_t {
    uint64_t pin_bit_mask;
    int mode, pull_up_en, pull_down_en, intr_type;
};
esp_err_t gpio_config(const gpio_config_t*);
esp_err_t gpio_set_level(gpio_num_t, uint32_t);
int gpio_get_level(gpio_num_t);

using uart_port_t = int;
constexpr int UART_NUM_0 = 0, UART_NUM_1 = 1, UART_NUM_2 = 2,
    UART_PIN_NO_CHANGE = -1, UART_DATA_8_BITS = 8, UART_PARITY_DISABLE = 0,
    UART_STOP_BITS_1 = 1, UART_HW_FLOWCTRL_DISABLE = 0, UART_SCLK_DEFAULT = 0;
struct uart_config_t {
    int baud_rate, data_bits, parity, stop_bits, flow_ctrl, rx_flow_ctrl_thresh, source_clk;
};
esp_err_t uart_param_config(uart_port_t, const uart_config_t*);
esp_err_t uart_set_pin(uart_port_t, int, int, int, int);
esp_err_t uart_driver_install(uart_port_t, int, int, int, void*, int);
esp_err_t uart_driver_delete(uart_port_t);
esp_err_t uart_flush_input(uart_port_t);
int uart_write_bytes(uart_port_t, const void*, size_t);
esp_err_t uart_wait_tx_done(uart_port_t, TickType_t);
int uart_read_bytes(uart_port_t, void*, uint32_t, TickType_t);

constexpr int ESP_MAC_WIFI_STA = 0;
inline esp_err_t esp_read_mac(uint8_t* mac, int) {
    const uint8_t bytes[] = {1, 2, 3, 4, 5, 6};
    memcpy(mac, bytes, 6); return ESP_OK;
}
inline uint32_t esp_random() { return UINT32_MAX; }
using nvs_handle_t = int;
constexpr int NVS_READONLY = 0, NVS_READWRITE = 1,
    ESP_ERR_NVS_NO_FREE_PAGES = 10, ESP_ERR_NVS_NEW_VERSION_FOUND = 11,
    ESP_ERR_NVS_NOT_FOUND = 8;
esp_err_t nvs_flash_init();
esp_err_t nvs_flash_erase();
esp_err_t nvs_open(const char*, int, nvs_handle_t*);
esp_err_t nvs_get_blob(nvs_handle_t, const char*, void*, size_t*);
esp_err_t nvs_set_blob(nvs_handle_t, const char*, const void*, size_t);
esp_err_t nvs_get_str(nvs_handle_t, const char*, char*, size_t*);
esp_err_t nvs_set_str(nvs_handle_t, const char*, const char*);
esp_err_t nvs_get_u32(nvs_handle_t, const char*, uint32_t*);
esp_err_t nvs_set_u32(nvs_handle_t, const char*, uint32_t);
esp_err_t nvs_get_u8(nvs_handle_t, const char*, uint8_t*);
esp_err_t nvs_set_u8(nvs_handle_t, const char*, uint8_t);
esp_err_t nvs_commit(nvs_handle_t);
esp_err_t nvs_erase_key(nvs_handle_t, const char*);
esp_err_t nvs_erase_all(nvs_handle_t);
void nvs_close(nvs_handle_t);
extern "C" void esp_restart(void);

