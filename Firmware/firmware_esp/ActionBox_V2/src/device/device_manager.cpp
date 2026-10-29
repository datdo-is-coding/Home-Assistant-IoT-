#include "device_manager.h"
#include "relay_driver.h"
#include "bl0942.h"
#include "button_driver.h"
#include "led_driver.h"
#include "safety_supervisor.h"
#include "nvs_storage.h"
#include "espnow_transport.h"
#include "app_config.h"
#include "voice_capture.h"
#include "hc_runtime.h"
#include "device_reset.h"

#include <string.h>
#include <stdio.h>
#include <atomic>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "DEV_MGR";

static std::atomic<uint8_t> s_armed_kind{static_cast<uint8_t>(ArmedKind::NONE)};
static std::atomic<uint64_t> s_armed_at_ms{0};

bool device_manager_is_claimed(void) {
    return nvs_storage_is_claimed();
}

ArmedKind device_manager_get_armed_kind(void) {
    uint8_t kind_val = s_armed_kind.load();
    if (kind_val != static_cast<uint8_t>(ArmedKind::NONE)) {
        uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
        uint64_t armed_ms = s_armed_at_ms.load();
        if (is_armed_timed_out(now_ms, armed_ms, 5000)) {
            ESP_LOGW(TAG, "Armed reset TIMED OUT after 5s -> cancelled");
            s_armed_kind.store(static_cast<uint8_t>(ArmedKind::NONE));
            s_armed_at_ms.store(0);
            return ArmedKind::NONE;
        }
    }
    return static_cast<ArmedKind>(kind_val);
}

esp_err_t device_manager_init(void) {
    ESP_LOGI(TAG, "Initializing Device Manager Coordinator...");

    button_register_callback(device_manager_on_button_event, NULL);

    safety_register_fault_callback(device_manager_on_fault_alert);

    device_manager_update_leds();

    ESP_LOGI(TAG, "Device Manager initialized.");
    return ESP_OK;
}

void device_manager_update_leds(void) {
    // LED2 is dedicated strictly to voice capture (managed by voice_capture module).
    // Do NOT overwrite LED2 with relay states or faults.
    // LED1 is updated by task_manager telemetry loop based on lifecycle, faults, and armed reset.
}

