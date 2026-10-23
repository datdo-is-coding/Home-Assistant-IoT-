#pragma once
#include <cstdint>
#include <cstring>

// Protocol-3 enrollment uses physical setup at both ends. These frames do not
// authenticate radio peers; secure hc_core provisioning must not consume them.
constexpr uint8_t CLAIM_FRAME = 0x30;
constexpr uint8_t CLAIM_RECEIPT = 0x31;
#pragma pack(push, 1)
struct ClaimFrame {
    uint8_t type, version;
    uint32_t session, revision;
    char node_id[16], room[16], operation[32], channels[3][24];
};
struct ClaimReceipt {
    uint8_t type, version, success;
    uint32_t revision, owner_epoch;
    char node_id[16], operation[32];
};
struct RegisteredPeer {
    uint8_t mac[6];
    ClaimFrame claim;
};
#pragma pack(pop)
static_assert(sizeof(ClaimFrame) <= 250 && sizeof(ClaimReceipt) <= 250, "ESP-NOW v1 frame limit");
inline bool valid_claim(const ClaimFrame& c) {
    if (c.type != CLAIM_FRAME || c.version != 3 || !c.session || !c.revision) return false;
    if (!c.node_id[0] || !memchr(c.node_id,0,sizeof(c.node_id)) || !c.operation[0] ||
        !memchr(c.operation,0,sizeof(c.operation)) || !c.room[0] || !memchr(c.room,0,sizeof(c.room))) return false;
    for (const auto& name : c.channels) if (!name[0] || !memchr(name,0,sizeof(name))) return false;
    return true;
}
