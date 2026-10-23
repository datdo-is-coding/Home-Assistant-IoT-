#pragma once

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>

// Wire v2 Limits
constexpr size_t WIRE_V2_MAX_FRAME_LEN = 250;
constexpr size_t WIRE_V2_MAX_CHUNK_LEN = 160;
constexpr size_t WIRE_V2_MAX_CONFIG_LEN = 4096;
constexpr uint32_t WIRE_V2_REASSEMBLY_TIMEOUT_MS = 10000;
constexpr int WIRE_V2_MAX_CONCURRENT_OPS_ACTIONBOX = 1;
constexpr int WIRE_V2_MAX_CONCURRENT_OPS_SUBBOX = 2;

enum class LifecycleState : uint8_t {
    UNCLAIMED = 0,
    CLAIMING = 1,
    CLAIMED = 2,
    RESETTING = 3,
    DECOMMISSIONED = 4
};

enum class ConnectivityState : uint8_t {
    UNKNOWN = 0,
    CONNECTING = 1,
    ONLINE = 2,
    OFFLINE = 3
};

enum class FaultKind : uint8_t {
    NONE = 0,
    OVER_CURRENT = 1,
    OVER_TEMPERATURE = 2,
    RELAY_WELDED = 3,
    METER_FAULT = 4,
    SYSTEM_FAULT = 5
};

enum class OperationKind : uint8_t {
    IDENTIFY = 0,
    REBOOT = 1,
    NETWORK_RESET = 2,
    FACTORY_RESET = 3,
    REMOVE_FROM_HOME = 4,
    CONFIGURE = 5
};

enum class OperationState : uint8_t {
    ACCEPTED = 0,
    AWAITING_CONFIRMATION = 1,
    RUNNING = 2,
    AWAITING_RECONNECT = 3,
    SUCCEEDED = 4,
    FAILED = 5,
    TIMED_OUT = 6
};

enum class LedPattern : uint8_t {
    FAULT = 0,
    AWAITING_FACTORY_RESET = 1,
    AWAITING_NETWORK_RESET = 2,
    CLAIMING = 3,
    CONFIG_APPLYING = 4,
    UNCLAIMED = 5,
    IDENTIFY = 6,
    OFFLINE = 7,
    CONNECTING = 8,
    READY = 9,
    OFF = 10
};

enum class ButtonAction : uint8_t {
    NONE = 0,
    SHORT_PRESS = 1,
    REBOOT = 2,
    START_SETUP = 3,
    ARM_NETWORK_RESET = 4,
    ARM_FACTORY_RESET = 5,
    CONFIRM_RESET = 6,
    CANCEL_ARMED = 7,
    VOICE_TRIGGER = 8
};

enum class ArmedKind : uint8_t {
    NONE = 0,
    NETWORK_RESET = 1,
    FACTORY_RESET = 2
};

inline ButtonAction classify_release(uint64_t held_ms, bool is_claimed, ArmedKind armed_kind, bool is_stuck_boot = false) {
    if (is_stuck_boot) {
        return ButtonAction::NONE;
    }
    if (held_ms < 40 || held_ms >= 20000) {
        return ButtonAction::NONE;
    }
    if (armed_kind != ArmedKind::NONE) {
        if (held_ms < 700) {
            return ButtonAction::CONFIRM_RESET;
        }
        return ButtonAction::CANCEL_ARMED;
    }
    if (held_ms < 700) {
        return ButtonAction::SHORT_PRESS;
    }
    if (held_ms < 3000) {
        return ButtonAction::NONE;
    }
    if (held_ms < 5000) {
        return ButtonAction::REBOOT;
    }
    if (held_ms < 10000) {
        return is_claimed ? ButtonAction::ARM_NETWORK_RESET : ButtonAction::START_SETUP;
    }
    return ButtonAction::ARM_FACTORY_RESET;
}

inline ButtonAction classify_actionbox_button(uint8_t channel, uint64_t held_ms, bool is_claimed, ArmedKind armed_kind, bool is_stuck_boot = false) {
    if (channel == 2) {
        if (is_stuck_boot || held_ms < 40 || held_ms >= 20000) {
            return ButtonAction::NONE;
        }
        if (held_ms < 700) {
            return ButtonAction::SHORT_PRESS;
        }
        return ButtonAction::VOICE_TRIGGER;
    }
    return classify_release(held_ms, is_claimed, armed_kind, is_stuck_boot);
}

