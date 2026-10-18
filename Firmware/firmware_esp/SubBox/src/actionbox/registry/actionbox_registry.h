#pragma once

#include <string>
#include <vector>
#include <map>
#include <mutex>
#include "nlu/entity/entity_types.h"

struct ActionBoxNode {
    std::string node_id;
    std::string hardware_uid;
    std::string label;
    uint32_t config_version = 0;
    RoomType    room;
    DeviceType  device;
    uint8_t     channel;
    bool        has_speaker;
    bool        has_microphone;
    bool        has_relay;
    bool        has_current_sensor;

    bool        is_online;
    bool        relay_state;
    uint32_t    current_ma;
    uint32_t    voltage_v;
    int32_t     power_w;
    bool        has_fault;
    std::string fault_msg;
    uint32_t    last_seen_ms;
};

class ActionBoxRegistry {
public:
    ActionBoxRegistry();
    ~ActionBoxRegistry() = default;

    bool registerNode(const ActionBoxNode& node);

    void updateTelemetry(
        const std::string& node_id,
        bool relay_on,
        uint32_t current_ma,
        uint32_t voltage_v,
        int32_t power_w,
        bool has_fault = false,
        const char* fault_str = nullptr
    );

    bool findNodeByDeviceAndRoom(DeviceType device, RoomType room, ActionBoxNode& out_node) const;

    bool findNodeById(const std::string& node_id, ActionBoxNode& out_node) const;

    void setCachedRelayState(const std::string& node_id, uint8_t channel, bool state);

    std::vector<ActionBoxNode> getAllNodes() const;

    void checkTimeouts(uint32_t timeout_ms = 30000);

    void loadDefaultRoomNodes(RoomType local_room);

private:
    std::map<std::string, ActionBoxNode> m_nodes;
    mutable std::mutex m_mutex;
};
