/**
 * @file intent_parser.h
 * @brief Deterministic Rule-Based Intent Classifier for Smart Home
 */

#pragma once

#include <string>
#include "intent_types.h"

class IntentParser {
public:
    /**
     * @brief Classify intent from normalized Vietnamese text
     * @param normalized_text Lowercase, cleaned Vietnamese string
     * @return IntentType recognized
     */
    static IntentType parse(const std::string& normalized_text);

    /**
     * @brief Check if utterance contains complex conditional logic
     * @param text Normalized text
     * @return true if requires Pi4 LLM/reasoning
     */
    static bool isComplexCommand(const std::string& text);
};
