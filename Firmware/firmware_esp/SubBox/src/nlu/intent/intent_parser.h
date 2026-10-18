#pragma once

#include <string>
#include "intent_types.h"

class IntentParser {
public:

    static IntentType parse(const std::string& normalized_text);

    static bool isComplexCommand(const std::string& text);
};
