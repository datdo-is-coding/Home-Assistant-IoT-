/**
 * @file safety_supervisor.cpp
 * @brief Independent Local Safety Supervisor Implementation
 */

#include "safety_supervisor.h"
#include "board_pins.h"
#include "app_config.h"
#include "relay_driver.h"
#include "led_driver.h"
#include "nvs_storage.h"
#include "bl0942.h"
#include <atomic>

#include <string.h>
#include <stdio.h>
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "SAFETY";

typedef struct {
    int64_t  overcurrent_start_us;
    bool     overcurrent_active;
    uint32_t peak_current_ma;
} SafetyChannelState;

static SafetyChannelState s_ch_state[BOARD_RELAY_CHANNEL_COUNT];
static fault_alert_cb_t s_fault_callback = NULL;
static std::atomic<int64_t> s_last_network_heartbeat_us(0);
static bool s_safety_initialized = false;
static std::atomic<uint32_t> s_last_sample_ms[BOARD_RELAY_CHANNEL_COUNT];
static std::atomic<bool> s_sample_seen[BOARD_RELAY_CHANNEL_COUNT];

bool safety_sensor_ready(uint8_t channel) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT) return false;
    const uint8_t idx = channel - 1;
    return s_sample_seen[idx].load() &&
        uint32_t(esp_timer_get_time() / 1000 - s_last_sample_ms[idx].load()) < SAFETY_SENSOR_TIMEOUT_MS;
}

void safety_check_sensor_timeouts(void) {
    for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ++ch) {
        if (!safety_sensor_ready(ch) && relay_get_state(ch) == RELAY_STATE_ON) {
            relay_set_fault(ch, RELAY_FAULT_HARDWARE);
            if (ch != 1) led_set_pattern(ch, LED_PATTERN_BLINK_FAST);
            if (s_fault_callback) s_fault_callback(ch, RELAY_FAULT_HARDWARE, 0);
        }
    }
}

esp_err_t safety_supervisor_init(void) {
    ESP_LOGI(TAG, "Initializing Safety Supervisor Layer...");

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        s_ch_state[i].overcurrent_start_us = 0;
        s_ch_state[i].overcurrent_active = false;
        s_ch_state[i].peak_current_ma = 0;
    }

    /* Start in timed out state until first packet from SubBox */
    s_last_network_heartbeat_us = 0;

    /* Configure Task Watchdog Timer */
#if defined(CONFIG_ESP_TASK_WDT_EN)
    esp_task_wdt_config_t twdt_config = {
        .timeout_ms = SAFETY_WATCHDOG_TIMEOUT_MS,
        .idle_core_mask = (1 << 0) | (1 << 1),
        .trigger_panic = true,
    };
    esp_err_t twdt_err = esp_task_wdt_reconfigure(&twdt_config);
    if (twdt_err != ESP_OK) {
        esp_task_wdt_init(&twdt_config);
    }
    ESP_LOGI(TAG, "Task Watchdog Timer configured (Timeout: %d ms)", SAFETY_WATCHDOG_TIMEOUT_MS);
#endif

    s_safety_initialized = true;
    ESP_LOGI(TAG, "Safety Supervisor initialized successfully.");
    return ESP_OK;
}

void safety_register_fault_callback(fault_alert_cb_t cb) {
    s_fault_callback = cb;
}

void safety_process_measurement(uint8_t channel, const CurrentMeasurement *meas) {
    if (!s_safety_initialized || channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT || !meas) {
        return;
    }
    if (meas->validity != SENSOR_STATUS_VALID) return;

    uint8_t idx = channel - 1;
    s_last_sample_ms[idx].store(meas->timestamp_ms);
    s_sample_seen[idx].store(true);
    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    uint32_t limit_ma = cfg->max_current_ma[idx];
    int64_t now_us = esp_timer_get_time();

    /* Track peak current */
    if (meas->current_rms_ma > s_ch_state[idx].peak_current_ma) {
        s_ch_state[idx].peak_current_ma = meas->current_rms_ma;
    }

    /* 1. Hard Ceiling Instant Trip: Cut off immediately */
    if (meas->current_rms_ma >= SAFETY_ABSOLUTE_MAX_CURRENT_MA) {
        ESP_LOGE(TAG, "EMERGENCY HARD CEILING TRIP! Ch%u current %lu mA >= %d mA!",
                 channel, meas->current_rms_ma, SAFETY_ABSOLUTE_MAX_CURRENT_MA);

        relay_set_fault(channel, RELAY_FAULT_OVERCURRENT);
        if (channel != 1) led_set_pattern(channel, LED_PATTERN_BLINK_FAST);

        if (s_fault_callback) {
            s_fault_callback(channel, RELAY_FAULT_OVERCURRENT, meas->current_rms_ma);
        }
        s_ch_state[idx].overcurrent_active = false;
        return;
    }

    /* 2. Sustained Overcurrent Trip (with inrush debounce) */
    if (meas->current_rms_ma >= limit_ma) {
        if (!s_ch_state[idx].overcurrent_active) {
            s_ch_state[idx].overcurrent_active = true;
            s_ch_state[idx].overcurrent_start_us = now_us;
            ESP_LOGW(TAG, "Ch%u current above limit (%lu mA >= %lu mA). Monitoring inrush...",
                     channel, meas->current_rms_ma, limit_ma);
        } else {
            int64_t elapsed_ms = (now_us - s_ch_state[idx].overcurrent_start_us) / 1000;
            if (elapsed_ms >= SAFETY_OVERCURRENT_PERSIST_MS) {
                ESP_LOGE(TAG, "OVERCURRENT TRIP EXCEEDED! Ch%u sustained %lld ms (%lu mA). TRIP RELAY!",
                         channel, elapsed_ms, meas->current_rms_ma);

                /* Trip relay immediately */
                relay_set_fault(channel, RELAY_FAULT_OVERCURRENT);
                if (channel != 1) led_set_pattern(channel, LED_PATTERN_BLINK_FAST);

                if (s_fault_callback) {
                    s_fault_callback(channel, RELAY_FAULT_OVERCURRENT, meas->current_rms_ma);
                }
                s_ch_state[idx].overcurrent_active = false;
            }
        }
    } else {
        /* Normal operating current */
        s_ch_state[idx].overcurrent_active = false;
    }
}

