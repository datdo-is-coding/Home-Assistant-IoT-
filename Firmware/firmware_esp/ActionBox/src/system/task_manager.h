/**
 * @file task_manager.h
 * @brief FreeRTOS Task Architecture & Inter-Task Queue Management for ActionBox
 */

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

/**
 * @brief Create all FreeRTOS queues, semaphores, and spawn core tasks
 * @return ESP_OK on success
 */
esp_err_t task_manager_init(void);

/**
 * @brief Post a command to the command execution queue
 * @param cmd Pointer to command struct
 * @return ESP_OK on success
 */
esp_err_t task_manager_post_command(const ActionBoxCommand *cmd);

/**
 * @brief Post an incoming network packet to the network task queue
 * @param src_mac 6-byte source MAC
 * @param data Packet data
 * @param len Data length
 * @return ESP_OK on success
 */
esp_err_t task_manager_post_network_rx(const uint8_t *src_mac, const uint8_t *data, size_t len);

/**
 * @brief Post an outbound packet to the network transmit queue
 * @param dest_mac 6-byte destination MAC (or NULL for default SubBox)
 * @param data Packet data
 * @param len Data length
 * @return ESP_OK on success
 */
esp_err_t task_manager_post_network_tx(const uint8_t *dest_mac, const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
