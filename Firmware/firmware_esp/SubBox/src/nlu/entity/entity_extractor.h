#pragma once

#include <string>
#include "entity_types.h"

class EntityExtractor {
public:

    static ParsedEntities extract(const std::string& normalized_text);

    static DeviceType extractDevice(const std::string& text);

    static RoomType extractRoom(const std::string& text);

    static bool extractNumericValue(const std::string& text, float& out_val);
};
