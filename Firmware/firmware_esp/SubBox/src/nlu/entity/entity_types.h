#pragma once

#include <string>

enum class DeviceType {
    LIGHT,
    FAN,
    AIR_CONDITIONER,
    SOCKET,
    OTHER,
    NONE
};

enum class RoomType {
    BEDROOM,
    LIVING_ROOM,
    KITCHEN,
    BALCONY,
    PORCH,
    OUTDOOR,
    OTHER,
    UNSPECIFIED
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
