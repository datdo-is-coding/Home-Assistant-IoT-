#pragma once
#include <stdbool.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
esp_err_t subbox_led_init(void);
void subbox_led_set_wifi_connected(bool connected);
void subbox_led_set_mqtt_connected(bool connected);
void subbox_led_set_mqtt_configured(bool configured);
void subbox_led_peer_seen(void);
void subbox_led_set_error(bool has_error);
bool subbox_led_wifi_connected(void);
bool subbox_led_mqtt_connected(void);
#ifdef __cplusplus
}
#endif