esp_err_t device_manager_execute_command(const ActionBoxCommand *cmd, ActionBoxResponse *out_resp) {
    if (!cmd || !out_resp) return ESP_ERR_INVALID_ARG;

    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    memset(out_resp, 0, sizeof(ActionBoxResponse));
    out_resp->version = cmd->version;
    strncpy(out_resp->node_id, cfg->node_id, sizeof(out_resp->node_id) - 1);
    out_resp->request_id = cmd->request_id;
    out_resp->session_id = cmd->session_id;
    out_resp->channel = cmd->channel;

    if (is_reset_locked()) {
        out_resp->success = false;
        strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
        strncpy(out_resp->state, "RESET_LOCKED", sizeof(out_resp->state) - 1);
        snprintf(out_resp->error_msg, sizeof(out_resp->error_msg), "Reset in progress");
        return ESP_ERR_INVALID_STATE;
    }

    char err_buf[48] = {0};
    if (!safety_validate_command(cmd, err_buf, sizeof(err_buf))) {
        out_resp->success = false;
        strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
        strncpy(out_resp->state, "FAULT", sizeof(out_resp->state) - 1);
        strncpy(out_resp->error_msg, err_buf, sizeof(out_resp->error_msg) - 1);
        return ESP_FAIL;
    }

    esp_err_t exec_err = ESP_OK;

    switch (cmd->cmd) {
        case CMD_TYPE_LISTEN_FOLLOWUP:
            out_resp->success = voice_capture_request_followup();
            strncpy(out_resp->status, out_resp->success ? "OK" : "ERROR", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, out_resp->success ? "LISTENING" : "IDLE", sizeof(out_resp->state) - 1);
            return out_resp->success ? ESP_OK : ESP_ERR_INVALID_STATE;
        case CMD_TYPE_TURN_ON: {
            exec_err = relay_on(cmd->channel);
            if (exec_err == ESP_OK) {
                out_resp->success = true;
                strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
                strncpy(out_resp->state, "ON", sizeof(out_resp->state) - 1);
                nvs_storage_record_relay_state(cmd->channel, RELAY_STATE_ON);
            } else {
                out_resp->success = false;
                strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
                strncpy(out_resp->state, "FAULT", sizeof(out_resp->state) - 1);
                snprintf(out_resp->error_msg, sizeof(out_resp->error_msg), "Actuation failed");
            }
            break;
        }

        case CMD_TYPE_TURN_OFF: {
            exec_err = relay_off(cmd->channel);
            if (exec_err == ESP_OK) {
                out_resp->success = true;
                strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
                strncpy(out_resp->state, "OFF", sizeof(out_resp->state) - 1);
                nvs_storage_record_relay_state(cmd->channel, RELAY_STATE_OFF);
            } else {
                out_resp->success = false;
                strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
                strncpy(out_resp->state, "FAULT", sizeof(out_resp->state) - 1);
                snprintf(out_resp->error_msg, sizeof(out_resp->error_msg), "Actuation failed");
            }
            break;
        }

        case CMD_TYPE_TOGGLE: {
            out_resp->success = false;
            strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, "REJECTED", sizeof(out_resp->state) - 1);
            snprintf(out_resp->error_msg, sizeof(out_resp->error_msg), "Network TOGGLE rejected");
            exec_err = ESP_ERR_NOT_SUPPORTED;
            break;
        }

        case CMD_TYPE_GET_STATE: {
            RelayState st = relay_get_state(cmd->channel);
            RelayFault flt = relay_get_fault(cmd->channel);
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            if (flt != RELAY_FAULT_NONE) {
                strncpy(out_resp->state, "FAULT", sizeof(out_resp->state) - 1);
            } else {
                strncpy(out_resp->state, (st == RELAY_STATE_ON) ? "ON" : "OFF", sizeof(out_resp->state) - 1);
            }
            break;
        }

        case CMD_TYPE_GET_CURRENT: {
            CurrentMeasurement meas{};
            if (bl0942_read_channel(cmd->channel, &meas) != ESP_OK || meas.validity != SENSOR_STATUS_VALID) {
                out_resp->success = false;
                strcpy(out_resp->status, "ERROR");
                strcpy(out_resp->error_msg, "Sensor unavailable");
                break;
            }
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            RelayState st = relay_get_state(cmd->channel);
            strncpy(out_resp->state, (st == RELAY_STATE_ON) ? "ON" : "OFF", sizeof(out_resp->state) - 1);
            out_resp->current_ma = meas.current_rms_ma;
            out_resp->voltage_v  = meas.voltage_rms_v;
            break;
        }

        case CMD_TYPE_GET_POWER: {
            CurrentMeasurement meas{};
            if (bl0942_read_channel(cmd->channel, &meas) != ESP_OK || meas.validity != SENSOR_STATUS_VALID) {
                out_resp->success = false;
                strcpy(out_resp->status, "ERROR");
                strcpy(out_resp->error_msg, "Sensor unavailable");
                break;
            }
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            RelayState st = relay_get_state(cmd->channel);
            strncpy(out_resp->state, (st == RELAY_STATE_ON) ? "ON" : "OFF", sizeof(out_resp->state) - 1);
            out_resp->current_ma = meas.current_rms_ma;
            out_resp->voltage_v  = meas.voltage_rms_v;
            out_resp->power_w    = meas.active_power_w;
            break;
        }

        case CMD_TYPE_CLEAR_FAULT: {
            relay_clear_fault(cmd->channel);
            RelayState st = relay_get_state(cmd->channel);
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, (st == RELAY_STATE_ON) ? "ON" : "OFF", sizeof(out_resp->state) - 1);
            ESP_LOGI(TAG, "Fault cleared on Ch%u by SubBox command", cmd->channel);
            break;
        }

        case CMD_TYPE_PING: {
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, "PONG", sizeof(out_resp->state) - 1);
            break;
        }

        case CMD_TYPE_SET_CONFIG: {
            ActionBoxPersistentConfig new_cfg = *cfg;
            if (strlen(cmd->new_node_id) > 0) {
                strncpy(new_cfg.node_id, cmd->new_node_id, sizeof(new_cfg.node_id) - 1);
            }
            if (strlen(cmd->new_room_id) > 0) {
                strncpy(new_cfg.room_id, cmd->new_room_id, sizeof(new_cfg.room_id) - 1);
            }
            if (cmd->max_current_ma > 0 && cmd->channel >= 1 && cmd->channel <= BOARD_RELAY_CHANNEL_COUNT) {
                new_cfg.max_current_ma[cmd->channel - 1] = cmd->max_current_ma;
            }

            nvs_storage_save_config(&new_cfg);
            out_resp->success = true;
            strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, "CONFIG_SAVED", sizeof(out_resp->state) - 1);
            strncpy(out_resp->node_id, new_cfg.node_id, sizeof(out_resp->node_id) - 1);
            break;
        }

        default: {
            out_resp->success = false;
            strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
            strncpy(out_resp->state, "UNKNOWN_CMD", sizeof(out_resp->state) - 1);
            snprintf(out_resp->error_msg, sizeof(out_resp->error_msg), "Unknown command");
            break;
        }
    }

    return exec_err;
}

