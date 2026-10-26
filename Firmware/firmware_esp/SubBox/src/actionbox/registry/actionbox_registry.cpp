#include "actionbox_registry.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "AB_REGISTRY";

ActionBoxRegistry::ActionBoxRegistry() {
}

bool ActionBoxRegistry::registerNode(const ActionBoxNode& node) {
    if (node.node_id.empty()) return false;

    std::lock_guard<std::mutex> lock(m_mutex);
    m_nodes[node.node_id] = node;
    m_nodes[node.node_id].last_seen_ms = (uint32_t)(esp_timer_get_time() / 1000);
    m_nodes[node.node_id].is_online = true;

    ESP_LOGD(TAG, "Registered ActionBox: %s [Room: %s, Device: %s, Ch: %u, Spk: %d, Mic: %d]",
             node.node_id.c_str(), roomToString(node.room), deviceToString(node.device),
             node.channel, node.has_speaker, node.has_microphone);
    return true;
}

void ActionBoxRegistry::updateTelemetry(
    const std::string& node_id,
    bool relay_on,
    uint32_t current_ma,
    uint32_t voltage_v,
    int32_t power_w,
    bool has_fault,
    const char* fault_str
) {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_nodes.find(node_id);
    if (it != m_nodes.end()) {
        it->second.relay_state = relay_on;
        it->second.current_ma = current_ma;
        it->second.voltage_v = voltage_v;
        it->second.power_w = power_w;
        it->second.has_fault = has_fault;
        if (fault_str) it->second.fault_msg = fault_str;
        it->second.last_seen_ms = (uint32_t)(esp_timer_get_time() / 1000);
        it->second.is_online = true;
    }
}

bool ActionBoxRegistry::findNodeByDeviceAndRoom(DeviceType device, RoomType room, ActionBoxNode& out_node) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    bool found = false;
    for (const auto& pair : m_nodes) {
        const auto& node = pair.second;
        if (node.is_online && node.device == device &&
            (room == RoomType::UNSPECIFIED || node.room == room)) {
            if (found) return false;
            out_node = node;
            found = true;
        }
    }
    return found;
}

bool ActionBoxRegistry::findNodeById(const std::string& node_id, ActionBoxNode& out_node) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_nodes.find(node_id);
    if (it != m_nodes.end()) {
        out_node = it->second;
        return true;
    }

    for (const auto& pair : m_nodes) {
        if (pair.second.node_id == node_id || pair.second.node_id == node_id + "_CH2") {
            out_node = pair.second;
            return true;
        }
    }
    return false;
}

void ActionBoxRegistry::setCachedRelayState(const std::string& node_id, uint8_t channel, bool state) {
    std::lock_guard<std::mutex> lock(m_mutex);
    for (auto& pair : m_nodes) {
        if (pair.second.node_id.rfind(node_id, 0) == 0 && pair.second.channel == channel) {
            pair.second.relay_state = state;
        }
    }
}

std::vector<ActionBoxNode> ActionBoxRegistry::getAllNodes() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    std::vector<ActionBoxNode> list;
    list.reserve(m_nodes.size());
    for (const auto& pair : m_nodes) {
        list.push_back(pair.second);
    }
    return list;
}

void ActionBoxRegistry::checkTimeouts(uint32_t timeout_ms) {
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    std::lock_guard<std::mutex> lock(m_mutex);
    for (auto& pair : m_nodes) {
        if (pair.second.is_online && (now - pair.second.last_seen_ms > timeout_ms)) {
            pair.second.is_online = false;
            ESP_LOGW(TAG, "ActionBox node offline timeout: %s", pair.second.node_id.c_str());
        }
    }
}
