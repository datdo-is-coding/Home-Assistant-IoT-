/**
 * @file device_manager.h
 * @brief High-Level Device Coordination & Command Execution Layer
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "actionbox_protocol.h"
#include "button_driver.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize Device Manager (registers button & safety callbacks)
 * @return ESP_OK on success
 */
esp_err_t device_manager_init(void);

/**
 * @brief Execute a validated ActionBoxCommand and populate ActionBoxResponse
 * @param cmd Pointer to command
 * @param out_resp Pointer to response structure
 * @return ESP_OK on success
 */
esp_err_t device_manager_execute_command(const ActionBoxCommand *cmd, ActionBoxResponse *out_resp);

/**
 * @brief Callback handler triggered by local physical button driver
 * @param channel Channel ID (1 or 2)
 * @param event ButtonEvent
 * @param user_data Optional context
 */
void device_manager_on_button_event(uint8_t channel, ButtonEvent event, void *user_data);

/**
 * @brief Callback handler triggered by safety supervisor on overcurrent trip
 * @param channel Channel ID (1 or 2)
 * @param fault RelayFault
 * @param current_ma Trip current reading
 */
void device_manager_on_fault_alert(uint8_t channel, RelayFault fault, uint32_t current_ma);

/**
 * @brief Update visual LED indicators based on current relay and network states
 */
void device_manager_update_leds(void);

#ifdef __cplusplus
}
#endif
