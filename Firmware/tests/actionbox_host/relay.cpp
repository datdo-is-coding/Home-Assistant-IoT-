#include "host_idf.h"
#include "relay_driver.h"
#include "led_driver.h"
#include <vector>

static std::mutex gpio_mutex;
static int levels[49]{};
static uint64_t outputs = 0;
struct Pulse { int pin; int64_t start, end; };
static std::vector<Pulse> pulses;
static const int set_pins[] = {16, 7, 5};
static const int reset_pins[] = {15, 6, 4};
static bool sensor_ready = true;
extern "C" bool safety_sensor_ready(uint8_t) { return sensor_ready; }

esp_err_t gpio_config(const gpio_config_t* config) {
    outputs |= config->pin_bit_mask;
    return ESP_OK;
}
esp_err_t gpio_set_level(int pin, uint32_t level) {
    assert(pin >= 0 && pin < 49 && "Never write nonexistent LED3");
    std::lock_guard<std::mutex> lock(gpio_mutex);
    const int old = levels[pin];
    levels[pin] = level;
    for (int i = 0; i < 3; ++i) {
        assert(!(levels[set_pins[i]] && levels[reset_pins[i]]) && "SET/RESET overlap");
        if (pin != set_pins[i] && pin != reset_pins[i]) continue;
        if (level && !old) pulses.push_back({pin, esp_timer_get_time(), 0});
        if (!level && old) {
            for (auto& pulse : pulses) if (pulse.pin == pin && !pulse.end) pulse.end = esp_timer_get_time();
        }
    }
    return ESP_OK;
}
static void all_coils_low() {
    std::lock_guard<std::mutex> lock(gpio_mutex);
    for (int pin : {4, 5, 6, 7, 15, 16}) assert(levels[pin] == 0);
}
int main() {
    assert(relay_driver_init() == ESP_OK);
    assert(pulses.size() == 3 && "Boot must RESET all three physical relays");
    for (int i = 0; i < 3; ++i) {
        assert(pulses[i].pin == reset_pins[i]);
        assert(outputs & (1ULL << set_pins[i]));
        assert(outputs & (1ULL << reset_pins[i]));
        assert(relay_get_state(i + 1) == RELAY_STATE_OFF);
    }
    all_coils_low();
    assert(led_driver_init() == ESP_OK);
    led_set_pattern(3, LED_PATTERN_ON); // no LED3 exists on this PCB
    led_driver_tick();
    for (int ch = 1; ch <= 3; ++ch) {
        assert(relay_on(ch) == ESP_OK);
        assert(pulses.back().pin == set_pins[ch - 1]);
        assert(last_timer_duration == 50000);
        all_coils_low();
        auto count = pulses.size();
        assert(relay_on(ch) == ESP_OK && pulses.size() == count);
        assert(relay_off(ch) == ESP_OK);
        assert(pulses.back().pin == reset_pins[ch - 1]);
        count = pulses.size();
        assert(relay_off(ch) == ESP_OK && pulses.size() == count);
    }
    sensor_ready = false;
    assert(relay_on(3) != ESP_OK);
    sensor_ready = true;
    assert(relay_on(3) == ESP_OK);
    relay_set_fault(3, RELAY_FAULT_OVERCURRENT);
    assert(relay_get_state(3) == RELAY_STATE_OFF);
    assert(relay_on(3) != ESP_OK);
    assert(relay_clear_fault(3) == ESP_OK);
    fail_timer_start = true;
    assert(relay_on(3) != ESP_OK);
    assert(relay_get_state(3) != RELAY_STATE_ON);
    all_coils_low();

    // A task-context emergency arriving during a SET must wait for that pulse,
    // then RESET every channel.
    std::thread on([] { relay_on(1); });
    bool set_active = false;
    for (int i = 0; i < 1000 && !set_active; ++i) {
        { std::lock_guard<std::mutex> lock(gpio_mutex); set_active = levels[16]; }
        if (!set_active) vTaskDelay(1);
    }
    assert(set_active);
    relay_emergency_all_off();
    on.join();
    for (int ch = 1; ch <= 3; ++ch) assert(relay_get_state(ch) == RELAY_STATE_OFF);
    all_coils_low();
    // An ON that started before the emergency, but has not acquired the mutex,
    // must not capture the new emergency generation and turn back on afterwards.
    hold_deferred_take = true;
    esp_err_t pending_result = ESP_OK;
    std::thread pending([&] { defer_next_take = true; pending_result = relay_on(2); });
    while (!deferred_take_entered) vTaskDelay(1);
    relay_emergency_all_off();
    hold_deferred_take = false;
    pending.join();
    assert(pending_result != ESP_OK && relay_get_state(2) == RELAY_STATE_OFF);

    // The same cancellation must hold across the inrush stagger wait.
    assert(relay_on(1) == ESP_OK);
    std::thread stagger([&] { pending_result = relay_on(2); });
    vTaskDelay(10);
    relay_emergency_all_off();
    stagger.join();
    assert(pending_result != ESP_OK && relay_get_state(2) == RELAY_STATE_OFF);
    all_coils_low();
    auto count = pulses.size();
    assert(relay_on(0) == ESP_ERR_INVALID_ARG);
    assert(relay_off(4) == ESP_ERR_INVALID_ARG);
    assert(pulses.size() == count);
}
