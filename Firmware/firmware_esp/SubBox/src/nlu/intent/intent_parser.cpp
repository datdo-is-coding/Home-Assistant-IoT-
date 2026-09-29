/**
 * @file intent_parser.cpp
 * @brief Deterministic Rule-Based Intent Classifier Implementation
 */

#include "intent_parser.h"
#include "nlu/normalizer/vietnamese_normalizer.h"
#include "esp_log.h"

static const char* TAG = "INTENT_PARSER";

bool IntentParser::isComplexCommand(const std::string& text) {
    // Check conditional and scheduling keywords requiring Pi4 LLM/Reasoning
    static const char* complex_indicators[] = {
        "nếu ", " khi ", "thì ", "hẹn giờ", "lịch trình", "mỗi ngày", "lúc mấy giờ",
        "tự động", "kịch bản", "về nhà", "đi ngủ", "sau khi", "trước khi",
        "hôm qua", "tuần trước", "tháng trước", "trên 30 độ thì", "dưới 20 độ thì"
    };

    for (const char* indicator : complex_indicators) {
        if (text.find(indicator) != std::string::npos) {
            return true;
        }
    }
    return false;
}

IntentType IntentParser::parse(const std::string& normalized_text) {
    if (normalized_text.empty()) {
        return IntentType::UNKNOWN;
    }

    // Negated or ambiguous questions must never fall through to an actuator.
    for (const char* word : {"đừng", "chớ", "không", "chưa", "khoan"}) {
        if (VietnameseNormalizer::containsWord(normalized_text, word)) {
            return IntentType::UNKNOWN;
        }
    }

    // 1. Complex Condition Detection -> Forward to Pi4
    if (isComplexCommand(normalized_text)) {
        ESP_LOGI(TAG, "Utterance flagged as COMPLEX conditional -> Routing to Pi4");
        return IntentType::COMPLEX;
    }

    // 2. Query Power / Current / State
    if (VietnameseNormalizer::containsWord(normalized_text, "công suất") ||
        VietnameseNormalizer::containsWord(normalized_text, "tiêu thụ") ||
        VietnameseNormalizer::containsWord(normalized_text, "watt") ||
        VietnameseNormalizer::containsWord(normalized_text, "oát")) {
        return IntentType::QUERY_POWER;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "dòng điện") ||
        VietnameseNormalizer::containsWord(normalized_text, "ampe") ||
        VietnameseNormalizer::containsWord(normalized_text, "miliampe")) {
        return IntentType::QUERY_CURRENT;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "đang") ||
        VietnameseNormalizer::containsWord(normalized_text, "trạng thái") ||
        VietnameseNormalizer::containsWord(normalized_text, "đang bật hay tắt") ||
        VietnameseNormalizer::containsWord(normalized_text, "có đang bật") ||
        VietnameseNormalizer::containsWord(normalized_text, "có đang tắt") ||
        VietnameseNormalizer::containsWord(normalized_text, "kiểm tra")) {
        return IntentType::QUERY_STATE;
    }

    // 3. Temperature Setting
    if ((VietnameseNormalizer::containsWord(normalized_text, "nhiệt độ") ||
         VietnameseNormalizer::containsWord(normalized_text, "độ")) &&
        (VietnameseNormalizer::containsWord(normalized_text, "đặt") ||
         VietnameseNormalizer::containsWord(normalized_text, "chỉnh") ||
         VietnameseNormalizer::containsWord(normalized_text, "cài") ||
         VietnameseNormalizer::containsWord(normalized_text, "set"))) {
        return IntentType::SET_TEMPERATURE;
    }

    // 4. Increase / Decrease
    if (VietnameseNormalizer::containsWord(normalized_text, "tăng") ||
        VietnameseNormalizer::containsWord(normalized_text, "nâng") ||
        VietnameseNormalizer::containsWord(normalized_text, "mạnh hơn") ||
        VietnameseNormalizer::containsWord(normalized_text, "lớn hơn") ||
        VietnameseNormalizer::containsWord(normalized_text, "sáng hơn")) {
        return IntentType::INCREASE;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "giảm") ||
        VietnameseNormalizer::containsWord(normalized_text, "hạ") ||
        VietnameseNormalizer::containsWord(normalized_text, "yếu hơn") ||
        VietnameseNormalizer::containsWord(normalized_text, "nhỏ hơn") ||
        VietnameseNormalizer::containsWord(normalized_text, "tối hơn")) {
        return IntentType::DECREASE;
    }

    // 5. Turn ON / Turn OFF / Toggle / Stop
    if (VietnameseNormalizer::containsWord(normalized_text, "bật") ||
        VietnameseNormalizer::containsWord(normalized_text, "bật lên")) {
        return IntentType::TURN_ON;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "tắt") ||
        VietnameseNormalizer::containsWord(normalized_text, "tắt đi")) {
        return IntentType::TURN_OFF;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "đổi") ||
        VietnameseNormalizer::containsWord(normalized_text, "đảo") ||
        VietnameseNormalizer::containsWord(normalized_text, "chuyển")) {
        return IntentType::TOGGLE;
    }

    if (VietnameseNormalizer::containsWord(normalized_text, "dừng") ||
        VietnameseNormalizer::containsWord(normalized_text, "dừng lại") ||
        VietnameseNormalizer::containsWord(normalized_text, "ngừng") ||
        VietnameseNormalizer::containsWord(normalized_text, "thôi")) {
        return IntentType::STOP;
    }

    return IntentType::UNKNOWN;
}
