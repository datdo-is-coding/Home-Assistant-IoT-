#pragma once

#include <vector>
#include <stdint.h>

class TTSEngine {
public:
    virtual ~TTSEngine() = default;

    virtual bool init() = 0;

    virtual bool synthesize(const char* text, std::vector<int16_t>& pcm_out) = 0;
};
