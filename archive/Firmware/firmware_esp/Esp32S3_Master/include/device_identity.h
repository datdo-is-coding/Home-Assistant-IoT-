/*
 * AETHERIA OS — Commercial Device Identity & Lifecycle Manager
 * 
 * Implements:
 * 1. Hardware Identity:
 *    - device_id (e.g. "node_7f3a91c2" derived from chip silicon eFuse MAC)
 *    - hardware ("esp32s3")
 *    - serial (e.g. "S3-2026-000183")
 *    - mac address
 *    Guaranteed 100% unique per physical chip, persistent across factory reset.
 *
 * 2. User Identity:
 *    - name (e.g. "Loa phòng ngủ")
 *    - room (e.g. "bedroom")
 *    - location (e.g. "Tầng 2 - Phòng ngủ")
 *    - description (e.g. "Voice node")
 *    - relay names
 *
 * 3. Lifecycle State Machine:
 *    FACTORY_NEW -> PROVISIONING -> CLAIMED -> READY (with OTA/RECOVERY)
 *
 * 4. Factory Reset:
 *    Hold reset button for 10s: erases user config, Wi-Fi, gateway pairing,
 *    but KEEPS device_id and hardware identity.
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

/**
 * @brief Initialize Device Identity.
 * Reads or generates hardware identity from silicon eFuse MAC (namespace "hw_id").
 * Reads user identity from NVS (namespace "user_id").
 * Sets initial lifecycle state (FACTORY_NEW if unprovisioned, READY if provisioned).
 */
esp_err_t device_identity_init(void);

/**
 * @brief Get read-only pointer to Hardware Identity.
 */
const hardware_identity_t *device_identity_get_hardware(void);

/**
 * @brief Get read-only pointer to User Identity.
 */
const user_identity_t *device_identity_get_user(void);

/**
 * @brief Shorthand to get unique device_id string (e.g. "node_7f3a91c2").
 */
const char *device_identity_get_id(void);

/**
 * @brief Get current lifecycle state.
 */
device_lifecycle_state_t device_identity_get_state(void);

/**
 * @brief Set current lifecycle state.
 */
void device_identity_set_state(device_lifecycle_state_t state);

/**
 * @brief Get string name of lifecycle state.
 */
const char *device_identity_state_str(device_lifecycle_state_t state);

/**
 * @brief Save User Identity and gateway provision data into NVS (namespace "user_id").
 * Transitions state to READY upon success.
 */
esp_err_t device_identity_save_user_config(const user_identity_t *config);

/**
 * @brief Factory Reset:
 * Erases user config, Wi-Fi, gateway pairing (namespace "user_id").
 * KEEPS device_id and hardware identity (namespace "hw_id").
 * Resets state to FACTORY_NEW and reboots device.
 */
esp_err_t device_identity_factory_reset(void);

/**
 * @brief Export combined Identity as JSON string. Caller must free() the returned pointer.
 */
char *device_identity_export_json(void);

#ifdef __cplusplus
}
#endif
