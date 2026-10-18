#ifndef RELAY_DRIVER_H
#define RELAY_DRIVER_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef RELAY_CH1_GPIO
#define RELAY_CH1_GPIO    4
#endif

#ifndef RELAY_CH2_GPIO
#define RELAY_CH2_GPIO    5
#endif

#ifndef RELAY_ACTIVE_LOW
#define RELAY_ACTIVE_LOW  true
#endif

esp_err_t relay_driver_init(void);

void relay_driver_set(int channel, bool on);

bool relay_driver_get(int channel);

bool relay_driver_toggle(int channel);

uint8_t relay_driver_get_bitmask(void);

#ifdef __cplusplus
}
#endif

#endif
