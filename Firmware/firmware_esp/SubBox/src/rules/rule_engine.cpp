/**
 * @file rule_engine.cpp
 * @brief Deterministic Local Automation Rule Engine Implementation
 */

#include "rule_engine.h"
#include "esp_log.h"

static const char* TAG = "RULE_ENGINE";

RuleEngine::RuleEngine(std::shared_ptr<ActionBoxRegistry> registry)
    : m_registry(registry) {
    m_config.current_overload_ma = 10000; // 10A default limit
    m_config.temp_fan_auto_on_c = 32.0f;  // 32 degC fan trigger
    m_config.auto_fan_enabled = true;
    m_config.overcurrent_trip_enabled = true;
}

void RuleEngine::init() {
    ESP_LOGI(TAG, "Local Rule Engine initialized (Overcurrent: %lu mA, TempFan: %.1f C)",
             (unsigned long)m_config.current_overload_ma, m_config.temp_fan_auto_on_c);
}

void RuleEngine::setRuleConfig(const RuleConfig& config) {
    m_config = config;
}

RuleConfig RuleEngine::getRuleConfig() const {
    return m_config;
}

void RuleEngine::registerRuleTriggerCallback(std::function<void(const std::string&, const std::string&)> cb) {
    m_trigger_cb = cb;
}

void RuleEngine::evaluate(float ambient_temp_c) {
    if (!m_registry) return;

    std::vector<ActionBoxNode> nodes = m_registry->getAllNodes();

    for (const auto& node : nodes) {
        // RULE 1: IF current > limit THEN relay OFF
        if (m_config.overcurrent_trip_enabled && node.relay_state && (node.current_ma > m_config.current_overload_ma)) {
            ESP_LOGE(TAG, "🚨 [RULE TRIGGER] Overcurrent on %s (%lu mA > %lu mA) -> FORCING RELAY OFF!",
                     node.node_id.c_str(), (unsigned long)node.current_ma, (unsigned long)m_config.current_overload_ma);

            m_registry->setCachedRelayState(node.node_id, node.channel, false);

            if (m_trigger_cb) {
                m_trigger_cb("OVERCURRENT_TRIP",
                             "Đã tự động ngắt " + node.node_id + " do quá tải dòng điện (" +
                             std::to_string(node.current_ma) + " mA)!");
            }
        }

        // RULE 2: IF device fault THEN report event
        if (node.has_fault) {
            ESP_LOGW(TAG, "⚠️ [RULE TRIGGER] Hardware fault detected on %s: %s",
                     node.node_id.c_str(), node.fault_msg.c_str());

            if (m_trigger_cb) {
                m_trigger_cb("HARDWARE_FAULT",
                             "Cảnh báo: Thiết bị " + node.node_id + " gặp sự cố phần cứng: " + node.fault_msg);
            }
        }

        // RULE 3: IF temperature > threshold THEN FAN ON
        if (m_config.auto_fan_enabled && ambient_temp_c > 0.0f && (ambient_temp_c >= m_config.temp_fan_auto_on_c)) {
            if (node.device == DeviceType::FAN && !node.relay_state) {
                ESP_LOGI(TAG, "🌡️ [RULE TRIGGER] Ambient temp %.1fC >= %.1fC -> AUTO TURNING ON FAN (%s)!",
                         ambient_temp_c, m_config.temp_fan_auto_on_c, node.node_id.c_str());

                m_registry->setCachedRelayState(node.node_id, node.channel, true);

                if (m_trigger_cb) {
                    m_trigger_cb("AUTO_FAN_ON",
                                 "Nhiệt độ phòng đạt " + std::to_string((int)ambient_temp_c) +
                                 " độ C. Đã tự động bật quạt.");
                }
            }
        }
    }
}
