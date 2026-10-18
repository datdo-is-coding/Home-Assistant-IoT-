#ifndef AUDIO_PROXY_H
#define AUDIO_PROXY_H

#include "esp_err.h"
#include "driver/i2s_std.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t audio_proxy_init(const char *gateway_ws_uri, i2s_chan_handle_t spk_handle);

void audio_proxy_on_stream_start(const uint8_t *sender_mac, uint8_t wake_word_index, uint8_t codec);

void audio_proxy_on_chunk(const uint8_t *sender_mac, const uint8_t *pcm_data, uint16_t pcm_len);

void audio_proxy_on_stream_end(const uint8_t *sender_mac, uint16_t total_chunks, uint32_t total_pcm_bytes);

bool audio_proxy_is_active(void);

#ifdef __cplusplus
}
#endif

#endif
