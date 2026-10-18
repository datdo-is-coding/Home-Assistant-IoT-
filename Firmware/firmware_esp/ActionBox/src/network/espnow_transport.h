#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*espnow_rx_cb_t)(const uint8_t *mac_addr, const uint8_t *data, int len);

esp_err_t espnow_transport_init(void);

void espnow_transport_register_rx_callback(espnow_rx_cb_t cb);

esp_err_t espnow_transport_send(const uint8_t *payload, size_t len);

esp_err_t espnow_transport_send_to(const uint8_t *dest_mac, const uint8_t *payload, size_t len);

esp_err_t espnow_transport_pair_subbox(const uint8_t *subbox_mac);

bool espnow_transport_is_paired(void);

void espnow_transport_get_local_mac(uint8_t *out_mac);

void espnow_transport_scan_channels(void);

void espnow_transport_hop_channel(void);

#ifdef __cplusplus
}
#endif
