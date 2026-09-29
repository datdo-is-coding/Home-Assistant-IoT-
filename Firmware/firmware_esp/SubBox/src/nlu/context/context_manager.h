/**
 * @file context_manager.h
 * @brief Context Tracking and Pronoun Resolution for Vietnamese NLU
 */

#pragma once

#include <string>
#include <mutex>
#include <cstdint>
#include "nlu/intent/intent_types.h"
#include "nlu/entity/entity_types.h"

struct CommandResolution {
    IntentType  intent;
    DeviceType  device;
    RoomType    target_room;
    RoomType    speaker_room;
    std::string origin_node_id;
    bool        has_value;
    float       value;
    bool        resolved_via_context;
    bool        is_valid;
    std::string error_reason;
    std::string raw_text;
};

class ContextManager {
public:
    explicit ContextManager(RoomType subbox_room = RoomType::LIVING_ROOM);
    ~ContextManager() = default;

    /**
     * @brief Resolve complete command from extracted intent & entities against room context
     * @param raw_text Normalized text
     * @param origin_node_id ActionBox node that captured the audio
     * @param intent Intent classified
     * @param entities Entities extracted
     * @return Fully resolved CommandResolution
     */
    CommandResolution resolve(
        const std::string& raw_text,
        const std::string& origin_node_id,
        IntentType intent,
        const ParsedEntities& entities
    );

    /**
     * @brief Commit a successfully executed command into context history
     */
    void commitResolution(const CommandResolution& res);

    void setSubboxRoom(RoomType room);
    RoomType getSubboxRoom() const;

    void reset();

private:
    RoomType    m_subbox_room;
    std::string m_last_input_actionbox;
    DeviceType  m_last_device;
    RoomType    m_last_target_room;
    IntentType  m_last_intent;
    float       m_last_value;
    bool        m_has_history;
    int64_t     m_last_context_us = 0;
    mutable std::mutex m_mutex;
};
