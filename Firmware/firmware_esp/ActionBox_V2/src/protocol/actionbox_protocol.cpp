/**
 * @file actionbox_protocol.cpp
 * @brief Idempotent JSON Protocol Implementation using cJSON
 */

#include "actionbox_protocol.h"
#include "app_config.h"
#include "nvs_storage.h"
#include "relay_driver.h"
#include "bl0942.h"

#include <string.h>
#include <stdio.h>
#include "cJSON.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "PROTOCOL";

#define IDEMPOTENCY_CACHE_SIZE 32
#define MAX_RESPONSE_CACHE_LEN 768
static char s_hardware_uid[13];
static uint32_t s_boot_id;

const char* protocol_get_hardware_uid(void) { return s_hardware_uid; }

static void add_identity(cJSON* root) {
    cJSON_AddNumberToObject(root, "protocol_version", APP_PROTOCOL_VERSION);
    cJSON_AddStringToObject(root, "hardware_uid", s_hardware_uid);
    cJSON_AddNumberToObject(root, "config_version", nvs_storage_get_cached_config()->config_version);
    cJSON_AddNumberToObject(root, "boot_id", s_boot_id);
}

typedef struct {
    uint32_t request_id;
    uint32_t session_id;
    char     response_json[MAX_RESPONSE_CACHE_LEN];
    bool     valid;
} IdempotencyRecord;

static IdempotencyRecord s_idempotency_cache[IDEMPOTENCY_CACHE_SIZE];
static uint8_t s_cache_head = 0;
static SemaphoreHandle_t s_cache_mutex = NULL;

