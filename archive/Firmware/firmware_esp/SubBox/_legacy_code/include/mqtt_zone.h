#ifndef MQTT_ZONE_H
#define MQTT_ZONE_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include "zone_manager.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t mqtt_zone_init(const char *broker_uri, const char *user, const char *pass);

void mqtt_zone_publish_node_status(const zone_node_entry_t *node);

void mqtt_zone_publish_relay_state(const char *device_id, uint8_t channel, uint8_t state);

void mqtt_zone_publish_telemetry(const char *device_id, const esp_now_packet_t *tele);

void mqtt_zone_publish_zone_summary(void);

bool mqtt_zone_is_connected(void);

#ifdef __cplusplus
}
#endif

#endif
