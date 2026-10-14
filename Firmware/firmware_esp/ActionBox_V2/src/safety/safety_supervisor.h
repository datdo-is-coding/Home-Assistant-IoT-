/**
 * @file safety_supervisor.h
 * @brief Independent Local Safety Supervisor & Overcurrent Protection Layer
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "current_sensor.h"
#include "actionbox_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*fault_alert_cb_t)(uint8_t channel, RelayFault fault, uint32_t current_ma);

/**
 * @brief Initialize safety supervisor, configure TWDT, apply safe boot state
 * @return ESP_OK on success
 */
esp_err_t safety_supervisor_init(void);

/**
 * @brief Register callback for urgent fault alert notifications
 * @param cb Callback function
 */
void safety_register_fault_callback(fault_alert_cb_t cb);

/**
 * @brief Evaluate new current measurement for safety violations
 * If overcurrent detected, instantly trips the relay, isolates channel, and dispatches alert.
 * @param channel Channel ID (1 or 2)
 * @param meas Pointer to latest CurrentMeasurement
 */
void safety_process_measurement(uint8_t channel, const CurrentMeasurement *meas);
bool safety_sensor_ready(uint8_t channel);
void safety_check_sensor_timeouts(void);

/**
 * @brief Validate an incoming command against safety policy before execution
 * @param cmd Pointer to parsed ActionBoxCommand
 * @param out_err_msg Buffer for error message if rejected
 * @param max_err_len Buffer size
 * @return true if command is safe to execute, false if rejected
 */
bool safety_validate_command(const ActionBoxCommand *cmd, char *out_err_msg, size_t max_err_len);

/**
 * @brief Record heartbeat from SubBox to reset network timeout watchdog
 */
void safety_feed_network_watchdog(void);

/**
 * @brief Check if network communication has timed out
 * @return true if SubBox communication is timed out, false if active
 */
bool safety_is_network_timed_out(void);

/**
 * @brief Register the calling FreeRTOS task with the Task Watchdog Timer
 * @return ESP_OK on success
 */
esp_err_t safety_register_calling_task_wdt(void);

/**
 * @brief Feed FreeRTOS Task Watchdog Timer
 */
void safety_feed_task_watchdog(void);

/**
 * @brief Apply configured startup state (from NVS) to relays on boot
 */
void safety_apply_startup_state(void);

#ifdef __cplusplus
}
#endif
