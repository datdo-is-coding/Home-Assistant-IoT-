#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    DEVICE_STATE_FACTORY_NEW   = 0,
    DEVICE_STATE_PROVISIONING  = 1,
    DEVICE_STATE_CLAIMED       = 2,
    DEVICE_STATE_READY         = 3,
    DEVICE_STATE_RECOVERY      = 4
} device_lifecycle_state_t;

typedef struct {
    char device_id[32];
    char hardware[32];
    char serial[32];
    char mac_str[18];
    uint8_t mac_raw[6];
} hardware_identity_t;

typedef struct {
    char name[64];
    char room[32];
    char location[64];
    char description[64];
    char rl1_name[32];
    char rl2_name[32];
    uint32_t cfg_version;
    bool is_provisioned;
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
