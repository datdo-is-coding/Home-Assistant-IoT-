/**
 * @file intent_types.h
 * @brief Intent Enumeration and Helper Functions
 */

#pragma once

enum class IntentType {
    TURN_ON,            /**< "bật đèn", "mở quạt" */
    TURN_OFF,           /**< "tắt đèn", "đóng relay" */
    TOGGLE,             /**< "đổi trạng thái đèn" */
    SET_TEMPERATURE,    /**< "chỉnh nhiệt độ 25 độ" */
    INCREASE,           /**< "tăng quạt", "tăng 2 độ" */
    DECREASE,           /**< "giảm quạt", "hạ nhiệt độ" */
    QUERY_STATE,        /**< "đèn đang bật hay tắt" */
    QUERY_CURRENT,      /**< "dòng điện bao nhiêu ampe" */
    QUERY_POWER,        /**< "công suất tiêu thụ là bao nhiêu" */
    STOP,               /**< "dừng lại", "ngừng" */
    UNKNOWN,            /**< Unrecognized local speech */
    COMPLEX             /**< Multi-condition / conditional sentence -> Forward to Pi4 */
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
