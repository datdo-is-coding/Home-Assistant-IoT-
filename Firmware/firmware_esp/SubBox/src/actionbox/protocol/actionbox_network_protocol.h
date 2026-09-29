/**
 * @file actionbox_network_protocol.h
 * @brief Idempotent JSON & Binary Protocol Formatter for SubBox -> ActionBox
 */

#pragma once

#include <stdint.h>
#include <string>
#include <cstring>
#include "cJSON.h"
#include "esp_random.h"
#include "nlu/intent/intent_types.h"

class ActionBoxNetworkProtocol {
public:
    /**
     * @brief Build JSON command payload for ActionBox
     * @param request_id Unique monotonic request identifier
     * @param cmd_str Command string: "TURN_ON", "TURN_OFF", "TOGGLE", "GET_STATE", "GET_POWER"
     * @param channel Relay channel (1 or 2)
     * @return Formatted JSON string
     */
    static std::string buildCommandJson(uint32_t request_id, const char* cmd_str, uint8_t channel, const char* node_id, const char* hardware_uid, uint32_t config_version) {
        if (!node_id || !*node_id || !cmd_str || strcmp(cmd_str, "TOGGLE") == 0 || !hardware_uid || strlen(hardware_uid) != 12 || !config_version) return "";
        cJSON *root = cJSON_CreateObject();
        if (!root) return "";
        cJSON_AddNumberToObject(root, "protocol_version", 3);
        cJSON_AddStringToObject(root, "hardware_uid", hardware_uid);
        cJSON_AddNumberToObject(root, "config_version", config_version);
        cJSON_AddStringToObject(root, "node_id", node_id);
        cJSON_AddNumberToObject(root, "request_id", request_id);
        static const uint32_t session_id = esp_random() | 1;
        cJSON_AddNumberToObject(root, "session_id", session_id);
        cJSON_AddStringToObject(root, "cmd", cmd_str);
        cJSON_AddNumberToObject(root, "channel", channel);

        char *rendered = cJSON_PrintUnformatted(root);
        std::string json_str = (rendered != nullptr) ? rendered : "";
        if (rendered) free(rendered);
        cJSON_Delete(root);
        return json_str;
    }
};