bool safety_validate_command(const ActionBoxCommand *cmd, char *out_err_msg, size_t max_err_len) {
    if (!cmd) {
        if (out_err_msg) snprintf(out_err_msg, max_err_len, "Null command");
        return false;
    }

    /* Check channel boundary for channel-specific commands */
    if (cmd->cmd == CMD_TYPE_TURN_ON || cmd->cmd == CMD_TYPE_TURN_OFF || 
        cmd->cmd == CMD_TYPE_TOGGLE || cmd->cmd == CMD_TYPE_CLEAR_FAULT ||
        cmd->cmd == CMD_TYPE_GET_STATE || cmd->cmd == CMD_TYPE_GET_CURRENT || cmd->cmd == CMD_TYPE_GET_POWER) {
        
        if (cmd->channel < 1 || cmd->channel > BOARD_RELAY_CHANNEL_COUNT) {
            ESP_LOGW(TAG, "Rejected: Invalid channel %u", cmd->channel);
            if (out_err_msg) snprintf(out_err_msg, max_err_len, "Invalid channel %u", cmd->channel);
            return false;
        }
    }

    /* Check channel fault state */
    if (cmd->cmd == CMD_TYPE_TURN_ON || cmd->cmd == CMD_TYPE_TOGGLE) {
        RelayFault flt = relay_get_fault(cmd->channel);
        if (flt != RELAY_FAULT_NONE) {
            ESP_LOGW(TAG, "Rejected: Channel %u is in FAULT state (%d)", cmd->channel, flt);
            if (out_err_msg) snprintf(out_err_msg, max_err_len, "Channel in FAULT state (%d)", flt);
            return false;
        }
    }

    return true;
}

void safety_feed_network_watchdog(void) {
    s_last_network_heartbeat_us.store(esp_timer_get_time());
}

bool safety_is_network_timed_out(void) {
    int64_t last = s_last_network_heartbeat_us.load();
    if (last == 0) return true;
    int64_t elapsed_ms = (esp_timer_get_time() - last) / 1000;
    return (elapsed_ms >= SAFETY_COMMS_TIMEOUT_MS);
}

esp_err_t safety_register_calling_task_wdt(void) {
#if defined(CONFIG_ESP_TASK_WDT_EN)
    esp_err_t err = esp_task_wdt_add(NULL);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Task '%s' registered to Task Watchdog", pcTaskGetName(NULL));
    }
    return err;
#else
    return ESP_OK;
#endif
}

void safety_feed_task_watchdog(void) {
#if defined(CONFIG_ESP_TASK_WDT_EN)
    esp_task_wdt_reset();
#endif
}

void safety_apply_startup_state(void) {
    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    ESP_LOGI(TAG, "Applying safe startup states to relays...");

    for (uint8_t i = 0; i < BOARD_RELAY_CHANNEL_COUNT; i++) {
        uint8_t ch = i + 1;
        CurrentMeasurement sample{};
        if (bl0942_read_channel(ch, &sample) == ESP_OK) safety_process_measurement(ch, &sample);
        StartupMode mode = cfg->startup_modes[i];

        switch (mode) {
            case STARTUP_MODE_ALWAYS_ON:
                ESP_LOGI(TAG, "Ch%u startup policy: ALWAYS_ON", ch);
                relay_on(ch);
                if (ch != 1) led_set_pattern(ch, relay_get_state(ch) == RELAY_STATE_ON ? LED_PATTERN_ON : LED_PATTERN_OFF);
                break;

            case STARTUP_MODE_RESTORE_LAST:
                if (cfg->last_states[i] == RELAY_STATE_ON) {
                    ESP_LOGI(TAG, "Ch%u startup policy: RESTORE_LAST (Previous: ON)", ch);
                    relay_on(ch);
                    if (ch != 1) led_set_pattern(ch, relay_get_state(ch) == RELAY_STATE_ON ? LED_PATTERN_ON : LED_PATTERN_OFF);
                } else {
                    ESP_LOGI(TAG, "Ch%u startup policy: RESTORE_LAST (Previous: OFF)", ch);
                    relay_off(ch);
                    if (ch != 1) led_set_pattern(ch, LED_PATTERN_OFF);
                }
                break;

            case STARTUP_MODE_ALWAYS_OFF:
            default:
                ESP_LOGI(TAG, "Ch%u startup policy: ALWAYS_OFF", ch);
                relay_off(ch);
                if (ch != 1) led_set_pattern(ch, LED_PATTERN_OFF);
                break;
        }
    }
}
