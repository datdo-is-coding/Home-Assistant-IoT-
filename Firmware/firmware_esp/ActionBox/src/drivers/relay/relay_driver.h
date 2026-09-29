/**
 * @file relay_driver.h
 * @brief Hardware-Independent Relay Actuation Driver with Magnetic-Latching and Monostable Support
 */

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
    uint8_t    channel_id;      /**< 1 or 2 */
    RelayState current_state;   /**< Current verified contact state */
    RelayState target_state;    /**< Target state being actuated */
    RelayFault fault_state;     /**< Hardware or safety fault code */
    uint32_t   last_actuated_ms;/**< Timestamp of last switch operation */
    uint32_t   cycle_count;     /**< Switch cycle counter */
} RelayChannelInfo;

/**
 * @brief Initialize Relay hardware driver (GPIOs, pulse timers, initial states)
 * @return ESP_OK on success
 */
esp_err_t relay_driver_init(void);

/**
 * @brief Turn ON the specified relay channel
 * @param channel Channel ID (1 or 2)
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if channel invalid, ESP_FAIL if channel is in FAULT
 */
esp_err_t relay_on(uint8_t channel);

/**
 * @brief Turn OFF the specified relay channel
 * @param channel Channel ID (1 or 2)
 * @return ESP_OK on success
 */
esp_err_t relay_off(uint8_t channel);

/**
 * @brief Toggle the specified relay channel
 * @param channel Channel ID (1 or 2)
 * @return ESP_OK on success
 */
esp_err_t relay_toggle(uint8_t channel);

/**
 * @brief Retrieve current verified contact state
 * @param channel Channel ID (1 or 2)
 * @return RELAY_STATE_ON, RELAY_STATE_OFF, or RELAY_STATE_UNKNOWN
 */
RelayState relay_get_state(uint8_t channel);

/**
 * @brief Retrieve current fault state
 * @param channel Channel ID (1 or 2)
 * @return RelayFault enum
 */
RelayFault relay_get_fault(uint8_t channel);

/**
 * @brief Manually set or isolate a fault on a channel (e.g. from safety supervisor)
 * @param channel Channel ID (1 or 2)
 * @param fault RelayFault code
 */
void relay_set_fault(uint8_t channel, RelayFault fault);

/**
 * @brief Clear any active fault on a channel (allows re-enabling after inspection)
 * @param channel Channel ID (1 or 2)
 * @return ESP_OK on success
 */
esp_err_t relay_clear_fault(uint8_t channel);

/**
 * @brief Query full diagnostic channel info
 * @param channel Channel ID (1 or 2)
 * @param out_info Pointer to destination struct
 * @return ESP_OK on success
 */
esp_err_t relay_get_channel_info(uint8_t channel, RelayChannelInfo *out_info);

/**
 * @brief Emergency cutoff - unconditionally de-energizes all relays immediately
 */
void relay_emergency_all_off(void);

#ifdef __cplusplus
}
#endif
