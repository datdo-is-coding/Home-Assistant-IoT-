/**
 * @file rule_engine.h
 * @brief Deterministic Local Automation Rule Engine
 */

#pragma once

#include <memory>
#include <functional>
#include <string>
#include "actionbox/registry/actionbox_registry.h"

struct RuleConfig {
    uint32_t current_overload_ma;    /**< Overcurrent protection limit (default 10000mA = 10A) */
    float    temp_fan_auto_on_c;     /**< Auto fan threshold in Celsius (default 32.0C) */
    bool     auto_fan_enabled;
    bool     overcurrent_trip_enabled;
};

class RuleEngine {
public:
    RuleEngine(std::shared_ptr<ActionBoxRegistry> registry);
    ~RuleEngine() = default;

    void init();

    /**
     * @brief Periodic evaluation of local rules across all registered nodes
     * @param ambient_temp_c Current room temperature (or -1.0 if sensor unavailable)
     */
    void evaluate(float ambient_temp_c = -1.0f);

    void setRuleConfig(const RuleConfig& config);
    RuleConfig getRuleConfig() const;

    /**
     * @brief Register callback when an automated rule triggers an action
     */
    void registerRuleTriggerCallback(std::function<void(const std::string& rule_name, const std::string& msg)> cb);

private:
    std::shared_ptr<ActionBoxRegistry> m_registry;
    RuleConfig m_config;
    std::function<void(const std::string&, const std::string&)> m_trigger_cb;
};
