#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    RELAY_STATE_OFF = 0,
    RELAY_STATE_ON  = 1,
    RELAY_STATE_UNKNOWN = 255
} RelayState;

typedef enum {
    RELAY_FAULT_NONE        = 0,
    RELAY_FAULT_OVERCURRENT = 1,
    RELAY_FAULT_HARDWARE    = 2,
    RELAY_FAULT_SAFETY_LOCK = 3
} RelayFault;

typedef struct {
    uint8_t    channel_id;
    RelayState current_state;
    RelayState target_state;
    RelayFault fault_state;
    uint32_t   last_actuated_ms;
    uint32_t   cycle_count;
} RelayChannelInfo;

esp_err_t relay_driver_init(void);

esp_err_t relay_on(uint8_t channel);

esp_err_t relay_off(uint8_t channel);

esp_err_t relay_toggle(uint8_t channel);

RelayState relay_get_state(uint8_t channel);

RelayFault relay_get_fault(uint8_t channel);

void relay_set_fault(uint8_t channel, RelayFault fault);

esp_err_t relay_clear_fault(uint8_t channel);

esp_err_t relay_get_channel_info(uint8_t channel, RelayChannelInfo *out_info);

void relay_emergency_all_off(void);

#ifdef __cplusplus
}
#endif
