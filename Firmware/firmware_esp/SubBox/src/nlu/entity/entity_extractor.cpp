/**
 * @file entity_extractor.cpp
 * @brief Vietnamese Entity Extractor Implementation
 */

#include "entity_extractor.h"
#include "nlu/normalizer/vietnamese_normalizer.h"
#include <cstdlib>
#include <cctype>

DeviceType EntityExtractor::extractDevice(const std::string& text) {
    if (VietnameseNormalizer::containsWord(text, "điều hòa") ||
        VietnameseNormalizer::containsWord(text, "máy lạnh") ||
        VietnameseNormalizer::containsWord(text, "nhiệt độ") ||
        VietnameseNormalizer::containsWord(text, "ac")) {
        return DeviceType::AIR_CONDITIONER;
    }

    if (VietnameseNormalizer::containsWord(text, "quạt") ||
        VietnameseNormalizer::containsWord(text, "quạt trần") ||
        VietnameseNormalizer::containsWord(text, "quạt cây") ||
        VietnameseNormalizer::containsWord(text, "quạt đứng") ||
        VietnameseNormalizer::containsWord(text, "quạt thông gió")) {
        return DeviceType::FAN;
    }

    if (VietnameseNormalizer::containsWord(text, "đèn") ||
        VietnameseNormalizer::containsWord(text, "bóng đèn") ||
        VietnameseNormalizer::containsWord(text, "đèn ngủ") ||
        VietnameseNormalizer::containsWord(text, "đèn chùm") ||
        VietnameseNormalizer::containsWord(text, "chiếu sáng")) {
        return DeviceType::LIGHT;
    }

    if (VietnameseNormalizer::containsWord(text, "ổ cắm") ||
        VietnameseNormalizer::containsWord(text, "công tắc") ||
        VietnameseNormalizer::containsWord(text, "nguồn")) {
        return DeviceType::SOCKET;
    }

    if (VietnameseNormalizer::containsWord(text, "thiết bị")) {
        return DeviceType::OTHER;
    }

    return DeviceType::NONE;
}

RoomType EntityExtractor::extractRoom(const std::string& text) {
    if (VietnameseNormalizer::containsWord(text, "phòng khách")) {
        return RoomType::LIVING_ROOM;
    }

    if (VietnameseNormalizer::containsWord(text, "phòng ngủ")) {
        return RoomType::BEDROOM;
    }

    if (VietnameseNormalizer::containsWord(text, "phòng bếp") ||
        VietnameseNormalizer::containsWord(text, "nhà bếp") ||
        VietnameseNormalizer::containsWord(text, "bếp")) {
        return RoomType::KITCHEN;
    }

    if (VietnameseNormalizer::containsWord(text, "ban công")) {
        return RoomType::BALCONY;
    }

    if (VietnameseNormalizer::containsWord(text, "hiên") ||
        VietnameseNormalizer::containsWord(text, "hành lang")) {
        return RoomType::PORCH;
    }

    if (VietnameseNormalizer::containsWord(text, "sân") ||
        VietnameseNormalizer::containsWord(text, "vườn") ||
        VietnameseNormalizer::containsWord(text, "ngoài trời")) {
        return RoomType::OUTDOOR;
    }

    return RoomType::UNSPECIFIED;
}

bool EntityExtractor::extractNumericValue(const std::string& text, float& out_val) {
    // 1. Scan for explicit digit sequences (e.g. "25", "26.5", "100")
    for (size_t i = 0; i < text.length(); ++i) {
        if (std::isdigit(static_cast<unsigned char>(text[i]))) {
            char* end_ptr = nullptr;
            float val = std::strtof(&text[i], &end_ptr);
            if (end_ptr != &text[i]) {
                out_val = val;
                return true;
            }
        }
    }

    // 2. Scan for common Vietnamese spoken numbers (16 - 32 for temperatures)
    static const struct {
        const char* word;
        float val;
    } spoken_numbers[] = {
        {"mười sáu", 16.0f}, {"mười bảy", 17.0f}, {"mười tám", 18.0f}, {"mười chín", 19.0f},
        {"hai mươi", 20.0f}, {"hai mốt", 21.0f}, {"hai hai", 22.0f}, {"hai ba", 23.0f},
        {"hai tư", 24.0f}, {"hai bốn", 24.0f}, {"hai lăm", 25.0f}, {"hai năm", 25.0f},
        {"hai sáu", 26.0f}, {"hai bảy", 27.0f}, {"hai tám", 28.0f}, {"hai chín", 29.0f},
        {"ba mươi", 30.0f}, {"một", 1.0f}, {"hai", 2.0f}, {"ba", 3.0f}, {"bốn", 4.0f},
        {"năm", 5.0f}, {"mười", 10.0f}
    };

    for (const auto& item : spoken_numbers) {
        if (text.find(item.word) != std::string::npos) {
            out_val = item.val;
            return true;
        }
    }

    return false;
}

ParsedEntities EntityExtractor::extract(const std::string& normalized_text) {
    ParsedEntities entities;
    entities.device = extractDevice(normalized_text);
    entities.room = extractRoom(normalized_text);
    entities.has_numeric_value = extractNumericValue(normalized_text, entities.numeric_value);
    if (entities.has_numeric_value) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%.1f", entities.numeric_value);
        entities.raw_value_str = buf;
    } else {
        entities.raw_value_str = "";
    }
    return entities;
}
