/**
 * @file espnow_transport.cpp
 * @brief Reliable ESP-NOW Network Transport Layer Implementation
 */

#include "espnow_transport.h"
#include "app_config.h"
#include "nvs_storage.h"
#include "safety_supervisor.h"

#include <string.h>
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_now.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "ESPNOW_TRANSPORT";

static const uint8_t s_broadcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static uint8_t s_subbox_mac[6] = {0};
static bool s_has_paired_subbox = false;
static espnow_rx_cb_t s_rx_callback = NULL;
static SemaphoreHandle_t s_transport_mutex = NULL;
static bool s_initialized = false;

#include "esp_idf_version.h"

static void on_espnow_recv(const esp_now_recv_info_t *recv_info, const uint8_t *data, int len) {
    if (!recv_info || !data || len <= 0) return;

    if (s_rx_callback) {
        s_rx_callback(recv_info->src_addr, data, len);
    }
}

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 0, 0)
static void on_espnow_send(const wifi_tx_info_t *tx_info, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS && tx_info) {
        ESP_LOGD(TAG, "ESP-NOW delivery fail to %02X:%02X:%02X:%02X:%02X:%02X",
                 tx_info->des_addr[0], tx_info->des_addr[1], tx_info->des_addr[2],
                 tx_info->des_addr[3], tx_info->des_addr[4], tx_info->des_addr[5]);
    }
}
#else
static void on_espnow_send(const uint8_t *mac_addr, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS && mac_addr) {
        ESP_LOGD(TAG, "ESP-NOW delivery fail to %02X:%02X:%02X:%02X:%02X:%02X",
                 mac_addr[0], mac_addr[1], mac_addr[2], mac_addr[3], mac_addr[4], mac_addr[5]);
    }
}
#endif

esp_err_t espnow_transport_init(void) {
    if (s_initialized) return ESP_OK;

    ESP_LOGI(TAG, "Initializing Wi-Fi and ESP-NOW transport...");
    s_transport_mutex = xSemaphoreCreateMutex();
    if (!s_transport_mutex) return ESP_ERR_NO_MEM;

    esp_err_t err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "esp_netif_init failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "event_loop_create failed: %s", esp_err_to_name(err));
        return err;
    }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_init failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err != ESP_OK) return err;

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) return err;

    err = esp_wifi_start();
    if (err != ESP_OK) return err;

    /* Disable power saving for instant relay actuation response */
    esp_wifi_set_ps(WIFI_PS_NONE);
    /* Must match the SubBox AP channel; peers follow the active radio channel. */
    ESP_ERROR_CHECK(esp_wifi_set_channel(APP_ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE));

    uint8_t local_mac[6];
    esp_read_mac(local_mac, ESP_MAC_WIFI_STA);
    ESP_LOGI(TAG, "Local ActionBox Wi-Fi MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             local_mac[0], local_mac[1], local_mac[2], local_mac[3], local_mac[4], local_mac[5]);

    err = esp_now_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_now_init failed: %s", esp_err_to_name(err));
        return err;
    }

    esp_now_register_recv_cb(on_espnow_recv);
    esp_now_register_send_cb(on_espnow_send);

    /* Register Broadcast Peer */
    esp_now_peer_info_t bcast_peer = {};
    memcpy(bcast_peer.peer_addr, s_broadcast_mac, 6);
    bcast_peer.channel = 0;
    bcast_peer.ifidx = WIFI_IF_STA;
    bcast_peer.encrypt = false;
    err = esp_now_add_peer(&bcast_peer);
    if (err != ESP_OK && err != ESP_ERR_ESPNOW_EXIST) {
        ESP_LOGE(TAG, "Failed to register broadcast peer: %s", esp_err_to_name(err));
        return err;
    }

    /* Check if paired SubBox MAC is saved in NVS */
    const ActionBoxPersistentConfig *stored_cfg = nvs_storage_get_cached_config();
    if (stored_cfg->has_assigned_subbox) {
        espnow_transport_pair_subbox(stored_cfg->assigned_subbox_mac);
    }

    s_initialized = true;
    ESP_LOGI(TAG, "ESP-NOW transport ready on channel %d.", APP_ESPNOW_CHANNEL);
    return ESP_OK;
}

