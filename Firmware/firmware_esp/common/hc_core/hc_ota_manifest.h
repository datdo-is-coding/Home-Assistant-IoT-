#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define HC_OTA_V1_HEADER_SIZE 68u
#define HC_OTA_V1_TARGET_SIZE 132u
#define HC_OTA_V2_HEADER_SIZE 112u
#define HC_OTA_V2_TARGET_SIZE 176u
#define HC_OTA_AGENT_VERSION 2u
#define HC_OTA_BOOTLOADER_API 1u
#define HC_OTA_ROLE_SUBBOX 1u
#define HC_OTA_ROLE_ACTIONBOX 2u
#define HC_OTA_ARTIFACT_FIRMWARE 1u
#define HC_OTA_MAX_IMAGE_SIZE 0x2f0000u

typedef struct {
    uint8_t role;
    bool has_compatibility;
    uint8_t compatibility[32];
    char model[16];
    uint16_t agent_version, bootloader_api, protocol_version;
    uint32_t max_size, key_id;
    uint64_t confirmed_counter;
    uint32_t security_epoch;
} hc_ota_policy;
typedef struct {
    uint8_t schema;
    char version[16];
    uint32_t size;
    uint8_t sha256[32];
    uint64_t release_counter;
    uint32_t security_epoch, key_id;
} hc_ota_target;
typedef bool (*hc_ota_verify_fn)(void *ctx,const uint8_t *header,size_t header_size,
                                const uint8_t signature[64]);
bool hc_ota_manifest_parse(const uint8_t *packet,size_t length,const hc_ota_policy *policy,
                           hc_ota_verify_fn verify,void *ctx,hc_ota_target *out);
#ifdef __cplusplus
}
#endif
