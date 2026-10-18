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

esp_err_t zone_manager_init(const char *zone_name);

const char *zone_manager_get_zone_name(void);

zone_node_entry_t *zone_manager_register_hello(const espnow_node_hello_t *hello, const uint8_t *sender_mac);

void zone_manager_update_relay(const uint8_t *sender_mac, uint8_t rl1, uint8_t rl2);

zone_node_entry_t *zone_manager_find_by_mac(const uint8_t *mac);

zone_node_entry_t *zone_manager_find_by_id(const char *device_id);

zone_node_entry_t *zone_manager_get_all(int *out_count);

void zone_manager_check_timeouts(void);

#ifdef __cplusplus
}
#endif

#endif
