/*
 * ESP-NOW Slave — Implementation
 * DTV Smart Home — T1 Actuator Node
 *
 * ESP-NOW only communication (no Wi-Fi STA connection needed).
 * Broadcasts hello on boot → T2 Zone Controller discovers and adds as peer.
 * Once paired, all communication is unicast to T2's MAC.
 */

#include "espnow_slave.h"
#include "t1_config.h"
#include "relay_driver.h"
#include "device_identity.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_idf_version.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "nvs_flash.h"

static const char *TAG = "ESPNOW_SLAVE";

/* ─── State ──────────────────────────────────────────────────────────── */

static uint8_t s_broadcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static uint8_t s_t2_mac[6] = {0};
static volatile bool s_t2_paired = false;
static volatile uint8_t s_audio_seq = 0;
static volatile uint8_t s_hello_seq = 0;
static uint32_t s_boot_time_ms = 0;

/* ─── Forward Declarations ───────────────────────────────────────────── */

static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
                           const uint8_t *data, int len);
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status);
#else
static void espnow_send_cb(const uint8_t *mac_addr, esp_now_send_status_t status);
#endif
static void heartbeat_task(void *arg);
static void handle_relay_cmd(const uint8_t *sender_mac,
                             const espnow_relay_cmd_t *cmd);
static void handle_node_cfg(const uint8_t *sender_mac,
                            const espnow_node_cfg_t *cfg);
static void send_hello(void);

/* ─── Public API ─────────────────────────────────────────────────────── */

esp_err_t espnow_slave_init(void)
{
    s_boot_time_ms = (uint32_t)(esp_timer_get_time() / 1000);

    ESP_LOGI(TAG, "Initializing ESP-NOW Slave Mode (Wi-Fi channel %d)...", ESPNOW_WIFI_CHANNEL);

    /* Initialize Wi-Fi in STA mode (required for ESP-NOW) but DON'T connect to AP */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.static_rx_buf_num = 4;
    cfg.dynamic_rx_buf_num = 8;
    cfg.dynamic_tx_buf_num = 8;
    cfg.mgmt_sbuf_num = 8;
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    /* Set Wi-Fi channel to match T2 Zone Controller */
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_channel(ESPNOW_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

    /* Initialize ESP-NOW */
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv_cb));
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_cb));

    /* Add broadcast peer for initial hello discovery */
    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, s_broadcast_mac, 6);
    peer.channel = ESPNOW_WIFI_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    uint8_t my_mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, my_mac);
    ESP_LOGI(TAG, "T1 Node MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             my_mac[0], my_mac[1], my_mac[2], my_mac[3], my_mac[4], my_mac[5]);

    /* Start heartbeat task */
    xTaskCreate(heartbeat_task, "t1_heartbeat", 3072, NULL, 3, NULL);

    /* Send initial hello broadcast */
    send_hello();

    ESP_LOGI(TAG, "ESP-NOW Slave initialized. Broadcasting hello to find T2 Zone Controller...");
    return ESP_OK;
}

esp_err_t espnow_slave_send_audio_start(uint8_t wake_word_index)
{
    s_audio_seq = 0;

    espnow_audio_start_t pkt = {0};
    pkt.msg_type = MSG_TYPE_AUDIO_START;
    pkt.seq = s_audio_seq;
    pkt.sample_rate = AUDIO_SAMPLE_RATE;
    pkt.bits_per_sample = AUDIO_BITS;
    pkt.channels = AUDIO_CHANNELS;
    pkt.wake_word_index = wake_word_index;
#if HAS_ADPCM
    pkt.codec = CODEC_IMA_ADPCM;
#else
    pkt.codec = CODEC_RAW_PCM;
#endif
    pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

    const uint8_t *dest = s_t2_paired ? s_t2_mac : s_broadcast_mac;
    esp_err_t err = esp_now_send(dest, (const uint8_t *)&pkt, sizeof(pkt));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send AUDIO_START: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "🎤 AUDIO_START sent (wake_word=%d)", wake_word_index);
    }
    return err;
}

esp_err_t espnow_slave_send_audio_chunk(const uint8_t *pcm_data, uint16_t pcm_len)
{
    if (pcm_len > ESPNOW_AUDIO_MAX_PCM_BYTES) {
        pcm_len = ESPNOW_AUDIO_MAX_PCM_BYTES;
    }

    espnow_audio_chunk_t pkt;
    pkt.msg_type = MSG_TYPE_AUDIO_CHUNK;
    pkt.seq = ++s_audio_seq;
    pkt.pcm_len = pcm_len;
    memcpy(pkt.pcm_data, pcm_data, pcm_len);

    /* Only send header + actual data, not the full 244 bytes */
    size_t send_len = 4 + pcm_len;

    const uint8_t *dest = s_t2_paired ? s_t2_mac : s_broadcast_mac;
    return esp_now_send(dest, (const uint8_t *)&pkt, send_len);
}