void device_manager_on_button_event(uint8_t channel, ButtonAction action, void *user_data) {
    if (is_reset_locked()) {
        ESP_LOGW(TAG, "Button event ignored: Reset in progress or locked");
        return;
    }

    if (channel < 1 || channel > BOARD_BUTTON_COUNT) return;

    if (channel == 2) {
        if (action == ButtonAction::SHORT_PRESS) {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch2: Toggling relay 2");
            relay_toggle(2);
            RelayState new_st = relay_get_state(2);
            nvs_storage_record_relay_state(2, new_st);
        } else if (action == ButtonAction::VOICE_TRIGGER) {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch2: Held >= 700ms -> Triggering Voice Streaming");
            voice_capture_start_streaming(WAKE_TRIGGER_BUTTON);
        }
        return;
    }

    // channel == 1 (BUT1): Admin gestures & relay 1
    switch (action) {
        case ButtonAction::SHORT_PRESS: {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch1: Toggling relay 1");
            relay_toggle(1);
            RelayState new_st = relay_get_state(1);
            nvs_storage_record_relay_state(1, new_st);
            break;
        }

        case ButtonAction::REBOOT: {
            ESP_LOGW(TAG, "LOCAL BUTTON Ch1: Admin gesture REBOOT -> Triggering confirmed reboot sequence");
            execute_confirmed_reset(ResetKind::REBOOT, "local_button_reboot");
            break;
        }

        case ButtonAction::START_SETUP: {
            if (hc_runtime_enabled()) {
                ESP_LOGW(TAG, "Secure node: use protected BOOT provisioning; legacy pairing is disabled");
                break;
            }
            espnow_transport_set_pairing_mode(true);
            ESP_LOGI(TAG, "LOCAL BUTTON Ch1: Admin gesture START_SETUP -> 180s setup window open");
            led_set_pattern(1, ::LedPattern::CLAIMING);
            break;
        }

        case ButtonAction::ARM_NETWORK_RESET: {
            ESP_LOGW(TAG, "LOCAL BUTTON Ch1: Admin gesture ARM_NETWORK_RESET -> Confirm with short press within 5s");
            prepare_reset(ResetKind::NETWORK_RESET, "local_button_network_reset", nvs_storage_get_owner_epoch());
            s_armed_kind.store(static_cast<uint8_t>(ArmedKind::NETWORK_RESET));
            s_armed_at_ms.store((uint64_t)(esp_timer_get_time() / 1000));
            led_set_pattern(1, ::LedPattern::AWAITING_NETWORK_RESET);
            break;
        }

        case ButtonAction::ARM_FACTORY_RESET: {
            ESP_LOGW(TAG, "LOCAL BUTTON Ch1: Admin gesture ARM_FACTORY_RESET -> Confirm with short press within 5s");
            prepare_reset(ResetKind::FACTORY_RESET, "local_button_factory_reset", nvs_storage_get_owner_epoch());
            s_armed_kind.store(static_cast<uint8_t>(ArmedKind::FACTORY_RESET));
            s_armed_at_ms.store((uint64_t)(esp_timer_get_time() / 1000));
            led_set_pattern(1, ::LedPattern::AWAITING_FACTORY_RESET);
            break;
        }

        case ButtonAction::CONFIRM_RESET: {
            // CRITICAL: DO NOT call relay_toggle!
            uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
            uint64_t armed_ms = s_armed_at_ms.load();
            if (is_armed_timed_out(now_ms, armed_ms, 5000)) {
                ESP_LOGW(TAG, "LOCAL BUTTON Ch1: Reset confirmation TIMED OUT -> cancelled (destructive action = 0)");
                s_armed_kind.store(static_cast<uint8_t>(ArmedKind::NONE));
                s_armed_at_ms.store(0);
                cancel_armed_reset();
                led_set_pattern(1, LED_PATTERN_OFF);
                break;
            }

            ArmedKind confirmed_kind = static_cast<ArmedKind>(s_armed_kind.exchange(static_cast<uint8_t>(ArmedKind::NONE)));
            s_armed_at_ms.store(0);
            led_set_pattern(1, LED_PATTERN_BLINK_FAST);

            if (confirmed_kind == ArmedKind::FACTORY_RESET) {
                ESP_LOGE(TAG, "LOCAL BUTTON Ch1: CONFIRMED FACTORY RESET! Executing safe reset...");
                execute_confirmed_reset(ResetKind::FACTORY_RESET, "local_button_factory_reset");
            } else if (confirmed_kind == ArmedKind::NETWORK_RESET) {
                ESP_LOGW(TAG, "LOCAL BUTTON Ch1: CONFIRMED NETWORK RESET! Executing safe reset...");
                execute_confirmed_reset(ResetKind::NETWORK_RESET, "local_button_network_reset");
            }
            break;
        }

        case ButtonAction::CANCEL_ARMED: {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch1: CANCEL_ARMED gesture received -> Reset cancelled");
            s_armed_kind.store(static_cast<uint8_t>(ArmedKind::NONE));
            s_armed_at_ms.store(0);
            led_set_pattern(1, LED_PATTERN_OFF);
            break;
        }

        case ButtonAction::NONE:
        default:
            break;
    }
}

void device_manager_on_fault_alert(uint8_t channel, RelayFault fault, uint32_t current_ma) {
    ESP_LOGE(TAG, "EMERGENCY FAULT CALLBACK: Ch%u, Fault: %d, Current: %lu mA", channel, fault, current_ma);

    char alert_json[APP_FAULT_ALERT_BUFFER_SIZE];
    esp_err_t err = protocol_serialize_fault_alert(channel, fault, current_ma, alert_json, sizeof(alert_json));
    if (err == ESP_OK) {

        espnow_transport_send((const uint8_t*)alert_json, strlen(alert_json));
        ESP_LOGI(TAG, "Urgent fault packet dispatched to network: %s", alert_json);
    }
}
