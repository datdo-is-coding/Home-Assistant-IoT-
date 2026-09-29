/**
 * @file vietnamese_normalizer.cpp
 * @brief Deterministic Vietnamese Text Normalizer Implementation
 */

#include "vietnamese_normalizer.h"
#include <algorithm>
#include <cctype>
#include <utility>

std::string VietnameseNormalizer::replaceAll(std::string str, const std::string& from, const std::string& to) {
    if (from.empty()) return str;
    size_t start_pos = 0;
    while ((start_pos = str.find(from, start_pos)) != std::string::npos) {
        str.replace(start_pos, from.length(), to);
        start_pos += to.length();
    }
    return str;
}

bool VietnameseNormalizer::containsWord(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return true;
    size_t pos = haystack.find(needle);
    while (pos != std::string::npos) {
        bool left_boundary = (pos == 0 || haystack[pos - 1] == ' ');
        bool right_boundary = (pos + needle.length() == haystack.length() || haystack[pos + needle.length()] == ' ');
        if (left_boundary && right_boundary) return true;
        pos = haystack.find(needle, pos + 1);
    }
    return false;
}

std::string VietnameseNormalizer::normalize(const std::string& input) {
    if (input.empty()) return "";

    std::string text = input;

    // 1. Lowercase standard ASCII
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) {
        return std::tolower(c);
    });

    // 2. Map uppercase UTF-8 Vietnamese accented characters to lowercase equivalents
    static const struct {
        const char* upper;
        const char* lower;
    } utf8_cases[] = {
        {"À", "à"}, {"Á", "á"}, {"Ả", "ả"}, {"Ã", "ã"}, {"Ạ", "ạ"},
        {"Ă", "ă"}, {"Ằ", "ằ"}, {"Ắ", "ắ"}, {"Ẳ", "ẳ"}, {"Ẵ", "ẵ"}, {"Ặ", "ặ"},
        {"Â", "â"}, {"Ầ", "ầ"}, {"Ấ", "ấ"}, {"Ẩ", "ẩ"}, {"Ẫ", "ẫ"}, {"Ậ", "ậ"},
        {"Đ", "đ"},
        {"È", "è"}, {"É", "é"}, {"Ẻ", "ẻ"}, {"Ẽ", "ẽ"}, {"Ẹ", "ẹ"},
        {"Ê", "ê"}, {"Ề", "ề"}, {"Ế", "ế"}, {"Ể", "ể"}, {"Ễ", "ễ"}, {"Ệ", "ệ"},
        {"Ì", "ì"}, {"Í", "í"}, {"Ỉ", "ỉ"}, {"Ĩ", "ĩ"}, {"Ị", "ị"},
        {"Ò", "ò"}, {"Ó", "ó"}, {"Ỏ", "ỏ"}, {"Õ", "õ"}, {"Ọ", "ọ"},
        {"Ô", "ô"}, {"Ồ", "ồ"}, {"Ố", "ố"}, {"Ổ", "ổ"}, {"Ỗ", "ỗ"}, {"Ộ", "ộ"},
        {"Ơ", "ơ"}, {"Ờ", "ờ"}, {"Ớ", "ớ"}, {"Ở", "ở"}, {"Ỡ", "ỡ"}, {"Ợ", "ợ"},
        {"Ù", "ù"}, {"Ú", "ú"}, {"Ủ", "ủ"}, {"Ũ", "ũ"}, {"Ụ", "ụ"},
        {"Ư", "ư"}, {"Ừ", "ừ"}, {"Ứ", "ứ"}, {"Ử", "ử"}, {"Ữ", "ữ"}, {"Ự", "ự"},
        {"Ỳ", "ỳ"}, {"Ý", "ý"}, {"Ỷ", "ỷ"}, {"Ỹ", "ỹ"}, {"Ỵ", "ỵ"}
    };

    for (const auto& pair : utf8_cases) {
        text = replaceAll(std::move(text), pair.upper, pair.lower);
    }

    // 3. Remove punctuation (.,!?:;'"~-()[]{}/*+\\)
    const std::string punctuation = ".,!?:;'\"~-()[]{}/=*+\\_#@$%^&";
    for (char p : punctuation) {
        std::replace(text.begin(), text.end(), p, ' ');
    }

    // 4. Compress multiple consecutive spaces into single space and trim edges
    std::string cleaned;
    cleaned.reserve(text.size());
    bool last_was_space = true; // Treats leading space as already encountered
    for (char c : text) {
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
            if (!last_was_space) {
                cleaned += ' ';
                last_was_space = true;
            }
        } else {
            cleaned += c;
            last_was_space = false;
        }
    }

    // Trim trailing space
    if (!cleaned.empty() && cleaned.back() == ' ') {
        cleaned.pop_back();
    }

    // 5. Canonicalize Vietnamese ASR dialect and verb variants
    // "máy lạnh" -> "điều hòa"
    cleaned = replaceAll(std::move(cleaned), "máy lạnh", "điều hòa");
    // "điều hoà" -> "điều hòa"
    cleaned = replaceAll(std::move(cleaned), "điều hoà", "điều hòa");
    // "mở" -> "bật"
    cleaned = replaceAll(std::move(cleaned), " mở ", " bật ");
    if (cleaned.rfind("mở ", 0) == 0) cleaned.replace(0, std::string("mở ").size(), "bật ");
    // "ngắt" -> "tắt"
    cleaned = replaceAll(std::move(cleaned), " ngắt ", " tắt ");
    if (cleaned.rfind("ngắt ", 0) == 0) cleaned.replace(0, std::string("ngắt ").size(), "tắt ");

    return cleaned;
}
