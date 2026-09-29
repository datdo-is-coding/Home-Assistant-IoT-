/**
 * @file command_router.cpp
 * @brief Local vs Cross-Room Command Execution & Router Implementation
 */

#include "command_router.h"
#include "actionbox/protocol/actionbox_network_protocol.h"
#include "esp_log.h"
#include "esp_random.h"
#include <cstring>

static const char* TAG = "CMD_ROUTER";

CommandRouter::CommandRouter(
    std::shared_ptr<ActionBoxRegistry> registry,
    std::shared_ptr<ContextManager> context_mgr,
    std::shared_ptr<AudioOutputRouter> audio_router,
    std::shared_ptr<AudioTransport> transport
) : m_registry(registry),
    m_context_mgr(context_mgr),
    m_audio_router(audio_router),
    m_transport(transport),
    m_mqtt_client(nullptr),
    m_request_counter(esp_random() & 0x3fffffff) {
}

void CommandRouter::setMqttClient(std::shared_ptr<MqttClient> mqtt_client) {
    m_mqtt_client = mqtt_client;
}

ExecutionResult CommandRouter::route(const CommandResolution& res) {
    ExecutionResult result;
    result.success = false;
    result.is_cross_room = false;
    result.forwarded_to_pi4 = false;

    if (!res.is_valid) {
        result.response_text = res.error_reason.empty() ?
                               "Không thể thực hiện yêu cầu này." : res.error_reason;
        ESP_LOGW(TAG, "Command validation failed: %s", result.response_text.c_str());
        return result;
    }

    // 1. Complex Condition / Scene Command -> Forward to Pi4
    if (res.intent == IntentType::COMPLEX) {
        return forwardToPi4(res);
    }

    // 2. Cross-Room Command -> Forward to Target Room SubBox / Pi4
    if (res.target_room != res.speaker_room && res.target_room != RoomType::UNSPECIFIED) {
        return forwardCrossRoom(res);
    }

    // 3. Local Command Execution in this SubBox's room
    ActionBoxNode node;
    bool found = m_registry->findNodeByDeviceAndRoom(res.device, res.target_room, node);

    // Fallback: If not found in target room, search local room
    if (!found) {
        found = m_registry->findNodeByDeviceAndRoom(res.device, m_context_mgr->getSubboxRoom(), node);
    }

    if (!found) {
        std::string candidates;
        for (const auto& candidate : m_registry->getAllNodes()) {
            if (candidate.is_online && candidate.device == res.device && candidate.room == res.target_room)
                candidates += (candidates.empty() ? "" : ", ") + candidate.label;
        }
        result.response_text = candidates.empty() ? "Không tìm thấy thiết bị phù hợp." :
            "Có nhiều thiết bị phù hợp: " + candidates + ". Hãy nói rõ nhãn thiết bị.";
        ESP_LOGW(TAG, "%s", result.response_text.c_str());
        return result;
    }

    return executeLocalCommand(res, node);
}

