#pragma once

#include <memory>
#include <functional>
#include <string>
#include "actionbox/registry/actionbox_registry.h"

struct RuleConfig {
    uint32_t current_overload_ma;
    float    temp_fan_auto_on_c;
    bool     auto_fan_enabled;
    bool     overcurrent_trip_enabled;
};

class RuleEngine {
public:
    RuleEngine(std::shared_ptr<ActionBoxRegistry> registry);
    ~RuleEngine() = default;

    void init();

    void evaluate(float ambient_temp_c = -1.0f);

    void setRuleConfig(const RuleConfig& config);
    RuleConfig getRuleConfig() const;

    void registerRuleTriggerCallback(std::function<void(const std::string& rule_name, const std::string& msg)> cb);

private:
    std::shared_ptr<ActionBoxRegistry> m_registry;
    RuleConfig m_config;
    std::function<void(const std::string&, const std::string&)> m_trigger_cb;
};
