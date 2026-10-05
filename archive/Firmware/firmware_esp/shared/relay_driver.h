/*
 * Relay Driver — Shared Hardware Abstraction
 * DTV Smart Home — Used by T1 Actuator Nodes
 *
 * Extracted from mqtt_relay.c for reuse across tiers.
 * Controls 2-channel relay via GPIO with Active-LOW optocoupler (PC817).
 */

#ifndef RELAY_DRIVER_H
#define RELAY_DRIVER_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Default GPIO assignments — override in t1_config.h if different
 * Matches schematic: PC817 Cathode on GPIO 4 & 5 → Active-LOW
 */
#ifndef RELAY_CH1_GPIO
#define RELAY_CH1_GPIO    4
#endif

#ifndef RELAY_CH2_GPIO
#define RELAY_CH2_GPIO    5
#endif

#ifndef RELAY_ACTIVE_LOW
#define RELAY_ACTIVE_LOW  true
#endif

/**
 * @brief Initialize relay GPIOs as outputs. Sets both relays OFF.
 */
esp_err_t relay_driver_init(void);

/**
 * @brief Set relay channel state.
 * @param channel  1 or 2
 * @param on       true=ON (device powered), false=OFF
 */
void relay_driver_set(int channel, bool on);

/**
 * @brief Get current relay channel state.
 * @param channel  1 or 2
 * @return true if ON, false if OFF
 */
bool relay_driver_get(int channel);

/**
 * @brief Toggle relay channel state.
 * @param channel  1 or 2
 * @return new state after toggle
 */
bool relay_driver_toggle(int channel);

/**
 * @brief Get combined relay state as bitmask (bit0=RL1, bit1=RL2)
 */
uint8_t relay_driver_get_bitmask(void);

#ifdef __cplusplus
}
#endif

#endif /* RELAY_DRIVER_H */
