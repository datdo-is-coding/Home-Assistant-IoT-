/**
 * @file actionbox_registry.h
 * @brief Dynamic Registry and State Cache for ActionBoxes
 */

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
    uint8_t     channel;            /**< 1 or 2 */
    bool        has_speaker;
    bool        has_microphone;
    bool        has_relay;
    bool        has_current_sensor;

    bool        is_online;
    bool        relay_state;        /**< true = ON, false = OFF */
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

    /**
     * @brief Register or update node metadata
     */
    bool registerNode(const ActionBoxNode& node);

    /**
     * @brief Update live telemetry received from an ActionBox
     */
    void updateTelemetry(
        const std::string& node_id,
        bool relay_on,
        uint32_t current_ma,
        uint32_t voltage_v,
        int32_t power_w,
        bool has_fault = false,
        const char* fault_str = nullptr
    );

    /**
     * @brief Find specific ActionBox matching device and room
     * @param device Target device type (e.g. LIGHT, FAN)
     * @param room Target room (e.g. LIVING_ROOM)
     * @param out_node Pointer to receiving ActionBoxNode copy
     * @return true if found
     */
    bool findNodeByDeviceAndRoom(DeviceType device, RoomType room, ActionBoxNode& out_node) const;

    /**
     * @brief Find ActionBox by its unique string node ID
     */
    bool findNodeById(const std::string& node_id, ActionBoxNode& out_node) const;

    /**
     * @brief Update relay state cache immediately upon command dispatch
     */
    void setCachedRelayState(const std::string& node_id, uint8_t channel, bool state);

    /**
     * @brief Retrieve snapshot of all registered ActionBoxes
     */
    std::vector<ActionBoxNode> getAllNodes() const;

    /**
     * @brief Check node timeouts and update online/offline status
     * @param timeout_ms Max time without heartbeat before considered offline (default 30s)
     */
    void checkTimeouts(uint32_t timeout_ms = 30000);

    /**
     * @brief Populate default demo nodes for local room if registry is empty
     */
    void loadDefaultRoomNodes(RoomType local_room);

private:
    std::map<std::string, ActionBoxNode> m_nodes;
    mutable std::mutex m_mutex;
};
