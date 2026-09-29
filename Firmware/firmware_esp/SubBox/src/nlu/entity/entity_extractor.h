/**
 * @file entity_extractor.h
 * @brief Vietnamese Entity Extractor for Devices, Rooms and Values
 */

#pragma once

#include <string>
#include "entity_types.h"

class EntityExtractor {
public:
    /**
     * @brief Extract all entities from normalized Vietnamese text
     * @param normalized_text Cleaned lowercase string
     * @return ParsedEntities struct with device, room and value
     */
    static ParsedEntities extract(const std::string& normalized_text);

    /**
     * @brief Extract targeted device type
     */
    static DeviceType extractDevice(const std::string& text);

    /**
     * @brief Extract explicitly stated target room
     */
    static RoomType extractRoom(const std::string& text);

    /**
     * @brief Extract numeric value (temperature, percentage, integer)
     * @param text Input text
     * @param out_val Output float
     * @return true if number was found
     */
    static bool extractNumericValue(const std::string& text, float& out_val);
};
