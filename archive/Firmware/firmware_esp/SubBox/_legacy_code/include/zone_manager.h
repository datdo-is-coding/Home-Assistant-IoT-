/*
 * Zone Manager — T2 Zone Controller
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Maintains the registry of T1 Actuator Nodes active in this zone:
 *   - Node discovery & pairing tracking
 *   - Current relay & sensor state cache
 *   - Heartbeat & online/offline status monitoring
 */

#ifndef ZONE_MANAGER_H
#define ZONE_MANAGER_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include "t2_config.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t  mac[6];
    char     device_id[ESPNOW_DEVICE_ID_LEN];
    char     room[ESPNOW_ROOM_LEN];
    char     rl1_name[32];
    char     rl2_name[32];
    uint8_t  rl1_state;
    uint8_t  rl2_state;
    uint8_t  capabilities;
    uint8_t  is_provisioned;
    uint32_t cfg_version;
    uint32_t uptime_s;
    int8_t   rssi;
    uint32_t last_seen_ms;
    bool     is_online;
} zone_node_entry_t;

/**
 * @brief Initialize Zone Manager with zone name.
 */
esp_err_t zone_manager_init(const char *zone_name);

/**
 * @brief Get the configured zone name (e.g. "living_room").
 */
const char *zone_manager_get_zone_name(void);

/**
 * @brief Register or update a T1 node from its HELLO packet.
 * @param hello       Received hello packet
 * @param sender_mac  Sender's MAC address
 * @return Pointer to node entry or NULL if zone table is full
 */
zone_node_entry_t *zone_manager_register_hello(const espnow_node_hello_t *hello, const uint8_t *sender_mac);

/**
 * @brief Update relay states for a node after receiving RELAY_ACK.
 */
void zone_manager_update_relay(const uint8_t *sender_mac, uint8_t rl1, uint8_t rl2);

/**
 * @brief Find a node by MAC address.
 */
zone_node_entry_t *zone_manager_find_by_mac(const uint8_t *mac);

/**
 * @brief Find a node by device ID (e.g. "node_7f3a91c2").
 */
zone_node_entry_t *zone_manager_find_by_id(const char *device_id);

/**
 * @brief Get all nodes in the zone.
 * @param out_count  Pointer to receive number of active nodes
 * @return Array of node entries (internal pointer)
 */
zone_node_entry_t *zone_manager_get_all(int *out_count);

/**
 * @brief Check node timeouts and mark stale nodes as offline.
 * Called periodically from watchdog task.
 */
void zone_manager_check_timeouts(void);

#ifdef __cplusplus
}
#endif

#endif /* ZONE_MANAGER_H */
