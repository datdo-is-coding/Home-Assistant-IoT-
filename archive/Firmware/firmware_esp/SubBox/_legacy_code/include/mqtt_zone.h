/*
 * MQTT Zone Gateway — T2 Zone Controller
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Connects T2 to Gateway's EMQX broker.
 * Subscribes to commands for all T1 nodes in this zone.
 * Publishes status, telemetry, and discovery to Gateway.
 */

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

/**
 * @brief Initialize MQTT Zone client and connect to broker.
 */
esp_err_t mqtt_zone_init(const char *broker_uri, const char *user, const char *pass);

/**
 * @brief Publish node online / hello status to MQTT.
 */
void mqtt_zone_publish_node_status(const zone_node_entry_t *node);

/**
 * @brief Publish confirmed relay state to MQTT (e.g. home/{zone}/{device_id}/relay/{ch}/state).
 */
void mqtt_zone_publish_relay_state(const char *device_id, uint8_t channel, uint8_t state);

/**
 * @brief Publish PZEM telemetry from a T1 node to MQTT.
 */
void mqtt_zone_publish_telemetry(const char *device_id, const esp_now_packet_t *tele);

/**
 * @brief Publish periodic summary of all nodes in this zone.
 */
void mqtt_zone_publish_zone_summary(void);

/**
 * @brief Check if MQTT is currently connected.
 */
bool mqtt_zone_is_connected(void);

#ifdef __cplusplus
}
#endif

#endif /* MQTT_ZONE_H */
