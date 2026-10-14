#pragma once
#include <cstdint>

// 0: ready; otherwise N short pulses followed by a two-second dark gap.
inline bool status_led_level(unsigned code, uint64_t elapsed_ms) {
    if (code == 0) return elapsed_ms % 200 < 100;
    const auto phase = elapsed_ms % (code * 400 + 2000);
    return phase < code * 400 && phase % 400 < 200;
}
inline unsigned subbox_status(bool wifi, bool configured, bool mqtt, bool peer, bool fault) {
    if (fault) return 5;
    if (!wifi) return 1;
    if (!configured) return 2;
    if (!mqtt) return 3;
    return peer ? 0 : 4;
}