ExecutionResult CommandRouter::executeLocalCommand(const CommandResolution& res, const ActionBoxNode& node) {
    ExecutionResult result;
    result.success = false;
    result.target_node_id = node.node_id;
    result.is_cross_room = false;
    result.forwarded_to_pi4 = false;

    uint32_t req_id = ++m_request_counter;
    std::string cmd_str;
    std::string dev_name;

    switch (node.device) {
        case DeviceType::LIGHT:           dev_name = "đèn"; break;
        case DeviceType::FAN:             dev_name = "quạt"; break;
        case DeviceType::AIR_CONDITIONER: dev_name = "điều hòa"; break;
        case DeviceType::SOCKET:          dev_name = "ổ cắm"; break;
        default:                          dev_name = "thiết bị"; break;
    }

    switch (res.intent) {
        case IntentType::TURN_ON: cmd_str = "TURN_ON"; break;
        case IntentType::TURN_OFF: cmd_str = "TURN_OFF"; break;
        case IntentType::TOGGLE:
            result.response_text = "Hãy nói bật hoặc tắt thiết bị.";
            return result;
        case IntentType::QUERY_STATE: cmd_str = "GET_STATE"; break;
        case IntentType::QUERY_CURRENT: cmd_str = "GET_CURRENT"; break;
        case IntentType::QUERY_POWER: cmd_str = "GET_POWER"; break;
        default:
            result.response_text = "Thiết bị relay không hỗ trợ lệnh này.";
            return result;
    }

    // Registry distinguishes the physical board from its relay-channel entry.
    std::string board_id = node.node_id;
    if (node.channel == 2 && board_id.size() > 4 && board_id.compare(board_id.size() - 4, 4, "_CH2") == 0)
        board_id.resize(board_id.size() - 4);
    std::string json_cmd = ActionBoxNetworkProtocol::buildCommandJson(req_id, cmd_str.c_str(), node.channel, board_id.c_str(), node.hardware_uid.c_str(), node.config_version);
    ESP_LOGI(TAG, "🟢 [LOCAL-ROOM COMMAND] ActionBox: %s | Room: %s | Device: %s | Action: %s -> Sending ESP-NOW to %s (Ch %u): %s",
             res.origin_node_id.c_str(), roomToString(res.speaker_room),
             deviceToString(res.device), intentToString(res.intent),
             node.node_id.c_str(), node.channel, json_cmd.c_str());

    // Transmit command directly over ESP-NOW transport
    std::string response;
    result.success = m_transport && m_transport->sendCommand(board_id.c_str(), json_cmd, &response);
    if (!result.success) {
        result.response_text = "Thiết bị chưa xác nhận lệnh hoặc đang báo lỗi.";
        return result;
    }
    cJSON* ack = cJSON_Parse(response.c_str());
    const cJSON* state = cJSON_GetObjectItem(ack, "state");
    if (!cJSON_IsString(state)) {
        cJSON_Delete(ack);
        result.success = false;
        result.response_text = "Phản hồi thiết bị không hợp lệ.";
        return result;
    }
    const bool on = strcmp(state->valuestring, "ON") == 0;
    const bool off = strcmp(state->valuestring, "OFF") == 0;
    if ((!on && !off) || (res.intent == IntentType::TURN_ON && !on) ||
        (res.intent == IntentType::TURN_OFF && !off)) {
        cJSON_Delete(ack);
        result.success = false;
        result.response_text = "Thiết bị báo lỗi hoặc trạng thái không khớp yêu cầu.";
        return result;
    }
    m_registry->setCachedRelayState(node.node_id, node.channel, on);
    if (res.intent == IntentType::QUERY_CURRENT || res.intent == IntentType::QUERY_POWER) {
        const bool current = res.intent == IntentType::QUERY_CURRENT;
        const cJSON* value = cJSON_GetObjectItem(ack, current ? "current_ma" : "power_w");
        result.response_text = dev_name + ": " + std::to_string(cJSON_IsNumber(value) ? value->valueint : 0) +
                               (current ? " miliampe." : " oát.");
    } else {
        if (res.intent == IntentType::TURN_ON || res.intent == IntentType::TURN_OFF)
            result.response_text = "Thiết bị đã nhận lệnh nhưng chưa xác nhận tải.";
        else result.response_text = dev_name + (on ? " relay đang bật; chưa xác nhận tải." : " relay đang tắt; chưa xác nhận tải.");
    }
    cJSON_Delete(ack);

    // Commit to context
    m_context_mgr->commitResolution(res);

    // Record last input node for directed TTS audio response
    if (m_audio_router) {
        m_audio_router->setLastInputNodeId(res.origin_node_id);
    }

    return result;
}

ExecutionResult CommandRouter::forwardToPi4(const CommandResolution& res) {
    ExecutionResult result;
    result.success = false;
    result.is_cross_room = false;
    result.forwarded_to_pi4 = true;
    result.response_text = "Yêu cầu có điều kiện đang được chuyển tới máy chủ xử lý.";

    ESP_LOGI(TAG, "Forwarding COMPLEX command to Raspberry Pi 4 via MQTT...");
    // Will be published on MQTT topic home/subbox/<id>/voice/request by mqtt_client
    return result;
}

ExecutionResult CommandRouter::forwardCrossRoom(const CommandResolution& res) {
    ExecutionResult result;
    result.success = false;
    result.is_cross_room = true;
    result.forwarded_to_pi4 = true;
    result.response_text = std::string("Đã gửi lệnh điều khiển ") + deviceToString(res.device) + " tới " + roomToString(res.target_room);

    ESP_LOGI(TAG, "🌐 [CROSS-ROOM COMMAND] ActionBox: %s | Speaker Room: %s | Target Room: %s | Device: %s | Action: %s",
             res.origin_node_id.c_str(), roomToString(res.speaker_room), roomToString(res.target_room),
             deviceToString(res.device), intentToString(res.intent));

    return result;
}
