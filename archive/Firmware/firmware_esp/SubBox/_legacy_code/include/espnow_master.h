/*
 * ESP-NOW Master — T2 Zone Controller
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Coordinates communications with all T1 Actuator Nodes in the zone:
 *   - Automatic peer registration on HELLO
 *   - Relay command forwarding
 *   - Audio packet demuxing
 *   - Telemetry reception
 */

#ifndef ESPNOW_MASTER_H
#define ESPNOW_MASTER_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize ESP-NOW in Master mode on ESPNOW_WIFI_CHANNEL.
 * (Wi-Fi must already be initialized in STA or AP+STA mode).
 */
esp_err_t espnow_master_init(void);

/**
 * @brief Send relay control command to a specific T1 node.
 * @param target_mac  MAC address of target T1 node
 * @param channel     Relay channel (1 or 2)
 * @param state       Relay state (1=ON, 0=OFF)
 */
esp_err_t espnow_master_send_relay_cmd(const uint8_t *target_mac, uint8_t channel, uint8_t state);

/**
 * @brief Send configuration to a T1 node (naming, room, etc.).
 */
esp_err_t espnow_master_send_node_cfg(const uint8_t *target_mac, const espnow_node_cfg_t *cfg);

#ifdef __cplusplus
}
#endif

#endif /* ESPNOW_MASTER_H */
