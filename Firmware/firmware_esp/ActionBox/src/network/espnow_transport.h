/**
 * @file espnow_transport.h
 * @brief Reliable ESP-NOW Network Transport Layer for ActionBox <-> SubBox
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*espnow_rx_cb_t)(const uint8_t *mac_addr, const uint8_t *data, int len);

/**
 * @brief Initialize Wi-Fi in Station mode and initialize ESP-NOW
 * @return ESP_OK on success
 */
esp_err_t espnow_transport_init(void);

/**
 * @brief Register callback function for incoming ESP-NOW packets
 * @param cb Callback function pointer
 */
void espnow_transport_register_rx_callback(espnow_rx_cb_t cb);

/**
 * @brief Transmit packet to assigned SubBox (or broadcast if unpaired)
 * @param payload Pointer to data buffer
 * @param len Data length (max 250 bytes)
 * @return ESP_OK on success
 */
esp_err_t espnow_transport_send(const uint8_t *payload, size_t len);

/**
 * @brief Transmit packet to a specific destination MAC address
 * @param dest_mac 6-byte destination MAC
 * @param payload Pointer to data buffer
 * @param len Data length
 * @return ESP_OK on success
 */
esp_err_t espnow_transport_send_to(const uint8_t *dest_mac, const uint8_t *payload, size_t len);

/**
 * @brief Pair with a SubBox MAC address and store in peer table
 * @param subbox_mac 6-byte SubBox MAC address
 * @return ESP_OK on success
 */
esp_err_t espnow_transport_pair_subbox(const uint8_t *subbox_mac);

/**
 * @brief Check if ActionBox has an active paired SubBox
 * @return true if paired, false otherwise
 */
bool espnow_transport_is_paired(void);

/**
 * @brief Retrieve local Wi-Fi MAC address of this ActionBox
 * @param out_mac 6-byte buffer for MAC address
 */
void espnow_transport_get_local_mac(uint8_t *out_mac);

/**
 * @brief Scan Wi-Fi channels 1-13 to find paired SubBox upon 10s heartbeat loss
 */
void espnow_transport_scan_channels(void);

/**
 * @brief Non-blocking single-channel hop across channels 1-13
 */
void espnow_transport_hop_channel(void);

#ifdef __cplusplus
}
#endif
