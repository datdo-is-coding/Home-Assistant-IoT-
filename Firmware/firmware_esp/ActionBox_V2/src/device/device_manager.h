#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "actionbox_protocol.h"
#include "button_driver.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t device_manager_init(void);

esp_err_t device_manager_execute_command(const ActionBoxCommand *cmd, ActionBoxResponse *out_resp);

void device_manager_on_button_event(uint8_t channel, ButtonEvent event, void *user_data);

void device_manager_on_fault_alert(uint8_t channel, RelayFault fault, uint32_t current_ma);

void device_manager_update_leds(void);

#ifdef __cplusplus
}
#endif
