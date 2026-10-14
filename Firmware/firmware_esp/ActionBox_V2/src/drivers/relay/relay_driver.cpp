/**
 * @file relay_driver.cpp
 * @brief Thread-safe Relay Driver Implementation Supporting Monostable & Latching Relays
 */

#include "relay_driver.h"
#include "board_pins.h"
#include "app_config.h"
#include "safety_supervisor.h"

#include <string.h>
#include <atomic>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "driver/gpio.h"

static const char *TAG = "RELAY_DRIVER";

static RelayChannelInfo s_channels[BOARD_RELAY_CHANNEL_COUNT];
static SemaphoreHandle_t s_relay_mutex = NULL;
static int64_t s_last_switch_time_us = 0;
static std::atomic<uint32_t> s_emergency_generation(0);

static inline bool is_valid_channel(uint8_t channel) {
    return (channel >= 1 && channel <= BOARD_RELAY_CHANNEL_COUNT);
}

static inline uint8_t ch_idx(uint8_t channel) {
    return channel - 1;
}

static gpio_num_t get_relay_pin(uint8_t channel) {
    switch (channel) {
#if (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL)
        case 1:  return BOARD_PIN_RELAY_CH1_SET;
        case 2:  return BOARD_PIN_RELAY_CH2_SET;
#if BOARD_RELAY_CHANNEL_COUNT >= 3
        case 3:  return BOARD_PIN_RELAY_CH3_SET;
#endif
#else
        case 1:  return BOARD_PIN_RELAY_CH1;
        case 2:  return BOARD_PIN_RELAY_CH2;
#endif
        default: return GPIO_NUM_NC;
    }
}

#if (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL)
static gpio_num_t get_relay_reset_pin(uint8_t channel) {
    switch (channel) {
        case 1:  return BOARD_PIN_RELAY_CH1_RESET;
        case 2:  return BOARD_PIN_RELAY_CH2_RESET;
#if BOARD_RELAY_CHANNEL_COUNT >= 3
        case 3:  return BOARD_PIN_RELAY_CH3_RESET;
#endif
        default: return GPIO_NUM_NC;
    }
}

static esp_timer_handle_t s_pulse_timer = nullptr;
static SemaphoreHandle_t s_pulse_done = nullptr;
static gpio_num_t s_pulse_pin = GPIO_NUM_NC;
static esp_err_t s_pulse_result = ESP_OK;
static portMUX_TYPE s_pulse_start_lock = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR end_latch_pulse(void*) {
    s_pulse_result = gpio_set_level(s_pulse_pin, !BOARD_RELAY_ACTIVE_LEVEL);
#if CONFIG_ESP_TIMER_SUPPORTS_ISR_DISPATCH_METHOD
    BaseType_t woken = pdFALSE;
    xSemaphoreGiveFromISR(s_pulse_done, &woken);
    if (woken) esp_timer_isr_dispatch_need_yield();
#else
    xSemaphoreGive(s_pulse_done);
#endif
}
#endif

static esp_err_t apply_hardware_actuation(uint8_t channel, RelayState state) {
    gpio_num_t pin = get_relay_pin(channel);
    if (pin == GPIO_NUM_NC) {
        return ESP_ERR_INVALID_ARG;
    }

#if (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_MONOSTABLE)
    int level = (state == RELAY_STATE_ON) ? BOARD_RELAY_ACTIVE_LEVEL : (!BOARD_RELAY_ACTIVE_LEVEL);
    ESP_LOGD(TAG, "Monostable Ch%u: GPIO %d set to level %d", channel, pin, level);
    return gpio_set_level(pin, level);

#elif (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL)
    gpio_num_t reset_pin = get_relay_reset_pin(channel);
    if (reset_pin == GPIO_NUM_NC) {
        return ESP_ERR_INVALID_ARG;
    }

    // All callers hold the relay mutex (or are single-threaded during init).
    esp_err_t err = gpio_set_level(pin, !BOARD_RELAY_ACTIVE_LEVEL);
    esp_err_t reset_err = gpio_set_level(reset_pin, !BOARD_RELAY_ACTIVE_LEVEL);
    if (err == ESP_OK) err = reset_err;
    s_pulse_pin = state == RELAY_STATE_ON ? pin : reset_pin;
    if (err == ESP_OK) {
        // Do not allow task preemption between energizing the coil and arming
        // its cutoff. Neither API blocks; the critical section is brief.
        portENTER_CRITICAL(&s_pulse_start_lock);
        err = gpio_set_level(s_pulse_pin, BOARD_RELAY_ACTIVE_LEVEL);
        if (err == ESP_OK) err = esp_timer_start_once(s_pulse_timer, BOARD_RELAY_LATCH_PULSE_MS * 1000ULL);
        if (err != ESP_OK) gpio_set_level(s_pulse_pin, !BOARD_RELAY_ACTIVE_LEVEL);
        portEXIT_CRITICAL(&s_pulse_start_lock);
    }
    if (err == ESP_OK) {
        // Timer lowers the gate independently of the calling task's scheduling.
        xSemaphoreTake(s_pulse_done, portMAX_DELAY);
        err = s_pulse_result;
    }
    if (err != ESP_OK) {
        gpio_set_level(pin, !BOARD_RELAY_ACTIVE_LEVEL);
        gpio_set_level(reset_pin, !BOARD_RELAY_ACTIVE_LEVEL);
        s_channels[ch_idx(channel)].current_state = RELAY_STATE_UNKNOWN;
        s_channels[ch_idx(channel)].fault_state = RELAY_FAULT_HARDWARE;
    }
    return err;
#endif

    return ESP_OK;
}