void espnow_transport_register_rx_callback(espnow_rx_cb_t cb) {
    s_rx_callback = cb;
}

esp_err_t espnow_transport_pair_subbox(const uint8_t *subbox_mac) {
    if (!subbox_mac) return ESP_ERR_INVALID_ARG;

    if (xSemaphoreTake(s_transport_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    if (esp_now_is_peer_exist(subbox_mac)) {
        esp_now_del_peer(subbox_mac);
    }

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, subbox_mac, 6);
    peer.channel = 0;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;

    esp_err_t err = esp_now_add_peer(&peer);
    if (err == ESP_OK) {
        memcpy(s_subbox_mac, subbox_mac, 6);
        s_has_paired_subbox = true;
        ESP_LOGI(TAG, "Successfully paired with SubBox MAC: %02X:%02X:%02X:%02X:%02X:%02X",
                 s_subbox_mac[0], s_subbox_mac[1], s_subbox_mac[2],
                 s_subbox_mac[3], s_subbox_mac[4], s_subbox_mac[5]);
    } else {
        ESP_LOGE(TAG, "Failed to add SubBox peer: %s", esp_err_to_name(err));
    }

    xSemaphoreGive(s_transport_mutex);
    return err;
}

esp_err_t espnow_transport_send(const uint8_t *payload, size_t len) {
    if (!payload || len == 0 || len > ESP_NOW_MAX_DATA_LEN_V2) return ESP_ERR_INVALID_ARG;

    const uint8_t *target_mac = s_has_paired_subbox ? s_subbox_mac : s_broadcast_mac;
    return espnow_transport_send_to(target_mac, payload, len);
}

esp_err_t espnow_transport_send_to(const uint8_t *dest_mac, const uint8_t *payload, size_t len) {
    if (!dest_mac || !payload || len == 0 || len > ESP_NOW_MAX_DATA_LEN_V2) return ESP_ERR_INVALID_ARG;

    if (xSemaphoreTake(s_transport_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    /* Auto-register peer if not already in table */
    if (!esp_now_is_peer_exist(dest_mac)) {
        esp_now_peer_info_t peer = {};
        memcpy(peer.peer_addr, dest_mac, 6);
        peer.channel = 0;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = false;
        esp_now_add_peer(&peer);
    }

    esp_err_t err = esp_now_send(dest_mac, payload, len);
    xSemaphoreGive(s_transport_mutex);
    return err;
}

bool espnow_transport_is_paired(void) {
    return s_has_paired_subbox;
}

void espnow_transport_get_local_mac(uint8_t *out_mac) {
    if (out_mac) {
        esp_read_mac(out_mac, ESP_MAC_WIFI_STA);
    }
}

void espnow_transport_scan_channels(void) {
    if (!s_has_paired_subbox) return;
    ESP_LOGW(TAG, "Heartbeat lost >10s. Scanning channels 1-13 for paired SubBox...");
    uint8_t orig_ch = APP_ESPNOW_CHANNEL;
    wifi_second_chan_t second;
    esp_wifi_get_channel(&orig_ch, &second);

    for (uint8_t ch = 1; ch <= 13; ch++) {
        esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
        vTaskDelay(pdMS_TO_TICKS(500));
        if (!safety_is_network_timed_out()) {
            ESP_LOGI(TAG, "Reconnected to SubBox on channel %u! Locking channel.", ch);
            return;
        }
    }
    esp_wifi_set_channel(orig_ch, WIFI_SECOND_CHAN_NONE);
}

void espnow_transport_hop_channel(void) {
    static uint8_t s_scan_ch = 1;
    s_scan_ch = (s_scan_ch % 13) + 1;
    esp_wifi_set_channel(s_scan_ch, WIFI_SECOND_CHAN_NONE);
    ESP_LOGD(TAG, "Scanning Wi-Fi channel %u for SubBox heartbeat...", s_scan_ch);
}
