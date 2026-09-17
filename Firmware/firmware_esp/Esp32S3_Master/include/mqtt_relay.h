/*
 * MQTT Relay Controller — Header
 * Handles MQTT connection and relay GPIO control on ESP32-S3.
 * Receives commands from Pi Gateway, controls 2-channel relay.
 */

#ifndef MQTT_RELAY_H
#define MQTT_RELAY_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Relay GPIO Configuration — CHANGE THESE TO MATCH YOUR WIRING
 * Default: GPIO 4 (Channel 1) and GPIO 5 (Channel 2)
 */
#define RELAY_CH1_GPIO    4
#define RELAY_CH2_GPIO    5
#define RELAY_ACTIVE_LOW  true    /* Active-LOW: Driven by PC817 Cathode (Pin 2) on GPIO 4 & 5 */

/**
 * @brief Initialize MQTT client and relay GPIOs.
 * @param broker_uri  MQTT broker URI (e.g. "mqtt://192.168.11.29:1883")
 * @param username    MQTT username (NULL if no auth)
 * @param password    MQTT password (NULL if no auth)
 * @return ESP_OK on success
 */
esp_err_t mqtt_relay_init(const char *broker_uri, const char *username, const char *password);

/**
 * @brief Set relay channel state.
 * @param channel  Relay channel (1 or 2)
 * @param state    true=ON, false=OFF
 */
void mqtt_relay_set(int channel, bool state);

/**
 * @brief Get current relay channel state.
 * @param channel  Relay channel (1 or 2)
 * @return true if ON, false if OFF
 */
bool mqtt_relay_get_state(int channel);

/**
 * @brief Publish current relay status to MQTT.
 *        Publishes to smarthome/status/esp32s3_master
 */
void mqtt_relay_publish_status(void);

/**
 * @brief Check if this node has been provisioned into the system.
 */
bool mqtt_relay_is_provisioned(void);

/**
 * @brief Mark this node as provisioned (or unprovisioned) in NVS.
 */
void mqtt_relay_set_provisioned(bool prov);

#ifdef __cplusplus
}
#endif

#endif /* MQTT_RELAY_H */
