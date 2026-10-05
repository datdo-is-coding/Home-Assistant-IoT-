#include <cassert>
#include "../firmware_esp/common/connection_status.h"
int main() {
    // Wi-Fi alone must never signal end-to-end readiness.
    assert(subbox_status(false, false, false, false, false) == 1);
    assert(subbox_status(true, false, false, false, false) == 2);
    assert(subbox_status(true, true, false, true, false) == 3);
    assert(subbox_status(true, true, true, false, false) == 4);
    assert(subbox_status(true, true, true, true, false) == 0);
    assert(subbox_status(true, true, true, true, true) == 5);
    // Two pulses, then a long dark gap. No overlap between error codes.
    assert(status_led_level(2, 0));
    assert(!status_led_level(2, 200));
    assert(status_led_level(2, 400));
    assert(!status_led_level(2, 800));
    assert(!status_led_level(2, 1800));
    assert(status_led_level(2, 2800));
    assert(status_led_level(0, 0));
    assert(!status_led_level(0, 100));
}