esp_err_t espnow_slave_send_audio_end(uint16_t total_chunks, uint32_t total_pcm_bytes)
{
    espnow_audio_end_t pkt = {0};
    pkt.msg_type = MSG_TYPE_AUDIO_END;
    pkt.seq = s_audio_seq;
    pkt.total_chunks = total_chunks;
    pkt.total_pcm_bytes = total_pcm_bytes;

    const uint8_t *dest = s_t2_paired ? s_t2_mac : s_broadcast_mac;
    esp_err_t err = esp_now_send(dest, (const uint8_t *)&pkt, sizeof(pkt));
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "🎤 AUDIO_END sent (chunks=%d, bytes=%lu)",
                 total_chunks, (unsigned long)total_pcm_bytes);
    }

    s_audio_seq = 0;
    return err;
}

esp_err_t espnow_slave_send_telemetry(const esp_now_packet_t *tele)
{
    const uint8_t *dest = s_t2_paired ? s_t2_mac : s_broadcast_mac;
    return esp_now_send(dest, (const uint8_t *)tele, sizeof(esp_now_packet_t));
}

bool espnow_slave_is_paired(void)
{
    return s_t2_paired;
}

esp_err_t espnow_slave_get_t2_mac(uint8_t *mac_out)
{
    if (!s_t2_paired) return ESP_ERR_NOT_FOUND;
    memcpy(mac_out, s_t2_mac, 6);
    return ESP_OK;
}

/* ─── Internal: ESP-NOW Receive Callback ─────────────────────────────── */

static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
                           const uint8_t *data, int len)
{
    if (len < 1) return;

    uint8_t msg_type = data[0];

    switch (msg_type) {
    case MSG_TYPE_RELAY_CMD:
        if (len >= (int)sizeof(espnow_relay_cmd_t)) {
            handle_relay_cmd(recv_info->src_addr, (const espnow_relay_cmd_t *)data);
        }
        break;

    case MSG_TYPE_NODE_HELLO_ACK:
        /* T2 acknowledged our hello — save T2's MAC for future unicast */
        if (!s_t2_paired) {
            memcpy(s_t2_mac, recv_info->src_addr, 6);
            s_t2_paired = true;

            /* Add T2 as unicast peer */
            esp_now_peer_info_t peer = {0};
            memcpy(peer.peer_addr, s_t2_mac, 6);
            peer.channel = ESPNOW_WIFI_CHANNEL;
            peer.ifidx = WIFI_IF_STA;
            peer.encrypt = false;

            if (!esp_now_is_peer_exist(s_t2_mac)) {
                esp_now_add_peer(&peer);
            }

            ESP_LOGI(TAG, "✅ Paired with T2 Zone Controller: %02X:%02X:%02X:%02X:%02X:%02X",
                     s_t2_mac[0], s_t2_mac[1], s_t2_mac[2],
                     s_t2_mac[3], s_t2_mac[4], s_t2_mac[5]);
        }
        break;

    case MSG_TYPE_NODE_CFG:
        if (len >= (int)sizeof(espnow_node_cfg_t)) {
            handle_node_cfg(recv_info->src_addr, (const espnow_node_cfg_t *)data);
        }
        break;

    case MSG_TYPE_REQ_POWER_STATUS:
        /* Legacy: T2 requesting telemetry — will be handled by telemetry.c polling */
        ESP_LOGD(TAG, "Received REQ_POWER_STATUS from T2");
        break;

    default:
        ESP_LOGW(TAG, "Unknown ESP-NOW msg type: 0x%02X (len=%d)", msg_type, len);
        break;
    }
}

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status)
{
    if (status != ESP_NOW_SEND_SUCCESS && tx_info && tx_info->des_addr) {
        ESP_LOGD(TAG, "ESP-NOW send failed to %02X:%02X:%02X:%02X:%02X:%02X",
                 tx_info->des_addr[0], tx_info->des_addr[1], tx_info->des_addr[2],
                 tx_info->des_addr[3], tx_info->des_addr[4], tx_info->des_addr[5]);
    }
}
#else
static void espnow_send_cb(const uint8_t *mac_addr, esp_now_send_status_t status)
{
    if (status != ESP_NOW_SEND_SUCCESS && mac_addr) {
        ESP_LOGD(TAG, "ESP-NOW send failed to %02X:%02X:%02X:%02X:%02X:%02X",
                 mac_addr[0], mac_addr[1], mac_addr[2],
                 mac_addr[3], mac_addr[4], mac_addr[5]);
    }
}
#endif

/* ─── Internal: Handle Relay Command from T2 ─────────────────────────── */

