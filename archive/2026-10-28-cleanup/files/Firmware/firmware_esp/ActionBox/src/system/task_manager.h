#pragma once

#include "esp_err.h"
#include "actionbox_protocol.h"
#include "current_sensor.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t mac[6];
    uint8_t payload[768];
    size_t  len;
} NetworkPacket;

esp_err_t task_manager_init(void);

esp_err_t task_manager_post_command(const ActionBoxCommand *cmd);

esp_err_t task_manager_post_network_rx(const uint8_t *src_mac, const uint8_t *data, size_t len);

esp_err_t task_manager_post_network_tx(const uint8_t *dest_mac, const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
