#pragma once
#include <stddef.h>
#include <stdint.h>

// Wire durations are little-endian uint16 in 10 us units, starting with a mark.
static inline bool ir_valid_wave(const uint16_t* ticks, size_t count, uint32_t frequency) {
    if (!ticks || count < 4 || count > 1024 || frequency < 20000 || frequency > 60000) return false;
    uint32_t total = 0;
    for (size_t i = 0; i < count; ++i) {
        if (ticks[i] < 5 || ticks[i] > (i % 2 ? 20000 : 2000)) return false;
        total += ticks[i];
    }
    return total <= 120000;
}
