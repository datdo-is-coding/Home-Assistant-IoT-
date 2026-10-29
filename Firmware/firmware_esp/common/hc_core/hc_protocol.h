#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define HC_HEADER_SIZE 38u
#define HC_TAG_SIZE 16u
#define HC_MAX_PAYLOAD 196u
#define HC_MAX_FRAME 250u
#define HC_VERSION 1u

typedef enum {
    HC_HELLO=1, HC_IDENTITY_CHALLENGE, HC_IDENTITY_RESPONSE, HC_PAIR_REQUEST,
    HC_PAIR_ACCEPT, HC_PAIR_REJECT, HC_HEARTBEAT, HC_CAPABILITY_REPORT,
    HC_CONFIG_PUSH, HC_CONFIG_ACK, HC_COMMAND, HC_COMMAND_ACK, HC_STATE_REPORT,
    HC_TELEMETRY_REPORT, HC_EVENT_REPORT, HC_ROOM_SNAPSHOT, HC_STATE_SYNC_REQUEST,
    HC_ERROR_REPORT, HC_OTA_OFFER, HC_OTA_START, HC_OTA_PROGRESS, HC_OTA_RESULT,
    HC_OTA_ABORT, HC_UNPAIR, HC_FACTORY_RESET_REQUEST, HC_OTA_CHUNK,
    HC_OTA_CHUNK_ACK, HC_FRAGMENT, HC_CHANNEL_PROBE, HC_MAINTENANCE,
    HC_MAINTENANCE_ACK
} hc_message_type;
typedef enum { HC_OK=0, HC_INVALID=-1, HC_AUTH=-2, HC_CAPACITY=-3 } hc_result;
typedef int (*hc_mac_fn)(void *ctx, const uint8_t *data, size_t len, uint8_t tag[16]);
typedef struct {
    uint8_t type, flags, payload_len;
    uint64_t message_id;
    uint32_t source, destination;
    uint64_t boot_id;
    uint32_t sequence, config_rev;
    uint8_t payload[HC_MAX_PAYLOAD];
} hc_frame;
int hc_encode(const hc_frame *frame, uint8_t *out, size_t capacity, hc_mac_fn mac, void *ctx);
int hc_decode(const uint8_t *data, size_t len, hc_frame *out, hc_mac_fn mac, void *ctx);
int hc_validate(const uint8_t *data, size_t len, hc_mac_fn mac, void *ctx);
int hc_roundtrip(const uint8_t *data, size_t len, uint8_t out[HC_MAX_FRAME], hc_mac_fn mac, void *ctx);
int hc_command_admit(uint64_t generations[3], uint8_t channel, uint8_t state, uint64_t generation, uint64_t deadline, uint64_t now);
void hc_factory_id(const uint8_t base_mac[6], char out[16]);
typedef struct { uint64_t boot; uint32_t high, mask; } hc_replay;
typedef enum { HC_NEW=0, HC_DUPLICATE=1, HC_STALE=2, HC_SESSION_REQUIRED=3 } hc_replay_result;
void hc_replay_admit(hc_replay *state, uint64_t authenticated_boot);
hc_replay_result hc_replay_check(hc_replay *state, uint64_t boot, uint32_t seq);
#ifdef __cplusplus
}
#endif
