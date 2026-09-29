/**
 * @file entity_types.h
 * @brief Device, Room and Value Entity Definitions
 */

#pragma once

#include <string>

enum class DeviceType {
    LIGHT,              /**< Đèn chiếu sáng */
    FAN,                /**< Quạt */
    AIR_CONDITIONER,    /**< Điều hòa / Máy lạnh */
    SOCKET,             /**< Ổ cắm điện */
    OTHER,              /**< Thiết bị khác */
    NONE                /**< Không xác định rõ trong câu */
};

enum class RoomType {
    BEDROOM,            /**< Phòng ngủ */
    LIVING_ROOM,        /**< Phòng khách */
    KITCHEN,            /**< Phòng bếp */
    BALCONY,            /**< Ban công */
    PORCH,              /**< Hiên / Hành lang */
    OUTDOOR,            /**< Ngoài trời / Sân */
    OTHER,              /**< Phòng khác */
    UNSPECIFIED         /**< Không chỉ định rõ -> Dùng speaker/subbox room */
};

struct ParsedEntities {
    DeviceType  device;
    RoomType    room;
    bool        has_numeric_value;
    float       numeric_value;
    std::string raw_value_str;
};

inline const char* deviceToString(DeviceType device) {
    switch (device) {
        case DeviceType::LIGHT:           return "LIGHT";
        case DeviceType::FAN:             return "FAN";
        case DeviceType::AIR_CONDITIONER: return "AIR_CONDITIONER";
        case DeviceType::SOCKET:          return "SOCKET";
        case DeviceType::OTHER:           return "OTHER";
        default:                          return "NONE";
    }
}

inline const char* roomToString(RoomType room) {
    switch (room) {
        case RoomType::BEDROOM:     return "BEDROOM";
        case RoomType::LIVING_ROOM: return "LIVING_ROOM";
        case RoomType::KITCHEN:     return "KITCHEN";
        case RoomType::BALCONY:     return "BALCONY";
        case RoomType::PORCH:       return "PORCH";
        case RoomType::OUTDOOR:     return "OUTDOOR";
        case RoomType::OTHER:       return "OTHER";
        default:                    return "UNSPECIFIED";
    }
}
