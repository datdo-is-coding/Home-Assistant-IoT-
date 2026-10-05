#include "subbox_led.h"
#include "../../../common/connection_status.h"
#include "config/board_pins.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <atomic>

static std::atomic<bool> s_fault(false), s_wifi(false), s_mqtt(false), s_configured(false);
static std::atomic<int64_t> s_peer_seen(0);
static esp_timer_handle_t s_timer = nullptr;

static void tick(void*) {
    const int64_t now = esp_timer_get_time();
    const auto peer = s_peer_seen.load();
    const unsigned code = subbox_status(s_wifi.load(), s_configured.load(), s_mqtt.load(),
                                        peer > 0 && now - peer < 15000000, s_fault.load());
    static unsigned previous = 99;
    static int64_t start = 0;
    if (code != previous) {
        previous = code;
        start = now;
        const char* labels[] = {"READY", "WIFI_DISCONNECTED", "MQTT_NOT_CONFIGURED",
                                "MQTT_DISCONNECTED", "ACTIONBOX_MISSING", "SYSTEM_FAULT"};
        ESP_LOGI("SUBBOX_LED", "LED1 code=%u %s", code, labels[code]);
    }
    bool on = status_led_level(code, (now - start) / 1000);
    gpio_set_level(BOARD_PIN_LED_SYSTEM, on ? BOARD_LED_ACTIVE_LEVEL : !BOARD_LED_ACTIVE_LEVEL);
}

esp_err_t subbox_led_init(void) {
    gpio_config_t io{};
    io.mode = GPIO_MODE_OUTPUT;
    io.pin_bit_mask = 1ULL << BOARD_PIN_LED_SYSTEM;
    esp_err_t err = gpio_config(&io);
    if (err != ESP_OK) return err;
    esp_timer_create_args_t args{};
    args.callback = tick;
    args.name = "subbox_led";
    args.skip_unhandled_events = true;
    err = esp_timer_create(&args, &s_timer);
    return err == ESP_OK ? esp_timer_start_periodic(s_timer, 50000) : err;
}
void subbox_led_set_wifi_connected(bool connected) { s_wifi.store(connected); }
void subbox_led_set_mqtt_connected(bool connected) { s_mqtt.store(connected); }
void subbox_led_set_mqtt_configured(bool configured) { s_configured.store(configured); }
void subbox_led_peer_seen(void) { s_peer_seen.store(esp_timer_get_time()); }
void subbox_led_set_error(bool error) { s_fault.store(error); }
bool subbox_led_wifi_connected(void) { return s_wifi.load(); }
bool subbox_led_mqtt_connected(void) { return s_mqtt.load(); }
