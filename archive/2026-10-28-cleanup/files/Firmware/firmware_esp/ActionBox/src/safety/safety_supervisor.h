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

esp_err_t safety_supervisor_init(void);

void safety_register_fault_callback(fault_alert_cb_t cb);

void safety_process_measurement(uint8_t channel, const CurrentMeasurement *meas);
bool safety_sensor_ready(uint8_t channel);
void safety_check_sensor_timeouts(void);

bool safety_validate_command(const ActionBoxCommand *cmd, char *out_err_msg, size_t max_err_len);

void safety_feed_network_watchdog(void);

bool safety_is_network_timed_out(void);

esp_err_t safety_register_calling_task_wdt(void);

void safety_feed_task_watchdog(void);

void safety_apply_startup_state(void);

#ifdef __cplusplus
}
#endif
