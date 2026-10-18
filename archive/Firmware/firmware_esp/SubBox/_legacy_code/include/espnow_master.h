#ifndef ESPNOW_MASTER_H
#define ESPNOW_MASTER_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t espnow_master_init(void);

esp_err_t espnow_master_send_relay_cmd(const uint8_t *target_mac, uint8_t channel, uint8_t state);

esp_err_t espnow_master_send_node_cfg(const uint8_t *target_mac, const espnow_node_cfg_t *cfg);

#ifdef __cplusplus
}
#endif

#endif
