#ifndef IR_CONTROLLER_H
#define IR_CONTROLLER_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    IR_AC_MODE_COOL = 0,
    IR_AC_MODE_HEAT = 1,
    IR_AC_MODE_AUTO = 2,
    IR_AC_MODE_DRY  = 3,
    IR_AC_MODE_FAN  = 4
} ir_ac_mode_t;

typedef enum {
    IR_AC_FAN_AUTO = 0,
    IR_AC_FAN_LOW  = 1,
    IR_AC_FAN_MED  = 2,
    IR_AC_FAN_HIGH = 3
} ir_ac_fan_t;

typedef struct {
    char         brand[16];
    bool         power;
    uint8_t      temp_c;
    ir_ac_mode_t mode;
    ir_ac_fan_t  fan;
    bool         swing;
} ir_ac_cmd_t;

esp_err_t ir_controller_init(gpio_num_t tx_gpio, gpio_num_t rx_gpio);

esp_err_t ir_send_nec(uint16_t address, uint16_t command);

esp_err_t ir_send_raw(const uint32_t *timings_us, size_t count);

esp_err_t ir_send_ac(const ir_ac_cmd_t *cmd);

esp_err_t ir_handle_json_cmd(const char *json_str);

#ifdef __cplusplus
}
#endif

#endif