void protocol_init(void) {
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    snprintf(s_hardware_uid, sizeof(s_hardware_uid), "%02X%02X%02X%02X%02X%02X", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    s_boot_id = esp_random();
    s_cache_mutex = xSemaphoreCreateMutex();
    for (int i = 0; i < IDEMPOTENCY_CACHE_SIZE; i++) {
        s_idempotency_cache[i].valid = false;
        s_idempotency_cache[i].request_id = 0;
        s_idempotency_cache[i].response_json[0] = '\0';
    }
}

static ActionBoxCommandType parse_cmd_type(const char *cmd_str) {
    if (!cmd_str) return CMD_TYPE_UNKNOWN;
    if (strcmp(cmd_str, "TURN_ON") == 0)     return CMD_TYPE_TURN_ON;
    if (strcmp(cmd_str, "TURN_OFF") == 0)    return CMD_TYPE_TURN_OFF;
    if (strcmp(cmd_str, "GET_STATE") == 0)   return CMD_TYPE_GET_STATE;
    if (strcmp(cmd_str, "GET_CURRENT") == 0) return CMD_TYPE_GET_CURRENT;
    if (strcmp(cmd_str, "GET_POWER") == 0)   return CMD_TYPE_GET_POWER;
    if (strcmp(cmd_str, "CLEAR_FAULT") == 0) return CMD_TYPE_CLEAR_FAULT;
    if (strcmp(cmd_str, "PING") == 0)        return CMD_TYPE_PING;
    if (strcmp(cmd_str, "SET_CONFIG") == 0)  return CMD_TYPE_SET_CONFIG;
    return CMD_TYPE_UNKNOWN;
}

static bool is_uint32(const cJSON* value) {
    return cJSON_IsNumber(value) && value->valuedouble >= 0 &&
        value->valuedouble <= UINT32_MAX &&
        value->valuedouble == static_cast<uint32_t>(value->valuedouble);
}

esp_err_t protocol_parse_command(const char *json_str, ActionBoxCommand *out_cmd) {
    if (!json_str || !out_cmd) return ESP_ERR_INVALID_ARG;

    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGW(TAG, "Malformed JSON received: %s", json_str);
        return ESP_ERR_INVALID_ARG;
    }

    memset(out_cmd, 0, sizeof(ActionBoxCommand));

    cJSON *item_ver = cJSON_GetObjectItem(root, "protocol_version");
    if (!item_ver) item_ver = cJSON_GetObjectItem(root, "version");
    cJSON *item_nid = cJSON_GetObjectItem(root, "node_id");
    cJSON *item_rid = cJSON_GetObjectItem(root, "request_id");
    cJSON *item_cmd = cJSON_GetObjectItem(root, "cmd");
    cJSON *item_ch  = cJSON_GetObjectItem(root, "channel");
    cJSON *item_ts  = cJSON_GetObjectItem(root, "timestamp");

    if (!is_uint32(item_ver) || !cJSON_IsString(item_nid) || !is_uint32(item_rid) ||
        !cJSON_IsString(item_cmd) || strlen(item_nid->valuestring) >= sizeof(out_cmd->node_id) ||
        (item_ch && (!is_uint32(item_ch) || item_ch->valuedouble > BOARD_RELAY_CHANNEL_COUNT)) ||
        (item_ts && !is_uint32(item_ts))) {
        ESP_LOGW(TAG, "Missing mandatory protocol fields (version, node_id, request_id, cmd)");
        cJSON_Delete(root);
        return ESP_ERR_INVALID_ARG;
    }

    out_cmd->version = (uint32_t)item_ver->valueint;
    if (out_cmd->version != APP_PROTOCOL_VERSION) {
        ESP_LOGW(TAG, "Unsupported protocol version: %lu (Expected: %d)", 
                 out_cmd->version, APP_PROTOCOL_VERSION);
        cJSON_Delete(root);
        return ESP_ERR_INVALID_VERSION;
    }

    if (item_nid->valuestring) {
        strncpy(out_cmd->node_id, item_nid->valuestring, sizeof(out_cmd->node_id) - 1);
    }

    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    cJSON* uid = cJSON_GetObjectItem(root, "hardware_uid");
    cJSON* revision = cJSON_GetObjectItem(root, "config_version");
    if (!cJSON_IsString(uid) || strcmp(uid->valuestring, s_hardware_uid) != 0 ||
        strcmp(out_cmd->node_id, cfg->node_id) != 0) {
        ESP_LOGD(TAG, "Packet node_id '%s' does not match local node_id '%s'", 
                 out_cmd->node_id, cfg->node_id);
        cJSON_Delete(root);
        return ESP_ERR_NOT_FOUND;
    }

    if (!is_uint32(revision) || revision->valuedouble != cfg->config_version) {
        cJSON_Delete(root);
        return ESP_ERR_INVALID_VERSION;
    }
    out_cmd->request_id = (uint32_t)item_rid->valuedouble;
    cJSON* session = cJSON_GetObjectItem(root, "session_id");
    if (!is_uint32(session) || session->valuedouble == 0 || out_cmd->request_id == 0) {
        cJSON_Delete(root);
        return ESP_ERR_INVALID_ARG;
    }
    out_cmd->session_id = session ? (uint32_t)session->valuedouble : 0;
    out_cmd->cmd = parse_cmd_type(item_cmd->valuestring);
    cJSON* settle = cJSON_GetObjectItem(root, "settle_ms");
    if (out_cmd->cmd == CMD_TYPE_UNKNOWN || (settle && (!is_uint32(settle) || settle->valuedouble < 100 || settle->valuedouble > 10000))) {
        cJSON_Delete(root);
        return ESP_ERR_INVALID_ARG;
    }
    out_cmd->settle_ms = settle ? (uint32_t)settle->valuedouble : 500;
    out_cmd->channel = item_ch ? (uint8_t)item_ch->valueint : 0;
    out_cmd->timestamp = item_ts ? (uint32_t)item_ts->valueint : 0;

    /* Parse optional configuration payloads */
    if (out_cmd->cmd == CMD_TYPE_SET_CONFIG) {
        cJSON *item_new_nid = cJSON_GetObjectItem(root, "new_node_id");
        cJSON *item_new_rid = cJSON_GetObjectItem(root, "new_room_id");
        cJSON *item_max_ma  = cJSON_GetObjectItem(root, "max_current_ma");

        if ((item_new_nid && (!cJSON_IsString(item_new_nid) || !item_new_nid->valuestring[0] || strlen(item_new_nid->valuestring) >= sizeof(out_cmd->new_node_id))) ||
            (item_new_rid && (!cJSON_IsString(item_new_rid) || strlen(item_new_rid->valuestring) >= sizeof(out_cmd->new_room_id))) ||
            (item_max_ma && (!is_uint32(item_max_ma) || item_max_ma->valuedouble < 1 || item_max_ma->valuedouble > SAFETY_ABSOLUTE_MAX_CURRENT_MA))) {
            cJSON_Delete(root); return ESP_ERR_INVALID_ARG;
        }
        if (item_new_nid && item_new_nid->valuestring) {
            strncpy(out_cmd->new_node_id, item_new_nid->valuestring, sizeof(out_cmd->new_node_id) - 1);
        }
        if (item_new_rid && item_new_rid->valuestring) {
            strncpy(out_cmd->new_room_id, item_new_rid->valuestring, sizeof(out_cmd->new_room_id) - 1);
        }
        if (item_max_ma) {
            out_cmd->max_current_ma = (uint32_t)item_max_ma->valueint;
        }
    }

    cJSON_Delete(root);
    return ESP_OK;
}

