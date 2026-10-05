/*
 * ESP-NOW Slave — T1 Actuator Node
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Handles all ESP-NOW communication with T2 Zone Controller:
 *   - Receive relay commands → drive GPIO
 *   - Receive config updates → save to NVS
 *   - Send heartbeat/hello periodically
 *   - Send audio stream chunks (called from voice_capture.c)
 *   - Send PZEM telemetry (called from telemetry.c)
 *
 * This module is ESP-NOW ONLY — no Wi-Fi STA, no MQTT, no WebSocket.
 */

#ifndef ESPNOW_SLAVE_H
#define ESPNOW_SLAVE_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize ESP-NOW in slave mode (Wi-Fi STA + ESP-NOW, no AP).
 * Sets up Wi-Fi in STA mode (without connecting to AP) for ESP-NOW only.
 * Registers send/receive callbacks.
 * Starts heartbeat task.
 * @return ESP_OK on success
 */
esp_err_t espnow_slave_init(void);

/**
 * @brief Send an audio start notification to T2.
 * Called when WakeNet detects wake word.
 * @param wake_word_index  Which wake word was detected (0 = "Hi ESP")
 */
esp_err_t espnow_slave_send_audio_start(uint8_t wake_word_index);

/**
 * @brief Send a PCM audio chunk to T2.
 * @param pcm_data  Raw PCM 16-bit samples
 * @param pcm_len   Length in bytes (max ESPNOW_AUDIO_MAX_PCM_BYTES = 240)
 */
esp_err_t espnow_slave_send_audio_chunk(const uint8_t *pcm_data, uint16_t pcm_len);

/**
 * @brief Send audio end notification to T2.
 * Called when VAD detects silence end.
 * @param total_chunks     Total chunks sent in this session
 * @param total_pcm_bytes  Total PCM bytes sent
 */
esp_err_t espnow_slave_send_audio_end(uint16_t total_chunks, uint32_t total_pcm_bytes);

/**
 * @brief Send PZEM telemetry data to T2.
 * Uses legacy esp_now_packet_t format for backward compatibility.
 */
esp_err_t espnow_slave_send_telemetry(const esp_now_packet_t *tele);

/**
 * @brief Check if T2 Zone Controller has been discovered.
 * @return true if T2 peer MAC is known
 */
bool espnow_slave_is_paired(void);

/**
 * @brief Get the T2 Zone Controller's MAC address.
 * @param mac_out  Output buffer (6 bytes)
 * @return ESP_OK if paired, ESP_ERR_NOT_FOUND if not
 */
esp_err_t espnow_slave_get_t2_mac(uint8_t *mac_out);

#ifdef __cplusplus
}
#endif

#endif /* ESPNOW_SLAVE_H */
