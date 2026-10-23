#include "subbox_led.h"
#include "../../../common/device_lifecycle.h"
#include "../../../common/connection_status.h"
#include "config/board_pins.h"
#include "storage/security_config.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <atomic>

static std::atomic<bool> s_fault(false), s_wifi(false), s_mqtt(false), s_configured(false), s_unclaimed(false);
static std::atomic<int64_t> s_peer_seen(0);
static esp_timer_handle_t s_timer = nullptr;
static int64_t s_pattern_start_us = 0;
static int64_t s_online_entered_us = 0;
static LedPattern s_previous_pattern = LedPattern::OFF;

static void tick(void*) {
    const int64_t now_us = esp_timer_get_time();
    const bool is_fault = s_fault.load();
    const bool is_wifi = s_wifi.load();
    const bool is_mqtt = s_mqtt.load();
    const bool is_cfg = s_configured.load();
    const bool is_unclaimed = s_unclaimed.load() || !is_cfg;

    LifecycleState lifecycle = is_unclaimed ? LifecycleState::UNCLAIMED : LifecycleState::CLAIMED;
    if (SecurityConfig::isPairingAllowed()) lifecycle = LifecycleState::CLAIMING;
    ConnectivityState connectivity = ConnectivityState::UNKNOWN;
    if (!is_wifi) {
        connectivity = ConnectivityState::OFFLINE;
    } else if (!is_mqtt) {
        connectivity = ConnectivityState::CONNECTING;
    } else {
        connectivity = ConnectivityState::ONLINE;
    }

    FaultKind fault = is_fault ? FaultKind::SYSTEM_FAULT : FaultKind::NONE;

    if (connectivity == ConnectivityState::ONLINE && lifecycle == LifecycleState::CLAIMED) {
        if (s_online_entered_us == 0) s_online_entered_us = now_us;
    } else {
        s_online_entered_us = 0;
    }
    uint64_t elapsed_in_online_ms = (s_online_entered_us > 0) ? (uint64_t)((now_us - s_online_entered_us) / 1000) : 0;

    LedPattern pattern = resolve_device_led_pattern(
        lifecycle,
        connectivity,
        fault,
        false,
        OperationKind::IDENTIFY,
        OperationState::RUNNING,
        elapsed_in_online_ms
    );

    if (pattern != s_previous_pattern) {
        s_previous_pattern = pattern;
        s_pattern_start_us = now_us;
        const char* labels[] = {
            "FAULT", "AWAITING_FACTORY_RESET", "AWAITING_NETWORK_RESET",
            "CLAIMING", "CONFIG_APPLYING", "UNCLAIMED", "IDENTIFY",
            "OFFLINE", "CONNECTING", "READY", "OFF"
        };
        ESP_LOGI("SUBBOX_LED", "LED1 pattern=%s", labels[static_cast<uint8_t>(pattern)]);
    }

    uint64_t elapsed_in_pattern_ms = (s_pattern_start_us > 0 && now_us >= s_pattern_start_us)
                                   ? (uint64_t)((now_us - s_pattern_start_us) / 1000) : 0;
    bool on = status_led_is_active(pattern, elapsed_in_pattern_ms);
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
void subbox_led_set_unclaimed(bool unclaimed) { s_unclaimed.store(unclaimed); }
bool subbox_led_wifi_connected(void) { return s_wifi.load(); }
bool subbox_led_mqtt_connected(void) { return s_mqtt.load(); }
