#include <cassert>
#include <cstdio>
#include <cstring>
#include "../firmware_esp/common/device_lifecycle.h"

int main() {
    // 1. Channel counts
    assert(get_channel_count("actionbox_v1") == 2);
    assert(get_channel_count("actionbox_v2") == 3);
    assert(get_channel_count("subbox_v1") == 0);
    assert(get_channel_count("unknown_box") == -1);
    assert(is_supported_board_model("actionbox_v1"));
    assert(is_supported_board_model("actionbox_v2"));
    assert(is_supported_board_model("subbox_v1"));
    assert(!is_supported_board_model("quantum_box_v99"));

    // 2. Constants
    assert(WIRE_V2_MAX_FRAME_LEN == 250);
    assert(WIRE_V2_MAX_CHUNK_LEN == 160);
    assert(WIRE_V2_MAX_CONFIG_LEN == 4096);
    assert(WIRE_V2_REASSEMBLY_TIMEOUT_MS == 10000);
    assert(WIRE_V2_MAX_CONCURRENT_OPS_ACTIONBOX == 1);
    assert(WIRE_V2_MAX_CONCURRENT_OPS_SUBBOX == 2);

    // 3. Validation
    assert(validate_chunk_size(160));
    assert(!validate_chunk_size(161));
    assert(validate_config_size(4096));
    assert(!validate_config_size(4097));

    // 4. Standard IEEE 802.3 CRC32 check vector: "123456789" -> 0xCBF43926
    const char* test_vec = "123456789";
    uint32_t crc = calculate_crc32(reinterpret_cast<const uint8_t*>(test_vec), strlen(test_vec));
    assert(crc == 0xCBF43926);

    // 5. Descriptor validation
    DeviceDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    strncpy(desc.device_uid, "ab2_001", sizeof(desc.device_uid) - 1);
    strncpy(desc.board_model, "actionbox_v2", sizeof(desc.board_model) - 1);
    strncpy(desc.board_revision, "v2.0", sizeof(desc.board_revision) - 1);
    desc.protocol_version = 2;
    strncpy(desc.capabilities, "relay,energy_meter,voice", sizeof(desc.capabilities) - 1);
    strncpy(desc.home_id, "home_01", sizeof(desc.home_id) - 1);
    desc.owner_epoch = 5;
    strncpy(desc.boot_id, "boot_01", sizeof(desc.boot_id) - 1);
    desc.config_revision = 1;

    const char* err = nullptr;
    assert(validate_device_descriptor(desc, 5, &err));
    assert(strcmp(desc.capabilities, "relay,energy_meter,voice") == 0);

    // Reject old epoch
    assert(!validate_device_descriptor(desc, 6, &err));
    assert(strcmp(err, "OLD_EPOCH") == 0);

    // Reject unsupported protocol
    desc.protocol_version = 1;
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "UNSUPPORTED_PROTOCOL") == 0);
    desc.protocol_version = 2;

    // Reject unknown model
    strncpy(desc.board_model, "unknown_board", sizeof(desc.board_model) - 1);
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "UNKNOWN_MODEL") == 0);
    strncpy(desc.board_model, "actionbox_v2", sizeof(desc.board_model) - 1);

    // Reject empty device_uid
    desc.device_uid[0] = '\0';
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "EMPTY_UID") == 0);
    strncpy(desc.device_uid, "ab2_001", sizeof(desc.device_uid) - 1);

    // Reject non-null-terminated device_uid (string overflow defense)
    memset(desc.device_uid, 'A', sizeof(desc.device_uid));
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "EMPTY_UID") == 0);
    memset(desc.device_uid, 0, sizeof(desc.device_uid));
    strncpy(desc.device_uid, "ab2_001", sizeof(desc.device_uid) - 1);

    // Reject non-null-terminated board_model (string overflow defense)
    memset(desc.board_model, 'B', sizeof(desc.board_model));
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "UNKNOWN_MODEL") == 0);
    memset(desc.board_model, 0, sizeof(desc.board_model));
    strncpy(desc.board_model, "actionbox_v2", sizeof(desc.board_model) - 1);

    // Reject non-null-terminated home_id (string overflow defense)
    memset(desc.home_id, 'H', sizeof(desc.home_id));
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "INVALID_HOME_ID") == 0);
    memset(desc.home_id, 0, sizeof(desc.home_id));
    strncpy(desc.home_id, "home_01", sizeof(desc.home_id) - 1);

    // Reject non-null-terminated boot_id (string overflow defense)
    memset(desc.boot_id, 'X', sizeof(desc.boot_id));
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "INVALID_BOOT_ID") == 0);
    memset(desc.boot_id, 0, sizeof(desc.boot_id));
    strncpy(desc.boot_id, "boot_01", sizeof(desc.boot_id) - 1);

    // Reject non-null-terminated capabilities (string overflow defense)
    memset(desc.capabilities, 'C', sizeof(desc.capabilities));
    assert(!validate_device_descriptor(desc, 5, &err));
    assert(strcmp(err, "INVALID_CAPABILITIES") == 0);
    memset(desc.capabilities, 0, sizeof(desc.capabilities));
    strncpy(desc.capabilities, "relay,energy_meter,voice", sizeof(desc.capabilities) - 1);

    // 6. LED pattern priorities
    // Fault overrides all
    LedPattern p = resolve_device_led_pattern(
        LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::RELAY_WELDED,
        true, OperationKind::IDENTIFY, OperationState::RUNNING
    );
    assert(p == LedPattern::FAULT);

    // Reset confirmation overrides setup/claim, identify
    p = resolve_device_led_pattern(
        LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE,
        true, OperationKind::FACTORY_RESET, OperationState::AWAITING_CONFIRMATION
    );
    assert(p == LedPattern::AWAITING_FACTORY_RESET);

    p = resolve_device_led_pattern(
        LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE,
        true, OperationKind::NETWORK_RESET, OperationState::AWAITING_CONFIRMATION
    );
    assert(p == LedPattern::AWAITING_NETWORK_RESET);

    // Claiming / Unclaimed
    p = resolve_device_led_pattern(LifecycleState::CLAIMING, ConnectivityState::UNKNOWN);
    assert(p == LedPattern::CLAIMING);

    p = resolve_device_led_pattern(LifecycleState::UNCLAIMED, ConnectivityState::UNKNOWN);
    assert(p == LedPattern::UNCLAIMED);

    // Identify
    p = resolve_device_led_pattern(
        LifecycleState::CLAIMED, ConnectivityState::OFFLINE, FaultKind::NONE,
        true, OperationKind::IDENTIFY, OperationState::RUNNING, 3000
    );
    assert(p == LedPattern::IDENTIFY);

    // Offline
    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::OFFLINE);
    assert(p == LedPattern::OFFLINE);

    // Ready solid 2s then OFF (persisting OFF at 2000ms, 2500ms, 3000ms, 5000ms)
    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE, false, OperationKind::IDENTIFY, OperationState::RUNNING, 1000);
    assert(p == LedPattern::READY);

    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE, false, OperationKind::IDENTIFY, OperationState::RUNNING, 2000);
    assert(p == LedPattern::OFF);

    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE, false, OperationKind::IDENTIFY, OperationState::RUNNING, 2500);
    assert(p == LedPattern::OFF);

    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE, false, OperationKind::IDENTIFY, OperationState::RUNNING, 3000);
    assert(p == LedPattern::OFF);

    p = resolve_device_led_pattern(LifecycleState::CLAIMED, ConnectivityState::ONLINE, FaultKind::NONE, false, OperationKind::IDENTIFY, OperationState::RUNNING, 5000);
    assert(p == LedPattern::OFF);

    // 7. Status LED timing waveforms
    assert(status_led_is_active(LedPattern::UNCLAIMED, 0));
    assert(status_led_is_active(LedPattern::UNCLAIMED, 400));
    assert(!status_led_is_active(LedPattern::UNCLAIMED, 500));
    assert(!status_led_is_active(LedPattern::UNCLAIMED, 900));
    assert(status_led_is_active(LedPattern::UNCLAIMED, 1000));

    assert(status_led_is_active(LedPattern::READY, 0));
    assert(status_led_is_active(LedPattern::READY, 1999));
    assert(!status_led_is_active(LedPattern::READY, 2000));

    // 8. Button classification boundary timings
    // < 40ms -> Debounce filter (NONE)
    assert(classify_release(0, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(39, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(39, false, ArmedKind::NONE, false) == ButtonAction::NONE);

    // 40ms..699ms -> SHORT_PRESS
    assert(classify_release(40, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_release(100, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_release(699, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_release(40, false, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_release(699, false, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);

    // 700ms..2999ms -> NONE (deadzone between short press and reboot)
    assert(classify_release(700, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(1500, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(2999, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(700, false, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(2999, false, ArmedKind::NONE, false) == ButtonAction::NONE);

    // 3000ms..4999ms -> REBOOT
    assert(classify_release(3000, true, ArmedKind::NONE, false) == ButtonAction::REBOOT);
    assert(classify_release(4000, true, ArmedKind::NONE, false) == ButtonAction::REBOOT);
    assert(classify_release(4999, true, ArmedKind::NONE, false) == ButtonAction::REBOOT);
    assert(classify_release(3000, false, ArmedKind::NONE, false) == ButtonAction::REBOOT);
    assert(classify_release(4999, false, ArmedKind::NONE, false) == ButtonAction::REBOOT);

    // 5000ms..9999ms -> Unclaimed: START_SETUP; Claimed: ARM_NETWORK_RESET
    assert(classify_release(5000, false, ArmedKind::NONE, false) == ButtonAction::START_SETUP);
    assert(classify_release(7500, false, ArmedKind::NONE, false) == ButtonAction::START_SETUP);
    assert(classify_release(9999, false, ArmedKind::NONE, false) == ButtonAction::START_SETUP);

    assert(classify_release(5000, true, ArmedKind::NONE, false) == ButtonAction::ARM_NETWORK_RESET);
    assert(classify_release(7500, true, ArmedKind::NONE, false) == ButtonAction::ARM_NETWORK_RESET);
    assert(classify_release(9999, true, ArmedKind::NONE, false) == ButtonAction::ARM_NETWORK_RESET);

    // 10000ms..19999ms -> ARM_FACTORY_RESET
    assert(classify_release(10000, true, ArmedKind::NONE, false) == ButtonAction::ARM_FACTORY_RESET);
    assert(classify_release(15000, true, ArmedKind::NONE, false) == ButtonAction::ARM_FACTORY_RESET);
    assert(classify_release(19999, true, ArmedKind::NONE, false) == ButtonAction::ARM_FACTORY_RESET);
    assert(classify_release(10000, false, ArmedKind::NONE, false) == ButtonAction::ARM_FACTORY_RESET);
    assert(classify_release(19999, false, ArmedKind::NONE, false) == ButtonAction::ARM_FACTORY_RESET);

    // >= 20000ms -> Abort / Stuck held discard (NONE)
    assert(classify_release(20000, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(25000, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(20000, false, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_release(60000, false, ArmedKind::NONE, false) == ButtonAction::NONE);

    // 9. Arm + Confirm flow (Armed state converts short press to CONFIRM_RESET)
    assert(classify_release(40, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CONFIRM_RESET);
    assert(classify_release(200, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CONFIRM_RESET);
    assert(classify_release(699, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CONFIRM_RESET);

    assert(classify_release(40, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::CONFIRM_RESET);
    assert(classify_release(350, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::CONFIRM_RESET);
    assert(classify_release(699, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::CONFIRM_RESET);

    // 10. Arm + Timeout flow
    uint64_t armed_at = 10000;
    assert(!is_armed_timed_out(armed_at, armed_at, 5000));
    assert(!is_armed_timed_out(armed_at + 1000, armed_at, 5000));
    assert(!is_armed_timed_out(armed_at + 4999, armed_at, 5000));
    assert(is_armed_timed_out(armed_at + 5000, armed_at, 5000));
    assert(is_armed_timed_out(armed_at + 5001, armed_at, 5000));
    assert(is_armed_timed_out(armed_at + 10000, armed_at, 5000));

    // 11. Arm + Cancel flow (Pressing >= 700ms while armed cancels the armed state)
    assert(classify_release(700, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CANCEL_ARMED);
    assert(classify_release(1200, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CANCEL_ARMED);
    assert(classify_release(3000, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::CANCEL_ARMED);
    assert(classify_release(700, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::CANCEL_ARMED);
    assert(classify_release(5000, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::CANCEL_ARMED);

    // 12. Stuck button at boot (Must be released and ignored until fresh press)
    assert(classify_release(40, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_release(200, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_release(3000, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_release(5000, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_release(10000, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_release(25000, true, ArmedKind::NONE, true) == ButtonAction::NONE);

    // 13. LED Waveform Traces: FAULT (4 pulses of 200ms ON / 200ms OFF every 3600ms)
    // Pulse 1: 0..199 ON, 200..399 OFF
    assert(status_led_is_active(LedPattern::FAULT, 0));
    assert(status_led_is_active(LedPattern::FAULT, 100));
    assert(status_led_is_active(LedPattern::FAULT, 199));
    assert(!status_led_is_active(LedPattern::FAULT, 200));
    assert(!status_led_is_active(LedPattern::FAULT, 399));
    // Pulse 2: 400..599 ON, 600..799 OFF
    assert(status_led_is_active(LedPattern::FAULT, 400));
    assert(status_led_is_active(LedPattern::FAULT, 599));
    assert(!status_led_is_active(LedPattern::FAULT, 600));
    assert(!status_led_is_active(LedPattern::FAULT, 799));
    // Pulse 3: 800..999 ON, 1000..1199 OFF
    assert(status_led_is_active(LedPattern::FAULT, 800));
    assert(status_led_is_active(LedPattern::FAULT, 999));
    assert(!status_led_is_active(LedPattern::FAULT, 1000));
    assert(!status_led_is_active(LedPattern::FAULT, 1199));
    // Pulse 4: 1200..1399 ON, 1400..3599 OFF (long quiet period)
    assert(status_led_is_active(LedPattern::FAULT, 1200));
    assert(status_led_is_active(LedPattern::FAULT, 1399));
    assert(!status_led_is_active(LedPattern::FAULT, 1400));
    assert(!status_led_is_active(LedPattern::FAULT, 2000));
    assert(!status_led_is_active(LedPattern::FAULT, 3599));
    // Cycle repetition: 3600 ON
    assert(status_led_is_active(LedPattern::FAULT, 3600));
    assert(status_led_is_active(LedPattern::FAULT, 3799));
    assert(!status_led_is_active(LedPattern::FAULT, 3800));

    // 14. LED Waveform Traces: AWAITING_FACTORY_RESET (5 pulses of 200ms ON / 200ms OFF every 3000ms)
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 0));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 199));
    assert(!status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 200));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 400));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 800));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 1200));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 1600));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 1799));
    assert(!status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 1800));
    assert(!status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 2999));
    assert(status_led_is_active(LedPattern::AWAITING_FACTORY_RESET, 3000));

    // 15. LED Waveform Traces: AWAITING_NETWORK_RESET (3 pulses of 200ms ON / 200ms OFF every 2200ms)
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 0));
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 199));
    assert(!status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 200));
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 400));
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 800));
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 999));
    assert(!status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 1000));
    assert(!status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 2199));
    assert(status_led_is_active(LedPattern::AWAITING_NETWORK_RESET, 2200));

    // 16. Button 2 (Voice PTT) classification: BUT2 held >= 700ms triggers VOICE_TRIGGER
    // Debounce filter
    assert(classify_actionbox_button(2, 0, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_actionbox_button(2, 39, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    // Short press (< 700ms)
    assert(classify_actionbox_button(2, 40, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_actionbox_button(2, 350, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_actionbox_button(2, 699, true, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    assert(classify_actionbox_button(2, 40, false, ArmedKind::NONE, false) == ButtonAction::SHORT_PRESS);
    // Voice trigger (>= 700ms and < 20000ms)
    assert(classify_actionbox_button(2, 700, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 1000, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 3000, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 5000, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 10000, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 19999, true, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    // Unclaimed device BUT2 >= 700ms still triggers VOICE_TRIGGER
    assert(classify_actionbox_button(2, 700, false, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 5000, false, ArmedKind::NONE, false) == ButtonAction::VOICE_TRIGGER);
    // Even if armed reset is somehow active, BUT2 NEVER confirms or resets - always voice trigger
    assert(classify_actionbox_button(2, 700, true, ArmedKind::FACTORY_RESET, false) == ButtonAction::VOICE_TRIGGER);
    assert(classify_actionbox_button(2, 700, true, ArmedKind::NETWORK_RESET, false) == ButtonAction::VOICE_TRIGGER);
    // Stuck held discard (>= 20000ms)
    assert(classify_actionbox_button(2, 20000, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    assert(classify_actionbox_button(2, 25000, true, ArmedKind::NONE, false) == ButtonAction::NONE);
    // Stuck boot discard
    assert(classify_actionbox_button(2, 700, true, ArmedKind::NONE, true) == ButtonAction::NONE);
    assert(classify_actionbox_button(2, 5000, true, ArmedKind::NONE, true) == ButtonAction::NONE);

    // 17. SubBox LED Online state non-oscillation simulation
    int64_t sbox_online_entered_us = 0;
    int64_t sbox_pattern_start_us = 0;
    LedPattern sbox_prev_pattern = LedPattern::OFF;
    int pattern_change_count = 0;

    // Simulate tick every 50ms from t=0 to t=5000ms
    for (int64_t t_ms = 0; t_ms <= 5000; t_ms += 50) {
        int64_t now_us = 1000000LL + t_ms * 1000;
        LifecycleState lifecycle = LifecycleState::CLAIMED;
        ConnectivityState connectivity = ConnectivityState::ONLINE;
        FaultKind fault = FaultKind::NONE;

        if (connectivity == ConnectivityState::ONLINE && lifecycle == LifecycleState::CLAIMED) {
            if (sbox_online_entered_us == 0) sbox_online_entered_us = now_us;
        } else {
            sbox_online_entered_us = 0;
        }
        uint64_t elapsed_in_online = (sbox_online_entered_us > 0)
                                   ? (uint64_t)((now_us - sbox_online_entered_us) / 1000) : 0;

        LedPattern pattern = resolve_device_led_pattern(
            lifecycle, connectivity, fault, false, OperationKind::IDENTIFY,
            OperationState::RUNNING, elapsed_in_online
        );

        if (pattern != sbox_prev_pattern) {
            sbox_prev_pattern = pattern;
            sbox_pattern_start_us = now_us;
            pattern_change_count++;
        }

        if (t_ms < 2000) {
            assert(pattern == LedPattern::READY);
        } else {
            // >= 2000ms: pattern is OFF and stays OFF at 2000, 2500, 3000, 5000ms
            assert(pattern == LedPattern::OFF);
        }
    }
    // Expected transitions: 1st tick transitions OFF -> READY, at 2000ms transitions READY -> OFF.
    // Total pattern changes must be exactly 2 (never oscillates back to READY).
    assert(pattern_change_count == 2);
    assert(sbox_prev_pattern == LedPattern::OFF);

    printf("ALL HOST TESTS PASSED\n");
    return 0;
}
