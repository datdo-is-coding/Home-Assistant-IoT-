#pragma once

enum class IntentType {
    TURN_ON,
    TURN_OFF,
    TOGGLE,
    SET_TEMPERATURE,
    INCREASE,
    DECREASE,
    QUERY_STATE,
    QUERY_CURRENT,
    QUERY_POWER,
    STOP,
    UNKNOWN,
    COMPLEX
};

inline const char* intentToString(IntentType intent) {
    switch (intent) {
        case IntentType::TURN_ON:         return "TURN_ON";
        case IntentType::TURN_OFF:        return "TURN_OFF";
        case IntentType::TOGGLE:          return "TOGGLE";
        case IntentType::SET_TEMPERATURE: return "SET_TEMPERATURE";
        case IntentType::INCREASE:        return "INCREASE";
        case IntentType::DECREASE:        return "DECREASE";
        case IntentType::QUERY_STATE:     return "QUERY_STATE";
        case IntentType::QUERY_CURRENT:   return "QUERY_CURRENT";
        case IntentType::QUERY_POWER:     return "QUERY_POWER";
        case IntentType::STOP:            return "STOP";
        case IntentType::COMPLEX:         return "COMPLEX";
        default:                          return "UNKNOWN";
    }
}
