/*
 * ESP-NOW Master — Implementation
 * DTV Smart Home — T2 Zone Controller
 */

#include "espnow_master.h"
#include "zone_manager.h"
#include "audio_proxy.h"
#include "mqtt_zone.h"
#include "t2_config.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_idf_version.h"
#include "esp_mac.h"
#include "esp_timer.h"

static const char *TAG = "ESPNOW_MASTER";

static uint8_t s_broadcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static volatile uint8_t s_relay_cmd_seq = 0;

/* ─── Forward Declarations ───────────────────────────────────────────── */

static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
                           const uint8_t *data, int len);
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status);
#else
static void espnow_send_cb(const uint8_t *mac_addr, esp_now_send_status_t status);
#endif
static void ensure_peer_exists(const uint8_t *mac);
static void zone_watchdog_task(void *arg);

/* ─── Public API ─────────────────────────────────────────────────────── */

esp_err_t espnow_master_init(void)
{
    ESP_LOGI(TAG, "Initializing ESP-NOW Master Mode...");

    /* ESP-NOW core init (Wi-Fi must already be started in STA or AP+STA) */
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv_cb));
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_cb));

    /* Add broadcast peer */
    ensure_peer_exists(s_broadcast_mac);

    uint8_t my_mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, my_mac);
    ESP_LOGI(TAG, "T2 Controller MAC: %02X:%02X:%02X:%02X:%02X:%02X (Channel %d)",
             my_mac[0], my_mac[1], my_mac[2], my_mac[3], my_mac[4], my_mac[5],
             ESPNOW_WIFI_CHANNEL);

    /* Start background watchdog to monitor T1 node heartbeats */
    xTaskCreate(zone_watchdog_task, "zone_watchdog", 3072, NULL, 3, NULL);

    ESP_LOGI(TAG, "ESP-NOW Master active. Listening for T1 node discovery & telemetry...");
    return ESP_OK;
}

esp_err_t espnow_master_send_relay_cmd(const uint8_t *target_mac, uint8_t channel, uint8_t state)
{
    if (!target_mac) return ESP_ERR_INVALID_ARG;

    ensure_peer_exists(target_mac);

    espnow_relay_cmd_t cmd = {
        .msg_type = MSG_TYPE_RELAY_CMD,
        .seq = ++s_relay_cmd_seq,
        .channel = channel,
        .state = state,
        .timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000),
    };

    esp_err_t err = esp_now_send(target_mac, (const uint8_t *)&cmd, sizeof(cmd));
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "⚡ Sent RELAY_CMD CH%d=%d (seq=%d) to %02X:%02X:%02X:%02X:%02X:%02X",
                 channel, state, cmd.seq,
                 target_mac[0], target_mac[1], target_mac[2],
                 target_mac[3], target_mac[4], target_mac[5]);
    } else {
        ESP_LOGE(TAG, "Failed to send RELAY_CMD: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t espnow_master_send_node_cfg(const uint8_t *target_mac, const espnow_node_cfg_t *cfg)
{
    if (!target_mac || !cfg) return ESP_ERR_INVALID_ARG;

    ensure_peer_exists(target_mac);

    return esp_now_send(target_mac, (const uint8_t *)cfg, sizeof(espnow_node_cfg_t));
}

/* ─── Internal Helper: Peer Management ───────────────────────────────── */

static void ensure_peer_exists(const uint8_t *mac)
{
    if (!esp_now_is_peer_exist(mac)) {
        esp_now_peer_info_t peer = {0};
        memcpy(peer.peer_addr, mac, 6);
        peer.channel = ESPNOW_WIFI_CHANNEL;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = false;
        esp_err_t err = esp_now_add_peer(&peer);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to add ESP-NOW peer %02X:%02X:%02X:%02X:%02X:%02X: %s",
                     mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], esp_err_to_name(err));
        }
    }
}

/* ─── ESP-NOW Callbacks ──────────────────────────────────────────────── */

