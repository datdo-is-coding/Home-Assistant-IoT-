/*
 * AETHERIA OS — Commercial Device Identity & Lifecycle Manager
 * Shared Module for T1 Actuator Nodes and T2 Zone Controllers
 */

#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    DEVICE_STATE_FACTORY_NEW   = 0,  /* Unclaimed, factory defaults */
    DEVICE_STATE_PROVISIONING  = 1,  /* Discovered by Gateway, awaiting user claim */
    DEVICE_STATE_CLAIMED       = 2,  /* Claimed by user, config applied */
    DEVICE_STATE_READY         = 3,  /* Fully operational in smart home */
    DEVICE_STATE_RECOVERY      = 4   /* OTA or recovery fallback mode */
} device_lifecycle_state_t;

typedef struct {
    char device_id[32];   /* e.g. "node_7f3a91c2" */
    char hardware[32];    /* "esp32s3" */
    char serial[32];      /* e.g. "S3-2026-000183" */
    char mac_str[18];     /* "F0:B4:29:18:31:33" */
    uint8_t mac_raw[6];   /* Raw bytes */
} hardware_identity_t;

typedef struct {
    char name[64];        /* e.g. "Loa phòng ngủ" */
    char room[32];        /* e.g. "bedroom" */
    char location[64];    /* e.g. "Tầng 2 - Phòng ngủ" */
    char description[64]; /* e.g. "Voice node" */
    char rl1_name[32];    /* e.g. "light" */
    char rl2_name[32];    /* e.g. "fan" */
    uint32_t cfg_version; /* Version counter */
    bool is_provisioned;  /* True if claimed and configured */
} user_identity_t;

esp_err_t device_identity_init(void);
const hardware_identity_t *device_identity_get_hardware(void);
const user_identity_t *device_identity_get_user(void);
const char *device_identity_get_id(void);
device_lifecycle_state_t device_identity_get_state(void);
void device_identity_set_state(device_lifecycle_state_t state);
const char *device_identity_state_str(device_lifecycle_state_t state);
esp_err_t device_identity_save_user_config(const user_identity_t *config);
esp_err_t device_identity_factory_reset(void);
char *device_identity_export_json(void);

#ifdef __cplusplus
}
#endif
