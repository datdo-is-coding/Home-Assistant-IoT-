/**
 * @file context_manager.cpp
 * @brief Context Tracking and Pronoun Resolution Implementation
 */

#include "context_manager.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "CONTEXT_MGR";

ContextManager::ContextManager(RoomType subbox_room)
    : m_subbox_room(subbox_room),
      m_last_device(DeviceType::NONE),
      m_last_target_room(RoomType::UNSPECIFIED),
      m_last_intent(IntentType::UNKNOWN),
      m_last_value(0.0f),
      m_has_history(false) {
}

void ContextManager::setSubboxRoom(RoomType room) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_subbox_room = room;
    ESP_LOGI(TAG, "SubBox local room configured to: %s", roomToString(m_subbox_room));
}

RoomType ContextManager::getSubboxRoom() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_subbox_room;
}

void ContextManager::reset() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_last_device = DeviceType::NONE;
    m_last_target_room = RoomType::UNSPECIFIED;
    m_last_intent = IntentType::UNKNOWN;
    m_last_value = 0.0f;
    m_has_history = false;
    m_last_input_actionbox.clear();
}

CommandResolution ContextManager::resolve(
    const std::string& raw_text,
    const std::string& origin_node_id,
    IntentType intent,
    const ParsedEntities& entities
) {
    std::lock_guard<std::mutex> lock(m_mutex);

    CommandResolution res;
    const bool usable_history = m_has_history && m_last_input_actionbox == origin_node_id &&
        esp_timer_get_time() - m_last_context_us < 30000000LL;
    res.raw_text = raw_text;
    res.intent = intent;
    res.speaker_room = m_subbox_room;
    res.origin_node_id = origin_node_id;
    res.has_value = entities.has_numeric_value;
    res.value = entities.numeric_value;
    res.resolved_via_context = false;
    res.is_valid = true;
    res.error_reason.clear();

    // 1. Resolve Target Room vs Speaker Room
    if (entities.room != RoomType::UNSPECIFIED) {
        // Explicitly mentioned target room (e.g. "bật đèn phòng bếp")
        res.target_room = entities.room;
    } else {
        // Unspecified -> Default to current SubBox room
        res.target_room = m_subbox_room;
    }

    // 2. Resolve Target Device
    if (entities.device != DeviceType::NONE) {
        res.device = entities.device;
    } else {
        // Check for pronoun or relative references ("nó", "lại", "đó", "cái đó")
        bool has_pronoun = (raw_text.find(" nó") != std::string::npos ||
                            raw_text.find(" lại") != std::string::npos ||
                            raw_text.find(" đó") != std::string::npos ||
                            raw_text.find("cái đó") != std::string::npos);

        if (has_pronoun && usable_history && m_last_device != DeviceType::NONE) {
            res.device = m_last_device;
            res.resolved_via_context = true;
            if (entities.room == RoomType::UNSPECIFIED && m_last_target_room != RoomType::UNSPECIFIED) {
                res.target_room = m_last_target_room;
            }
            ESP_LOGI(TAG, "Resolved pronoun reference -> Device: %s, Room: %s",
                     deviceToString(res.device), roomToString(res.target_room));
        } else if (intent == IntentType::INCREASE || intent == IntentType::DECREASE || intent == IntentType::STOP) {
            // "tăng lên", "giảm đi", "dừng lại" without naming device inherits last device
            if (usable_history && m_last_device != DeviceType::NONE) {
                res.device = m_last_device;
                res.resolved_via_context = true;
            } else {
                res.device = DeviceType::NONE;
                res.is_valid = false;
                res.error_reason = "Không rõ thiết bị nào cần điều chỉnh";
            }
        } else if (intent == IntentType::COMPLEX) {
            // Complex commands are valid for Pi4 forwarding even without local device resolution
            res.device = DeviceType::NONE;
            res.is_valid = true;
        } else {
            res.device = DeviceType::NONE;
            res.is_valid = false;
            res.error_reason = "Không xác định được thiết bị trong câu nói";
        }
    }

    if (intent == IntentType::UNKNOWN) {
        res.is_valid = false;
        res.error_reason = "Lệnh không được nhận diện";
    }

    return res;
}

void ContextManager::commitResolution(const CommandResolution& res) {
    if (!res.is_valid || res.intent == IntentType::UNKNOWN) return;

    std::lock_guard<std::mutex> lock(m_mutex);
    m_last_input_actionbox = res.origin_node_id;
    if (res.device != DeviceType::NONE) {
        m_last_device = res.device;
    }
    if (res.target_room != RoomType::UNSPECIFIED) {
        m_last_target_room = res.target_room;
    }
    m_last_intent = res.intent;
    if (res.has_value) {
        m_last_value = res.value;
    }
    m_has_history = true;
    m_last_context_us = esp_timer_get_time();

    ESP_LOGD(TAG, "Context updated -> LastDevice: %s, LastRoom: %s, LastIntent: %s",
             deviceToString(m_last_device), roomToString(m_last_target_room), intentToString(m_last_intent));
}
