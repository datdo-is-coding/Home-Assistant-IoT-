/*
 * Zone Manager — Implementation
 * DTV Smart Home — T2 Zone Controller
 */

#include "zone_manager.h"
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "ZONE_MGR";

static char s_zone_name[32] = DEFAULT_ZONE_NAME;
static zone_node_entry_t s_nodes[MAX_T1_NODES_PER_ZONE];
static int s_node_count = 0;

esp_err_t zone_manager_init(const char *zone_name)
{
    if (zone_name && strlen(zone_name) > 0) {
        strncpy(s_zone_name, zone_name, sizeof(s_zone_name) - 1);
    }
    memset(s_nodes, 0, sizeof(s_nodes));
    s_node_count = 0;
    ESP_LOGI(TAG, "Zone Manager initialized for zone '%s' (max %d nodes)",
             s_zone_name, MAX_T1_NODES_PER_ZONE);
    return ESP_OK;
}

const char *zone_manager_get_zone_name(void)
{
    return s_zone_name;
}

zone_node_entry_t *zone_manager_find_by_mac(const uint8_t *mac)
{
    if (!mac) return NULL;
    for (int i = 0; i < s_node_count; i++) {
        if (memcmp(s_nodes[i].mac, mac, 6) == 0) {
            return &s_nodes[i];
        }
    }
    return NULL;
}

zone_node_entry_t *zone_manager_find_by_id(const char *device_id)
{
    if (!device_id) return NULL;
    for (int i = 0; i < s_node_count; i++) {
        if (strncmp(s_nodes[i].device_id, device_id, sizeof(s_nodes[i].device_id)) == 0) {
            return &s_nodes[i];
        }
    }
    return NULL;
}

zone_node_entry_t *zone_manager_register_hello(const espnow_node_hello_t *hello, const uint8_t *sender_mac)
{
    if (!hello || !sender_mac) return NULL;

    uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    zone_node_entry_t *entry = zone_manager_find_by_mac(sender_mac);

    if (!entry) {
        if (s_node_count >= MAX_T1_NODES_PER_ZONE) {
            ESP_LOGW(TAG, "Zone '%s' table is full (%d nodes)!", s_zone_name, MAX_T1_NODES_PER_ZONE);
            return NULL;
        }
        entry = &s_nodes[s_node_count++];
        memcpy(entry->mac, sender_mac, 6);
        ESP_LOGI(TAG, "🆕 Registered new T1 node: %s [%02X:%02X:%02X:%02X:%02X:%02X] (Total: %d)",
                 hello->device_id,
                 sender_mac[0], sender_mac[1], sender_mac[2],
                 sender_mac[3], sender_mac[4], sender_mac[5],
                 s_node_count);
    }

    strncpy(entry->device_id, hello->device_id, sizeof(entry->device_id) - 1);
    entry->rl1_state = hello->rl1_state;
    entry->rl2_state = hello->rl2_state;
    entry->capabilities = hello->capabilities;
    entry->is_provisioned = hello->is_provisioned;
    entry->cfg_version = hello->cfg_version;
    entry->uptime_s = hello->uptime_s;
    entry->rssi = hello->rssi;
    entry->last_seen_ms = now_ms;
    entry->is_online = true;

    return entry;
}

void zone_manager_update_relay(const uint8_t *sender_mac, uint8_t rl1, uint8_t rl2)
{
    zone_node_entry_t *entry = zone_manager_find_by_mac(sender_mac);
    if (entry) {
        entry->rl1_state = rl1;
        entry->rl2_state = rl2;
        entry->last_seen_ms = (uint32_t)(esp_timer_get_time() / 1000);
        entry->is_online = true;
    }
}

zone_node_entry_t *zone_manager_get_all(int *out_count)
{
    if (out_count) *out_count = s_node_count;
    return s_nodes;
}

void zone_manager_check_timeouts(void)
{
    uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    for (int i = 0; i < s_node_count; i++) {
        if (s_nodes[i].is_online && (now_ms - s_nodes[i].last_seen_ms) > NODE_HEARTBEAT_TIMEOUT_MS) {
            s_nodes[i].is_online = false;
            ESP_LOGW(TAG, "⚠️ Node %s [%02X:%02X:%02X:%02X:%02X:%02X] timed out (offline)",
                     s_nodes[i].device_id,
                     s_nodes[i].mac[0], s_nodes[i].mac[1], s_nodes[i].mac[2],
                     s_nodes[i].mac[3], s_nodes[i].mac[4], s_nodes[i].mac[5]);
        }
    }
}