static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
                           const uint8_t *data, int len)
{
    if (len < 1) return;

    const uint8_t *src_mac = recv_info->src_addr;
    uint8_t msg_type = data[0];

    switch (msg_type) {
    case MSG_TYPE_NODE_HELLO: {
        if (len >= (int)sizeof(espnow_node_hello_t)) {
            const espnow_node_hello_t *hello = (const espnow_node_hello_t *)data;
            ensure_peer_exists(src_mac);

            zone_node_entry_t *node = zone_manager_register_hello(hello, src_mac);

            /* Send NODE_HELLO_ACK back to T1 */
            espnow_node_hello_ack_t ack = {0};
            ack.msg_type = MSG_TYPE_NODE_HELLO_ACK;
            ack.seq = hello->seq;
            ack.channel = ESPNOW_WIFI_CHANNEL;
            ack.registered = 1;
            ack.cfg_version = hello->cfg_version;
            strncpy(ack.zone_name, zone_manager_get_zone_name(), sizeof(ack.zone_name) - 1);

            esp_now_send(src_mac, (const uint8_t *)&ack, sizeof(ack));

            /* Publish discovery / status to MQTT */
            if (node) {
                mqtt_zone_publish_node_status(node);
            }
        }
        break;
    }

    case MSG_TYPE_RELAY_ACK: {
        if (len >= (int)sizeof(espnow_relay_ack_t)) {
            const espnow_relay_ack_t *ack = (const espnow_relay_ack_t *)data;
            zone_manager_update_relay(src_mac, ack->rl1_state, ack->rl2_state);

            zone_node_entry_t *node = zone_manager_find_by_mac(src_mac);
            if (node) {
                mqtt_zone_publish_relay_state(node->device_id, 1, ack->rl1_state);
                mqtt_zone_publish_relay_state(node->device_id, 2, ack->rl2_state);
            }
            ESP_LOGI(TAG, "✅ RELAY_ACK from %02X:%02X:%02X:%02X:%02X:%02X: RL1=%d, RL2=%d",
                     src_mac[0], src_mac[1], src_mac[2], src_mac[3], src_mac[4], src_mac[5],
                     ack->rl1_state, ack->rl2_state);
        }
        break;
    }

    case MSG_TYPE_AUDIO_START: {
        if (len >= (int)sizeof(espnow_audio_start_t)) {
            const espnow_audio_start_t *start = (const espnow_audio_start_t *)data;
            audio_proxy_on_stream_start(src_mac, start->wake_word_index, start->codec);
        }
        break;
    }

    case MSG_TYPE_AUDIO_CHUNK: {
        if (len >= 4) {
            const espnow_audio_chunk_t *chunk = (const espnow_audio_chunk_t *)data;
            audio_proxy_on_chunk(src_mac, chunk->pcm_data, chunk->pcm_len);
        }
        break;
    }

    case MSG_TYPE_AUDIO_END: {
        if (len >= (int)sizeof(espnow_audio_end_t)) {
            const espnow_audio_end_t *end_pkt = (const espnow_audio_end_t *)data;
            audio_proxy_on_stream_end(src_mac, end_pkt->total_chunks, end_pkt->total_pcm_bytes);
        }
        break;
    }

    case MSG_TYPE_RESP_POWER_STATUS: {
        if (len >= (int)sizeof(esp_now_packet_t)) {
            const esp_now_packet_t *tele = (const esp_now_packet_t *)data;
            zone_node_entry_t *node = zone_manager_find_by_mac(src_mac);
            const char *dev_id = node ? node->device_id : "unknown";
            mqtt_zone_publish_telemetry(dev_id, tele);
        }
        break;
    }

    default:
        ESP_LOGD(TAG, "Unhandled ESP-NOW msg 0x%02X from %02X:%02X:%02X:%02X:%02X:%02X",
                 msg_type, src_mac[0], src_mac[1], src_mac[2],
                 src_mac[3], src_mac[4], src_mac[5]);
        break;
    }
}

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status)
{
    if (status != ESP_NOW_SEND_SUCCESS && tx_info && tx_info->des_addr) {
        ESP_LOGD(TAG, "ESP-NOW master send fail to %02X:%02X:%02X:%02X:%02X:%02X",
                 tx_info->des_addr[0], tx_info->des_addr[1], tx_info->des_addr[2],
                 tx_info->des_addr[3], tx_info->des_addr[4], tx_info->des_addr[5]);
    }
}
#else
static void espnow_send_cb(const uint8_t *mac_addr, esp_now_send_status_t status)
{
    if (status != ESP_NOW_SEND_SUCCESS && mac_addr) {
        ESP_LOGD(TAG, "ESP-NOW master send fail to %02X:%02X:%02X:%02X:%02X:%02X",
                 mac_addr[0], mac_addr[1], mac_addr[2],
                 mac_addr[3], mac_addr[4], mac_addr[5]);
    }
}
#endif

/* ─── Watchdog Task ──────────────────────────────────────────────────── */

static void zone_watchdog_task(void *arg)
{
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(15000));
        zone_manager_check_timeouts();
        mqtt_zone_publish_zone_summary();
    }
}
