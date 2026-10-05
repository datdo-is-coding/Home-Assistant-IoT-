/*
 * T2 Zone Controller — Infrared (IR) Controller Module
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Supports:
 *   - IR TX via ESP-IDF 5.x RMT driver (38kHz carrier, 33% duty cycle)
 *   - NEC protocol encoder (TV, Fans, Audio systems)
 *   - Raw timings transmission (Universal AC: Daikin, Panasonic, Casper, Gree, etc.)
 *   - Optional IR RX for remote learning and state synchronization
 */

#ifndef IR_CONTROLLER_H
#define IR_CONTROLLER_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ─── AC Operating Modes ─── */
typedef enum {
    IR_AC_MODE_COOL = 0,
    IR_AC_MODE_HEAT = 1,
    IR_AC_MODE_AUTO = 2,
    IR_AC_MODE_DRY  = 3,
    IR_AC_MODE_FAN  = 4
} ir_ac_mode_t;

/* ─── AC Fan Speeds ─── */
typedef enum {
    IR_AC_FAN_AUTO = 0,
    IR_AC_FAN_LOW  = 1,
    IR_AC_FAN_MED  = 2,
    IR_AC_FAN_HIGH = 3
} ir_ac_fan_t;

/* ─── AC Command Structure ─── */
typedef struct {
    char         brand[16];      /* "daikin", "panasonic", "casper", "gree" */
    bool         power;          /* true=ON, false=OFF */
    uint8_t      temp_c;         /* 16 - 30 */
    ir_ac_mode_t mode;           /* COOL, HEAT, etc. */
    ir_ac_fan_t  fan;            /* AUTO, LOW, MED, HIGH */
    bool         swing;          /* true=Swing ON */
} ir_ac_cmd_t;

/* ─── API Functions ─── */

/**
 * @brief Initialize IR transmitter (and optional receiver) using RMT peripheral.
 * @param tx_gpio GPIO connected to IR LED driver (via NPN/MOSFET transistor)
 * @param rx_gpio GPIO connected to TSOP/VS1838B receiver (GPIO_NUM_NC if unused)
 * @return ESP_OK on success
 */
esp_err_t ir_controller_init(gpio_num_t tx_gpio, gpio_num_t rx_gpio);

/**
 * @brief Transmit NEC protocol frame (Standard TV, Fan, Set-top box).
 * @param address 16-bit NEC address
 * @param command 16-bit NEC command
 * @return ESP_OK on success
 */
esp_err_t ir_send_nec(uint16_t address, uint16_t command);

/**
 * @brief Transmit raw timing pulse-space array (in microseconds).
 * @param timings_us Array of alternating mark/space durations in microseconds
 * @param count Number of timing elements (must be even, mark + space pairs)
 * @return ESP_OK on success
 */
esp_err_t ir_send_raw(const uint32_t *timings_us, size_t count);

/**
 * @brief Send structured Air Conditioner command.
 * Encodes AC brand frame and transmits via RMT carrier.
 * @param cmd Pointer to ir_ac_cmd_t structure
 * @return ESP_OK on success
 */
esp_err_t ir_send_ac(const ir_ac_cmd_t *cmd);

/**
 * @brief Parse JSON IR command received from MQTT and execute.
 * Example payload:
 *   {"type": "ac", "brand": "daikin", "power": true, "temp": 26, "mode": "cool"}
 *   {"type": "nec", "addr": 0x00FF, "cmd": 0x12}
 *   {"type": "raw", "timings": [9000, 4500, 560, 560, ...]}
 * @param json_str Null-terminated JSON string
 * @return ESP_OK on success
 */
esp_err_t ir_handle_json_cmd(const char *json_str);

#ifdef __cplusplus
}
#endif

#endif /* IR_CONTROLLER_H */
