/**
 * @file vietnamese_normalizer.h
 * @brief Deterministic Vietnamese Text Normalizer for Edge ASR Output
 */

#pragma once

#include <string>

class VietnameseNormalizer {
public:
    /**
     * @brief Normalize raw ASR Vietnamese text
     * Performs:
     * - Lowercase UTF-8 mapping
     * - Punctuation stripping
     * - Whitespace compression & trimming
     * - Common ASR and dialect canonicalization:
     *   "điều hoà" -> "điều hòa"
     *   "mở" -> "bật"
     *   "đóng" -> "tắt"
     * @param input Raw text string from speech recognizer
     * @return Cleaned, canonicalized string
     */
    static std::string normalize(const std::string& input);

    /**
     * @brief Check if string contains a specific whole word or sub-phrase
     */
    static bool containsWord(const std::string& haystack, const std::string& needle);

    /**
     * @brief Replace all occurrences of search string with replacement
     */
    static std::string replaceAll(std::string str, const std::string& from, const std::string& to);
};
