/*
 * Audio Proxy — T2 Zone Controller
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Bridges audio between T1 Actuator Nodes and Gateway:
 *   - Receives raw PCM chunks over ESP-NOW from T1
 *   - Feeds PCM to Gateway WebSocket server (ASR/Whisper)
 *   - Plays WakeNet chime ("Ding!") on local MAX98357A speaker
 *   - Receives TTS audio stream from Gateway and plays on speaker
 */

#ifndef AUDIO_PROXY_H
#define AUDIO_PROXY_H

#include "esp_err.h"
#include "driver/i2s_std.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize Audio Proxy with I2S speaker handle and Gateway WebSocket URI.
 * @param gateway_ws_uri  WebSocket endpoint (e.g. "ws://192.168.11.29:8765")
 * @param spk_handle      I2S TX handle for MAX98357A speaker
 */
esp_err_t audio_proxy_init(const char *gateway_ws_uri, i2s_chan_handle_t spk_handle);

/**
 * @brief Called when a T1 node detects wake word ("Hi ESP").
 * Plays local chime and starts WebSocket audio stream to Gateway.
 * @param sender_mac       MAC address of the T1 node that triggered wake word
 * @param wake_word_index  Index of wake word
 * @param codec            Codec type (CODEC_RAW_PCM or CODEC_IMA_ADPCM)
 */
void audio_proxy_on_stream_start(const uint8_t *sender_mac, uint8_t wake_word_index, uint8_t codec);

/**
 * @brief Called when a T1 node sends a PCM audio chunk.
 * Forwards PCM samples to Gateway WebSocket client.
 * @param sender_mac  MAC address of T1 node
 * @param pcm_data    Raw PCM 16-bit audio
 * @param pcm_len     Length in bytes
 */
void audio_proxy_on_chunk(const uint8_t *sender_mac, const uint8_t *pcm_data, uint16_t pcm_len);

/**
 * @brief Called when a T1 node completes voice capture (silence/timeout).
 * @param sender_mac       MAC address of T1 node
 * @param total_chunks     Total chunks sent
 * @param total_pcm_bytes  Total bytes captured
 */
void audio_proxy_on_stream_end(const uint8_t *sender_mac, uint16_t total_chunks, uint32_t total_pcm_bytes);

/**
 * @brief Check if audio proxy is currently receiving or streaming audio.
 */
bool audio_proxy_is_active(void);

#ifdef __cplusplus
}
#endif

#endif /* AUDIO_PROXY_H */
