#ifndef ESPNOW_SLAVE_H
#define ESPNOW_SLAVE_H

#include "esp_err.h"
#include "esp_now_protocol.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t espnow_slave_init(void);

esp_err_t espnow_slave_send_audio_start(uint8_t wake_word_index);

esp_err_t espnow_slave_send_audio_chunk(const uint8_t *pcm_data, uint16_t pcm_len);

esp_err_t espnow_slave_send_audio_end(uint16_t total_chunks, uint32_t total_pcm_bytes);

esp_err_t espnow_slave_send_telemetry(const esp_now_packet_t *tele);

bool espnow_slave_is_paired(void);

esp_err_t espnow_slave_get_t2_mac(uint8_t *mac_out);

#ifdef __cplusplus
}
#endif

#endif
