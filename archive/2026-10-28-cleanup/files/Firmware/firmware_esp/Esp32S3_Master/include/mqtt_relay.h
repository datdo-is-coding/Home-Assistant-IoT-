#ifndef MQTT_RELAY_H
#define MQTT_RELAY_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RELAY_CH1_GPIO    4
#define RELAY_CH2_GPIO    5
#define RELAY_ACTIVE_LOW  true

esp_err_t mqtt_relay_init(const char *broker_uri, const char *username, const char *password);

esp_err_t mqtt_relay_start(void);

void mqtt_relay_set(int channel, bool state);

bool mqtt_relay_get_state(int channel);

void mqtt_relay_publish_status(void);

bool mqtt_relay_is_provisioned(void);

void mqtt_relay_set_provisioned(bool prov);

const char *mqtt_relay_get_node_id(void);

const char *mqtt_relay_get_room(void);

const char *mqtt_relay_get_mac_str(void);

uint32_t mqtt_relay_get_cfg_version(void);

esp_err_t mqtt_relay_save_config(const char *node_id, const char *room,
                                const char *rl1, const char *rl2,
                                uint32_t version);

void mqtt_relay_factory_reset(void);

bool mqtt_relay_handle_cfg_json(const char *json_str);

bool mqtt_relay_handle_desired_config(const char *json_str);

void mqtt_relay_publish_reported_config(uint32_t version);

void mqtt_relay_publish_ota_progress(int percent, const char *status, const char *message);

#ifdef __cplusplus
}
#endif

#endif