bool protocol_is_duplicate_request(uint32_t request_id, uint32_t session_id, char *out_cached_json, size_t max_len) {
    if (!s_cache_mutex || request_id == 0) return false;

    bool duplicate = false;
    if (xSemaphoreTake(s_cache_mutex, portMAX_DELAY) == pdTRUE) {
        for (int i = 0; i < IDEMPOTENCY_CACHE_SIZE; i++) {
            if (s_idempotency_cache[i].valid && s_idempotency_cache[i].request_id == request_id && s_idempotency_cache[i].session_id == session_id) {
                duplicate = true;
                if (out_cached_json && max_len > 0) {
                    strncpy(out_cached_json, s_idempotency_cache[i].response_json, max_len - 1);
                    out_cached_json[max_len - 1] = '\0';
                }
                break;
            }
        }
        xSemaphoreGive(s_cache_mutex);
    }
    return duplicate;
}

static void cache_response(uint32_t request_id, uint32_t session_id, const char *json_str) {
    if (!s_cache_mutex || request_id == 0 || !json_str) return;

    if (xSemaphoreTake(s_cache_mutex, portMAX_DELAY) == pdTRUE) {
        s_idempotency_cache[s_cache_head].request_id = request_id;
        s_idempotency_cache[s_cache_head].session_id = session_id;
        strncpy(s_idempotency_cache[s_cache_head].response_json, json_str, MAX_RESPONSE_CACHE_LEN - 1);
        s_idempotency_cache[s_cache_head].response_json[MAX_RESPONSE_CACHE_LEN - 1] = '\0';
        s_idempotency_cache[s_cache_head].valid = true;

        s_cache_head = (s_cache_head + 1) % IDEMPOTENCY_CACHE_SIZE;
        xSemaphoreGive(s_cache_mutex);
    }
}