esp_err_t relay_driver_init(void) {
    if (s_relay_mutex) return ESP_ERR_INVALID_STATE;
    ESP_LOGI(TAG, "Initializing Relay Driver (Channels: %d, Type: %s)...", 
             BOARD_RELAY_CHANNEL_COUNT,
             (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_MONOSTABLE) ? "Monostable" : "Latching");

    s_relay_mutex = xSemaphoreCreateMutex();
    if (!s_relay_mutex) {
        ESP_LOGE(TAG, "Failed to create relay mutex!");
        return ESP_ERR_NO_MEM;
    }

    gpio_config_t io_conf = {};
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    io_conf.intr_type = GPIO_INTR_DISABLE;

    uint64_t pin_mask = 0;
    for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ++ch) {
        gpio_num_t pin = get_relay_pin(ch);
        pin_mask |= (1ULL << pin);
        ESP_ERROR_CHECK(gpio_set_level(pin, !BOARD_RELAY_ACTIVE_LEVEL));
#if (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL)
        gpio_num_t reset = get_relay_reset_pin(ch);
        pin_mask |= (1ULL << reset);
        ESP_ERROR_CHECK(gpio_set_level(reset, !BOARD_RELAY_ACTIVE_LEVEL));
#endif
    }

    io_conf.pin_bit_mask = pin_mask;
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GPIO config failed: %s", esp_err_to_name(err));
        return err;
    }

#if (BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL)
    s_pulse_done = xSemaphoreCreateBinary();
    if (!s_pulse_done) return ESP_ERR_NO_MEM;
    esp_timer_create_args_t timer = {};
    timer.callback = end_latch_pulse;
    timer.name = "relay_pulse";
#if CONFIG_ESP_TIMER_SUPPORTS_ISR_DISPATCH_METHOD
    timer.dispatch_method = ESP_TIMER_ISR;
#endif
    err = esp_timer_create(&timer, &s_pulse_timer);
    if (err != ESP_OK) return err;
#endif

    /* Set default safe state (OFF) */
    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        uint8_t ch = i + 1;
        s_channels[i].channel_id = ch;
        s_channels[i].current_state = RELAY_STATE_OFF;
        s_channels[i].target_state = RELAY_STATE_OFF;
        s_channels[i].fault_state = RELAY_FAULT_NONE;
        s_channels[i].last_actuated_ms = 0;
        s_channels[i].cycle_count = 0;

        err = apply_hardware_actuation(ch, RELAY_STATE_OFF);
        if (err != ESP_OK) return err;
    }

    ESP_LOGI(TAG, "Relay Driver initialized successfully. Default states set to OFF.");
    return ESP_OK;
}

