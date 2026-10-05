/**
 * @file device_manager.cpp
 * @brief High-Level Device Coordination Implementation
 */

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

#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "DEV_MGR";

esp_err_t device_manager_init(void) {
    ESP_LOGI(TAG, "Initializing Device Manager Coordinator...");

    /* Register callback from local physical buttons */
    button_register_callback(device_manager_on_button_event, NULL);

    /* Register callback from safety supervisor */
    safety_register_fault_callback(device_manager_on_fault_alert);

    /* Sync initial LED states with relay states */
    device_manager_update_leds();

    ESP_LOGI(TAG, "Device Manager initialized.");
    return ESP_OK;
}

void device_manager_update_leds(void) {
    for (uint8_t ch = 1; ch <= BOARD_RELAY_CHANNEL_COUNT; ch++) {
        if (ch == 1) continue; /* LED1 is dedicated to System Connection Status & Faults */
        RelayFault flt = relay_get_fault(ch);
        if (flt != RELAY_FAULT_NONE) {
            led_set_pattern(ch, LED_PATTERN_BLINK_FAST);
        } else {
            RelayState st = relay_get_state(ch);
            led_set_pattern(ch, (st == RELAY_STATE_ON) ? LED_PATTERN_ON : LED_PATTERN_OFF);
        }
    }
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

    /* 1. Safety validation check */
    char err_buf[48] = {0};
    if (!safety_validate_command(cmd, err_buf, sizeof(err_buf))) {
        out_resp->success = false;
        strncpy(out_resp->status, "ERROR", sizeof(out_resp->status) - 1);
        strncpy(out_resp->state, "FAULT", sizeof(out_resp->state) - 1);
        strncpy(out_resp->error_msg, err_buf, sizeof(out_resp->error_msg) - 1);
        return ESP_FAIL;
    }

    /* 2. Execute command */
    esp_err_t exec_err = ESP_OK;

    switch (cmd->cmd) {
        case CMD_TYPE_TURN_ON: {
            exec_err = relay_on(cmd->channel);
            if (exec_err == ESP_OK) {
                out_resp->success = true;
                strncpy(out_resp->status, "OK", sizeof(out_resp->status) - 1);
                strncpy(out_resp->state, "ON", sizeof(out_resp->state) - 1);
                nvs_storage_record_relay_state(cmd->channel, RELAY_STATE_ON);
                if (cmd->channel != 1) led_set_pattern(cmd->channel, LED_PATTERN_ON);
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
                if (cmd->channel != 1) led_set_pattern(cmd->channel, LED_PATTERN_OFF);
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
            if (cmd->channel != 1) led_set_pattern(cmd->channel, (st == RELAY_STATE_ON) ? LED_PATTERN_ON : LED_PATTERN_OFF);
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

void device_manager_on_button_event(uint8_t channel, ButtonEvent event, void *user_data) {
    if (channel < 1 || channel > BOARD_RELAY_CHANNEL_COUNT) return;

    switch (event) {
        case BUTTON_EVENT_SHORT_PRESS: {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch%u: Toggling relay (offline operation)", channel);
            relay_toggle(channel);
            RelayState new_st = relay_get_state(channel);
            nvs_storage_record_relay_state(channel, new_st);
            device_manager_update_leds();
            break;
        }

        case BUTTON_EVENT_LONG_PRESS: {
            ESP_LOGI(TAG, "LOCAL BUTTON Ch%u: Long press (1.2s) -> Push-To-Talk Voice Trigger", channel);
            voice_capture_start_streaming(2); /* Trigger 2 = Manual Push-to-Talk */
            break;
        }

        case BUTTON_EVENT_FACTORY_RST: {
            ESP_LOGW(TAG, "LOCAL BUTTON Ch%u: Held 10s -> RESTORING FACTORY SETTINGS!", channel);
            led_set_pattern(1, LED_PATTERN_BLINK_FAST);
            led_set_pattern(2, LED_PATTERN_BLINK_FAST);
            nvs_storage_factory_reset(NULL);
            break;
        }

        default:
            break;
    }
}

void device_manager_on_fault_alert(uint8_t channel, RelayFault fault, uint32_t current_ma) {
    ESP_LOGE(TAG, "EMERGENCY FAULT CALLBACK: Ch%u, Fault: %d, Current: %lu mA", channel, fault, current_ma);

    char alert_json[256];
    esp_err_t err = protocol_serialize_fault_alert(channel, fault, current_ma, alert_json, sizeof(alert_json));
    if (err == ESP_OK) {
        /* Immediately transmit urgent fault packet over ESP-NOW */
        espnow_transport_send((const uint8_t*)alert_json, strlen(alert_json));
        ESP_LOGI(TAG, "Urgent fault packet dispatched to network: %s", alert_json);
    }
}
