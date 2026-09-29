/**
 * @file room_manager.h
 * @brief SubBox Room Identity and Boundary Coordinator
 */

#pragma once

#include <string>
#include <mutex>
#include "nlu/entity/entity_types.h"

class RoomManager {
public:
    RoomManager(const std::string& subbox_id = "subbox_livingroom_01", RoomType room = RoomType::LIVING_ROOM);
    ~RoomManager() = default;

    std::string getSubBoxId() const;
    void setSubBoxId(const std::string& id);

    RoomType getRoomType() const;
    void setRoomType(RoomType room);

    std::string getRoomName() const;
    void setRoomName(const std::string& name);

    bool isLocalRoom(RoomType room) const;

private:
    std::string m_subbox_id;
    RoomType    m_room_type;
    std::string m_room_name;
    mutable std::mutex m_mutex;
};