esp_err_t protocol_serialize_response(const ActionBoxResponse *resp, char *out_json, size_t max_len) {
    if (!resp || !out_json || max_len == 0) return ESP_ERR_INVALID_ARG;

    cJSON *root = cJSON_CreateObject();
    if (!root) return ESP_ERR_NO_MEM;

    add_identity(root);
    cJSON_AddStringToObject(root, "type", "ACK");
    cJSON_AddNumberToObject(root, "version", resp->version);
    cJSON_AddStringToObject(root, "node_id", resp->node_id);
    cJSON_AddNumberToObject(root, "request_id", resp->request_id);
    cJSON_AddNumberToObject(root, "session_id", resp->session_id);
    cJSON_AddStringToObject(root, "status", resp->status);
    cJSON_AddNumberToObject(root, "channel", resp->channel);
    cJSON_AddStringToObject(root, "state", resp->state);

    if (strlen(resp->error_msg) > 0) {
        cJSON_AddStringToObject(root, "error", resp->error_msg);
    }

    if (resp->current_ma > 0) {
        cJSON_AddNumberToObject(root, "current_ma", resp->current_ma);
    }
    if (resp->voltage_v > 0) {
        cJSON_AddNumberToObject(root, "voltage_v", resp->voltage_v);
    }
    if (resp->power_w != 0) {
        cJSON_AddNumberToObject(root, "power_w", resp->power_w);
    }

    cJSON_AddNumberToObject(root, "uptime_s", (uint32_t)(esp_timer_get_time() / 1000000));

    char *rendered = cJSON_PrintUnformatted(root);
    if (!rendered) {
        cJSON_Delete(root);
        return ESP_ERR_NO_MEM;
    }

    if (strlen(rendered) >= max_len) {
        cJSON_free(rendered);
        cJSON_Delete(root);
        return ESP_ERR_INVALID_SIZE;
    }
    strncpy(out_json, rendered, max_len - 1);
    out_json[max_len - 1] = '\0';

    cJSON_free(rendered);
    cJSON_Delete(root);

    /* Record into idempotency cache */
    cache_response(resp->request_id, resp->session_id, out_json);
    return ESP_OK;
}

esp_err_t protocol_serialize_telemetry(char *out_json, size_t max_len) {
    if (!out_json || max_len == 0) return ESP_ERR_INVALID_ARG;

    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    cJSON *root = cJSON_CreateObject();
    if (!root) return ESP_ERR_NO_MEM;

    add_identity(root);
    cJSON_AddNumberToObject(root, "version", APP_PROTOCOL_VERSION);
    cJSON_AddStringToObject(root, "type", "TELEMETRY");
    cJSON_AddStringToObject(root, "node_id", cfg->node_id);
    cJSON_AddStringToObject(root, "room_id", cfg->room_id);
    cJSON_AddStringToObject(root, "fw_ver", APP_FW_VERSION_STR);
    cJSON_AddNumberToObject(root, "uptime_s", (uint32_t)(esp_timer_get_time() / 1000000));

    cJSON *channels_arr = cJSON_CreateArray();
    for (uint8_t i = 1; i <= BOARD_RELAY_CHANNEL_COUNT; i++) {
        cJSON *ch_obj = cJSON_CreateObject();
        cJSON_AddNumberToObject(ch_obj, "channel", i);

        RelayState st = relay_get_state(i);
        RelayFault flt = relay_get_fault(i);
        cJSON_AddStringToObject(ch_obj, "state", (st == RELAY_STATE_ON) ? "ON" : "OFF");
        cJSON_AddNumberToObject(ch_obj, "fault", (int)flt);

        CurrentMeasurement meas = {};
        bl0942_get_latest_measurement(i, &meas);
        cJSON_AddNumberToObject(ch_obj, "current_ma", meas.current_rms_ma);
        cJSON_AddNumberToObject(ch_obj, "voltage_v", meas.voltage_rms_v);
        cJSON_AddNumberToObject(ch_obj, "power_w", meas.active_power_w);
        cJSON_AddNumberToObject(ch_obj, "energy_wh", meas.energy_wh);
        cJSON_AddBoolToObject(ch_obj, "valid", (meas.validity == SENSOR_STATUS_VALID));
        cJSON_AddNumberToObject(ch_obj, "sample_uptime_ms", meas.timestamp_ms);

        cJSON_AddItemToArray(channels_arr, ch_obj);
    }
    cJSON_AddItemToObject(root, "channels", channels_arr);

    char *rendered = cJSON_PrintUnformatted(root);
    if (!rendered) {
        cJSON_Delete(root);
        return ESP_ERR_NO_MEM;
    }

    if (strlen(rendered) >= max_len) {
        cJSON_free(rendered);
        cJSON_Delete(root);
        return ESP_ERR_INVALID_SIZE;
    }
    strncpy(out_json, rendered, max_len - 1);
    out_json[max_len - 1] = '\0';

    cJSON_free(rendered);
    cJSON_Delete(root);
    return ESP_OK;
}

