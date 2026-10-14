#include "host_idf.h"
#include "relay_driver.h"
#include "led_driver.h"

static int levels[49]{};
static uint64_t outputs;
extern "C" bool safety_sensor_ready(uint8_t) { return true; }
esp_err_t gpio_config(const gpio_config_t* config) { outputs |= config->pin_bit_mask; return ESP_OK; }
esp_err_t gpio_set_level(int pin, uint32_t level) { assert(pin >= 0 && pin < 49); levels[pin] = level; return ESP_OK; }
int main() {
    assert(relay_driver_init() == ESP_OK);
    assert(outputs == ((1ULL << 4) | (1ULL << 5)));
    assert(levels[4] == 0 && levels[5] == 0);
    assert(relay_on(1) == ESP_OK && levels[4] == 1);
    assert(relay_on(2) == ESP_OK && levels[5] == 1);
    assert(relay_on(3) == ESP_ERR_INVALID_ARG);
    assert(relay_off(1) == ESP_OK && levels[4] == 0 && levels[5] == 1);
    relay_emergency_all_off();
    assert(levels[4] == 0 && levels[5] == 0);
    assert(last_timer_duration == 0);
    assert(led_driver_init() == ESP_OK);
    led_set_pattern(1, LED_PATTERN_ON);
    led_set_pattern(2, LED_PATTERN_ON);
    assert(levels[48] == 1 && levels[47] == 1);
}