esp_err_t relay_on(uint8_t channel) {
    const uint32_t generation = s_emergency_generation.load();
    if (!is_valid_channel(channel)) {
        ESP_LOGE(TAG, "relay_on rejected: Invalid channel %u", channel);
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    uint8_t idx = ch_idx(channel);
    if (generation != s_emergency_generation.load() ||
        s_channels[idx].fault_state != RELAY_FAULT_NONE || !safety_sensor_ready(channel)) {
        ESP_LOGW(TAG, "relay_on rejected: Channel %u is in FAULT state (%d)", 
                 channel, s_channels[idx].fault_state);
        xSemaphoreGive(s_relay_mutex);
        return ESP_FAIL;
    }

    if (s_channels[idx].current_state == RELAY_STATE_ON) {
        /* Already ON, idempotent no-op */
        xSemaphoreGive(s_relay_mutex);
        return ESP_OK;
    }

    s_channels[idx].target_state = RELAY_STATE_ON;
    /* Never hold the protection mutex while waiting for the stagger interval. */
    while (true) {
        int64_t remaining_us = SAFETY_RELAY_STAGGER_DELAY_MS * 1000LL -
            (esp_timer_get_time() - s_last_switch_time_us);
        if (remaining_us <= 0) break;
        xSemaphoreGive(s_relay_mutex);
        vTaskDelay(pdMS_TO_TICKS((remaining_us + 999) / 1000) + 1);
        if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
        if (s_channels[idx].target_state != RELAY_STATE_ON ||
            generation != s_emergency_generation.load() ||
            s_channels[idx].fault_state != RELAY_FAULT_NONE || !safety_sensor_ready(channel)) {
            xSemaphoreGive(s_relay_mutex);
            return ESP_FAIL;
        }
        if (s_channels[idx].current_state == RELAY_STATE_ON) {
            xSemaphoreGive(s_relay_mutex);
            return ESP_OK;
        }
    }

    esp_err_t err = apply_hardware_actuation(channel, RELAY_STATE_ON);
    if (err == ESP_OK) {
        s_channels[idx].current_state = RELAY_STATE_ON;
        s_channels[idx].last_actuated_ms = (uint32_t)(esp_timer_get_time() / 1000);
        s_channels[idx].cycle_count++;
        s_last_switch_time_us = esp_timer_get_time();
        ESP_LOGI(TAG, "Relay Ch%u -> ON [Cycle: %lu]", channel, s_channels[idx].cycle_count);
    }

    xSemaphoreGive(s_relay_mutex);
    return err;
}

esp_err_t relay_off(uint8_t channel) {
    if (!is_valid_channel(channel)) {
        ESP_LOGE(TAG, "relay_off rejected: Invalid channel %u", channel);
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    uint8_t idx = ch_idx(channel);

    s_channels[idx].target_state = RELAY_STATE_OFF;
    if (s_channels[idx].current_state == RELAY_STATE_OFF) {
        xSemaphoreGive(s_relay_mutex);
        return ESP_OK;
    }
    esp_err_t err = apply_hardware_actuation(channel, RELAY_STATE_OFF);
    if (err == ESP_OK) {
        s_channels[idx].current_state = RELAY_STATE_OFF;
        s_channels[idx].last_actuated_ms = (uint32_t)(esp_timer_get_time() / 1000);
        s_last_switch_time_us = esp_timer_get_time();
        ESP_LOGI(TAG, "Relay Ch%u -> OFF", channel);
    }

    xSemaphoreGive(s_relay_mutex);
    return err;
}

esp_err_t relay_toggle(uint8_t channel) {
    if (!is_valid_channel(channel)) {
        return ESP_ERR_INVALID_ARG;
    }

    RelayState current = relay_get_state(channel);
    if (current == RELAY_STATE_ON) {
        return relay_off(channel);
    } else {
        return relay_on(channel);
    }
}

RelayState relay_get_state(uint8_t channel) {
    if (!is_valid_channel(channel)) {
        return RELAY_STATE_UNKNOWN;
    }

    RelayState st = RELAY_STATE_UNKNOWN;
    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        st = s_channels[ch_idx(channel)].current_state;
        xSemaphoreGive(s_relay_mutex);
    }
    return st;
}

RelayFault relay_get_fault(uint8_t channel) {
    if (!is_valid_channel(channel)) {
        return RELAY_FAULT_HARDWARE;
    }

    RelayFault fault = RELAY_FAULT_NONE;
    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        fault = s_channels[ch_idx(channel)].fault_state;
        xSemaphoreGive(s_relay_mutex);
    }
    return fault;
}

void relay_set_fault(uint8_t channel, RelayFault fault) {
    if (!is_valid_channel(channel)) {
        return;
    }

    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        uint8_t idx = ch_idx(channel);
        s_channels[idx].fault_state = fault;
        ESP_LOGW(TAG, "Channel %u fault status set to: %d", channel, fault);

        if (fault != RELAY_FAULT_NONE) {
            /* Force relay OFF immediately on fault */
            s_channels[idx].target_state = RELAY_STATE_OFF;
            if (s_channels[idx].current_state != RELAY_STATE_OFF &&
                apply_hardware_actuation(channel, RELAY_STATE_OFF) == ESP_OK) {
                s_channels[idx].current_state = RELAY_STATE_OFF;
            }
        }
        xSemaphoreGive(s_relay_mutex);
    }
}

esp_err_t relay_clear_fault(uint8_t channel) {
    if (!is_valid_channel(channel)) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        uint8_t idx = ch_idx(channel);
        ESP_LOGI(TAG, "Clearing fault on Channel %u (Previous: %d)", channel, s_channels[idx].fault_state);
        s_channels[idx].fault_state = RELAY_FAULT_NONE;
        xSemaphoreGive(s_relay_mutex);
        return ESP_OK;
    }
    return ESP_ERR_TIMEOUT;
}

esp_err_t relay_get_channel_info(uint8_t channel, RelayChannelInfo *out_info) {
    if (!is_valid_channel(channel) || !out_info) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        memcpy(out_info, &s_channels[ch_idx(channel)], sizeof(RelayChannelInfo));
        xSemaphoreGive(s_relay_mutex);
        return ESP_OK;
    }
    return ESP_ERR_TIMEOUT;
}

void relay_emergency_all_off(void) {
    ESP_LOGE(TAG, "EMERGENCY: ALL RELAYS SHUTTING DOWN!");
    ++s_emergency_generation;
    // Task context only: wait for the active pulse before issuing RESET pulses.
    if (s_relay_mutex && xSemaphoreTake(s_relay_mutex, portMAX_DELAY) == pdTRUE) {
        for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
            s_channels[i].target_state = RELAY_STATE_OFF;
            if (apply_hardware_actuation(i + 1, RELAY_STATE_OFF) == ESP_OK) {
                s_channels[i].current_state = RELAY_STATE_OFF;
            }
        }
        xSemaphoreGive(s_relay_mutex);
    }
}