esp_err_t protocol_serialize_fault_alert(uint8_t channel, RelayFault fault_type, uint32_t current_ma, char *out_json, size_t max_len) {
    if (!out_json || max_len == 0) return ESP_ERR_INVALID_ARG;

    const ActionBoxPersistentConfig *cfg = nvs_storage_get_cached_config();
    cJSON *root = cJSON_CreateObject();
    if (!root) return ESP_ERR_NO_MEM;

    add_identity(root);
    cJSON_AddNumberToObject(root, "version", APP_PROTOCOL_VERSION);
    cJSON_AddStringToObject(root, "type", "FAULT_ALERT");
    cJSON_AddStringToObject(root, "node_id", cfg->node_id);
    cJSON_AddNumberToObject(root, "channel", channel);
    cJSON_AddNumberToObject(root, "fault_code", (int)fault_type);
    cJSON_AddStringToObject(root, "fault_name", 
        (fault_type == RELAY_FAULT_OVERCURRENT) ? "OVERCURRENT_CUTOFF" : "HARDWARE_FAULT");
    cJSON_AddNumberToObject(root, "measured_current_ma", current_ma);
    cJSON_AddNumberToObject(root, "timestamp_ms", (uint32_t)(esp_timer_get_time() / 1000));

    char *rendered = cJSON_PrintUnformatted(root);
    if (!rendered) {
        cJSON_Delete(root);
        return ESP_ERR_NO_MEM;
    }

    if (strlen(rendered) >= max_len) {
        cJSON_free(rendered);
        cJSON_Delete(root);
        return ESP_ERR_INVALID_SIZE;
    }
    strncpy(out_json, rendered, max_len - 1);
    out_json[max_len - 1] = '\0';

    cJSON_free(rendered);
    cJSON_Delete(root);
    return ESP_OK;
}


esp_err_t protocol_serialize_load_report(const ActionBoxResponse *ack, uint32_t command_ms,
        const CurrentMeasurement *sample, char *out_json, size_t max_len) {
    if (!ack || !sample || !out_json) return ESP_ERR_INVALID_ARG;
    cJSON* root = cJSON_CreateObject();
    if (!root) return ESP_ERR_NO_MEM;
    add_identity(root);
    cJSON_AddStringToObject(root, "type", "LOAD_REPORT");
    cJSON_AddStringToObject(root, "node_id", ack->node_id);
    cJSON_AddNumberToObject(root, "request_id", ack->request_id);
    cJSON_AddNumberToObject(root, "session_id", ack->session_id);
    cJSON_AddNumberToObject(root, "channel", ack->channel);
    cJSON_AddStringToObject(root, "state", relay_get_state(ack->channel) == RELAY_STATE_ON ? "ON" : "OFF");
    cJSON_AddNumberToObject(root, "fault", relay_get_fault(ack->channel));
    cJSON* value = cJSON_AddObjectToObject(root, "sample");
    cJSON_AddBoolToObject(value, "valid", sample->validity == SENSOR_STATUS_VALID);
    cJSON_AddNumberToObject(value, "current_ma", sample->current_rms_ma);
    cJSON_AddNumberToObject(value, "power_w", sample->active_power_w);
    cJSON_AddNumberToObject(value, "sample_uptime_ms", sample->timestamp_ms);
    cJSON_AddNumberToObject(value, "command_uptime_ms", command_ms);
    cJSON_AddNumberToObject(value, "boot_id", s_boot_id);
    cJSON_AddNumberToObject(root, "uptime_ms", (uint32_t)(esp_timer_get_time()/1000));
    bool printed = cJSON_PrintPreallocated(root, out_json, max_len, false);
    cJSON_Delete(root);
    return printed ? ESP_OK : ESP_ERR_INVALID_SIZE;
}
