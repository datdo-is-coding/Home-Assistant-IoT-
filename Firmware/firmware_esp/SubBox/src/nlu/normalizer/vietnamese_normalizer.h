#pragma once

#include <string>

class VietnameseNormalizer {
public:

    static std::string normalize(const std::string& input);

    static bool containsWord(const std::string& haystack, const std::string& needle);

    static std::string replaceAll(std::string str, const std::string& from, const std::string& to);
};