inline bool is_armed_timed_out(uint64_t current_ms, uint64_t armed_at_ms, uint64_t timeout_ms = 5000) {
    return (current_ms >= armed_at_ms) && ((current_ms - armed_at_ms) >= timeout_ms);
}

inline int get_channel_count(const char* board_model) {
    if (board_model == nullptr) return -1;
    if (strcmp(board_model, "actionbox_v1") == 0 || strcmp(board_model, "ActionBox_V1") == 0) return 2;
    if (strcmp(board_model, "actionbox_v2") == 0 || strcmp(board_model, "ActionBox_V2") == 0 || strcmp(board_model, "ActionBox") == 0) return 3;
    if (strcmp(board_model, "subbox_v1") == 0 || strcmp(board_model, "subbox") == 0 || strcmp(board_model, "SubBox") == 0) return 0;
    return -1;
}

inline bool is_supported_board_model(const char* board_model) {
    return get_channel_count(board_model) >= 0;
}

inline uint32_t calculate_crc32(const uint8_t* data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; ++i) {
        uint8_t byte = data[i];
        crc ^= byte;
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

inline bool validate_chunk_size(size_t chunk_len) {
    return chunk_len <= WIRE_V2_MAX_CHUNK_LEN;
}

inline bool validate_config_size(size_t total_len) {
    return total_len <= WIRE_V2_MAX_CONFIG_LEN;
}

struct DeviceDescriptor {
    char device_uid[64];
    char board_model[32];
    char board_revision[16];
    uint16_t protocol_version;
    char capabilities[128];
    char home_id[64];
    uint32_t owner_epoch;
    char boot_id[64];
    uint32_t config_revision;
};

inline bool validate_device_descriptor(const DeviceDescriptor& desc, uint32_t current_epoch, const char** err_msg) {
    if (strnlen(desc.board_model, sizeof(desc.board_model)) >= sizeof(desc.board_model) ||
        !is_supported_board_model(desc.board_model)) {
        if (err_msg) *err_msg = "UNKNOWN_MODEL";
        return false;
    }
    if (desc.protocol_version != 2) {
        if (err_msg) *err_msg = "UNSUPPORTED_PROTOCOL";
        return false;
    }
    if (desc.owner_epoch < current_epoch) {
        if (err_msg) *err_msg = "OLD_EPOCH";
        return false;
    }
    if (strnlen(desc.device_uid, sizeof(desc.device_uid)) >= sizeof(desc.device_uid) ||
        strnlen(desc.device_uid, sizeof(desc.device_uid)) == 0) {
        if (err_msg) *err_msg = "EMPTY_UID";
        return false;
    }
    if (strnlen(desc.home_id, sizeof(desc.home_id)) >= sizeof(desc.home_id)) {
        if (err_msg) *err_msg = "INVALID_HOME_ID";
        return false;
    }
    if (strnlen(desc.boot_id, sizeof(desc.boot_id)) >= sizeof(desc.boot_id)) {
        if (err_msg) *err_msg = "INVALID_BOOT_ID";
        return false;
    }
    if (strnlen(desc.capabilities, sizeof(desc.capabilities)) >= sizeof(desc.capabilities)) {
        if (err_msg) *err_msg = "INVALID_CAPABILITIES";
        return false;
    }
    return true;
}

struct Operation {
    OperationKind kind;
    char operation_id[64];
    char device_uid[64];
    OperationState state;
    char error_code[32];
    uint64_t expires_at_sec;
};

struct WireV2ConfigBegin {
    char operation_id[64];
    uint32_t config_revision;
    uint32_t total_len;
    uint16_t chunk_count;
    uint32_t crc32;
};

struct WireV2ConfigChunk {
    char operation_id[64];
    uint16_t chunk_index;
    uint16_t payload_len;
    uint8_t payload[WIRE_V2_MAX_CHUNK_LEN];
};

struct WireV2ConfigCommit {
    char operation_id[64];
    uint32_t config_revision;
    uint32_t crc32;
};

inline LedPattern resolve_device_led_pattern(
    LifecycleState lifecycle,
    ConnectivityState connectivity,
    FaultKind fault = FaultKind::NONE,
    bool has_active_op = false,
    OperationKind active_op_kind = OperationKind::IDENTIFY,
    OperationState active_op_state = OperationState::RUNNING,
    uint64_t elapsed_in_state_ms = 0
) {
    // 1. Fault has highest priority
    if (fault != FaultKind::NONE) {
        return LedPattern::FAULT;
    }

    // 2. Awaiting reset confirmation (max 5s)
    if (has_active_op && active_op_state == OperationState::AWAITING_CONFIRMATION) {
        if (active_op_kind == OperationKind::FACTORY_RESET) {
            return LedPattern::AWAITING_FACTORY_RESET;
        }
        if (active_op_kind == OperationKind::NETWORK_RESET) {
            return LedPattern::AWAITING_NETWORK_RESET;
        }
    }

    // 3. Setup / Claim / Lifecycle
    if (has_active_op && active_op_kind == OperationKind::CONFIGURE && active_op_state == OperationState::RUNNING) {
        return LedPattern::CONFIG_APPLYING;
    }
    if (lifecycle == LifecycleState::CLAIMING) {
        return LedPattern::CLAIMING;
    }
    if (lifecycle == LifecycleState::UNCLAIMED || lifecycle == LifecycleState::DECOMMISSIONED) {
        return LedPattern::UNCLAIMED;
    }

    // 4. Identify (max 15s)
    if (has_active_op && active_op_kind == OperationKind::IDENTIFY && active_op_state == OperationState::RUNNING) {
        if (elapsed_in_state_ms < 15000) {
            return LedPattern::IDENTIFY;
        }
    }

    // 5. Connectivity (when claimed)
    if (connectivity == ConnectivityState::CONNECTING) {
        return LedPattern::CONNECTING;
    }
    if (connectivity == ConnectivityState::OFFLINE || connectivity == ConnectivityState::UNKNOWN) {
        return LedPattern::OFFLINE;
    }

    // 6. Ready (Claimed & Online)
    if (lifecycle == LifecycleState::CLAIMED && connectivity == ConnectivityState::ONLINE) {
        if (elapsed_in_state_ms < 2000) {
            return LedPattern::READY;
        }
        return LedPattern::OFF;
    }

    return LedPattern::OFF;
}

inline bool status_led_is_active(LedPattern pattern, uint64_t elapsed_ms) {
    switch (pattern) {
        case LedPattern::FAULT: {
            uint64_t phase = elapsed_ms % 3600;
            return (phase < 1600) && ((phase % 400) < 200);
        }
        case LedPattern::AWAITING_FACTORY_RESET: {
            uint64_t phase = elapsed_ms % 3000;
            return (phase < 2000) && ((phase % 400) < 200);
        }
        case LedPattern::AWAITING_NETWORK_RESET: {
            uint64_t phase = elapsed_ms % 2200;
            return (phase < 1200) && ((phase % 400) < 200);
        }
        case LedPattern::CLAIMING:
            return (elapsed_ms % 500) < 250;
        case LedPattern::CONFIG_APPLYING: {
            uint64_t phase = elapsed_ms % 1600;
            return (phase < 800) && ((phase % 400) < 200);
        }
        case LedPattern::UNCLAIMED:
            return (elapsed_ms % 1000) < 500;
        case LedPattern::IDENTIFY: {
            uint64_t phase = elapsed_ms % 3000;
            return (phase < 1200) && ((phase % 400) < 200);
        }
        case LedPattern::OFFLINE: {
            uint64_t phase = elapsed_ms % 2800;
            return (phase < 800) && ((phase % 400) < 200);
        }
        case LedPattern::CONNECTING: {
            uint64_t phase = elapsed_ms % 1400;
            return (phase < 400) && ((phase % 400) < 200);
        }
        case LedPattern::READY:
            return elapsed_ms < 2000;
        case LedPattern::OFF:
        default:
            return false;
    }
}
