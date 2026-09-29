/**
 * @file room_manager.cpp
 * @brief SubBox Room Identity Implementation
 */

#include "room_manager.h"

RoomManager::RoomManager(const std::string& subbox_id, RoomType room)
    : m_subbox_id(subbox_id),
      m_room_type(room),
      m_room_name(roomToString(room)) {
}

std::string RoomManager::getSubBoxId() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_subbox_id;
}

void RoomManager::setSubBoxId(const std::string& id) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_subbox_id = id;
}

RoomType RoomManager::getRoomType() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_room_type;
}

void RoomManager::setRoomType(RoomType room) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_room_type = room;
    m_room_name = roomToString(room);
}

std::string RoomManager::getRoomName() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_room_name;
}

void RoomManager::setRoomName(const std::string& name) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_room_name = name;
}

bool RoomManager::isLocalRoom(RoomType room) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return (room == m_room_type || room == RoomType::UNSPECIFIED);
}
