#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "actionbox_protocol.h"
#include "common/device_lifecycle.h"
#include "button_driver.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t device_manager_init(void);

esp_err_t device_manager_execute_command(const ActionBoxCommand *cmd, ActionBoxResponse *out_resp);

void device_manager_on_fault_alert(uint8_t channel, RelayFault fault, uint32_t current_ma);

void device_manager_update_leds(void);

bool device_manager_is_claimed(void);

#ifdef __cplusplus
}
void device_manager_on_button_event(uint8_t channel, ButtonAction action, void *user_data);
ArmedKind device_manager_get_armed_kind(void);
#endif