static void handle_relay_cmd(const uint8_t *sender_mac,
                             const espnow_relay_cmd_t *cmd)
{
#if HAS_RELAY
    static uint8_t last_relay_seq = 0xFF;

    /* Dedup: skip if same seq as last executed */
    if (cmd->seq == last_relay_seq) {
        ESP_LOGD(TAG, "Duplicate relay cmd seq=%d, skipping", cmd->seq);
        return;
    }
    last_relay_seq = cmd->seq;

    relay_driver_set(cmd->channel, cmd->state ? true : false);
    ESP_LOGI(TAG, "⚡ Relay CH%d → %s (seq=%d)",
             cmd->channel, cmd->state ? "ON" : "OFF", cmd->seq);

    /* Send ACK back to T2 */
    espnow_relay_ack_t ack = {0};
    ack.msg_type = MSG_TYPE_RELAY_ACK;
    ack.seq = cmd->seq;
    ack.rl1_state = relay_driver_get(1) ? 1 : 0;
    ack.rl2_state = relay_driver_get(2) ? 1 : 0;
    ack.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

    esp_now_send(sender_mac, (const uint8_t *)&ack, sizeof(ack));
#else
    ESP_LOGW(TAG, "Relay command received but HAS_RELAY=0");
#endif
}

/* ─── Internal: Handle Config from T2 ────────────────────────────────── */

static void handle_node_cfg(const uint8_t *sender_mac,
                            const espnow_node_cfg_t *cfg)
{
    ESP_LOGI(TAG, "📋 Received config from T2: room='%s', rl1='%s', rl2='%s', v=%lu",
             cfg->room, cfg->rl1_name, cfg->rl2_name, (unsigned long)cfg->cfg_version);

    /* Save to NVS via device_identity module */
    user_identity_t user = {0};
    strncpy(user.room, cfg->room, sizeof(user.room) - 1);
    strncpy(user.rl1_name, cfg->rl1_name, sizeof(user.rl1_name) - 1);
    strncpy(user.rl2_name, cfg->rl2_name, sizeof(user.rl2_name) - 1);
    user.cfg_version = cfg->cfg_version;
    user.is_provisioned = true;

    device_identity_save_user_config(&user);

    /* Send CFG ACK */
    espnow_header_t ack = {
        .msg_type = MSG_TYPE_NODE_CFG_ACK,
        .seq = cfg->seq,
        .reserved = 0,
    };
    esp_now_send(sender_mac, (const uint8_t *)&ack, sizeof(ack));
}

/* ─── Internal: Send Hello / Heartbeat ───────────────────────────────── */

static void send_hello(void)
{
    const hardware_identity_t *hw = device_identity_get_hardware();
    const user_identity_t *usr = device_identity_get_user();

    espnow_node_hello_t hello = {0};
    hello.msg_type = MSG_TYPE_NODE_HELLO;
    hello.seq = ++s_hello_seq;
    memcpy(hello.mac, hw->mac_raw, 6);
    strncpy(hello.device_id, hw->device_id, ESPNOW_DEVICE_ID_LEN - 1);

#if HAS_RELAY
    hello.rl1_state = relay_driver_get(1) ? 1 : 0;
    hello.rl2_state = relay_driver_get(2) ? 1 : 0;
#endif

    hello.capabilities = T1_CAPABILITIES;
    hello.is_provisioned = usr->is_provisioned ? 1 : 0;
    hello.cfg_version = usr->cfg_version;
    hello.uptime_s = (uint32_t)((esp_timer_get_time() / 1000000ULL));
    hello.rssi = 0;  /* No Wi-Fi AP connection on T1 */
    hello.fw_major = FW_VERSION_MAJOR;
    hello.fw_minor = FW_VERSION_MINOR;
    hello.fw_patch = FW_VERSION_PATCH;

    const uint8_t *dest = s_t2_paired ? s_t2_mac : s_broadcast_mac;
    esp_now_send(dest, (const uint8_t *)&hello, sizeof(hello));

    ESP_LOGI(TAG, "📡 HELLO sent → %s (id=%s, caps=0x%02X, prov=%d)",
             s_t2_paired ? "T2 unicast" : "broadcast",
             hello.device_id, hello.capabilities, hello.is_provisioned);
}

/* ─── Internal: Heartbeat Task ───────────────────────────────────────── */

static void heartbeat_task(void *arg)
{
    ESP_LOGI(TAG, "Heartbeat task started (adaptive mesh discovery: 2s search, 5s live)");

    while (1) {
        if (!s_t2_paired) {
            vTaskDelay(pdMS_TO_TICKS(2000));
        } else {
            vTaskDelay(pdMS_TO_TICKS(5000));
        }
        send_hello();
    }
}

