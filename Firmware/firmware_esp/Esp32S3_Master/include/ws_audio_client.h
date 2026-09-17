/*
 * WebSocket Audio Client — Header
 * Handles two-way audio streaming between ESP32-S3 and Raspberry Pi 4.
 * Streams mic PCM to Pi for ASR, receives TTS PCM for speaker playback.
 */

#ifndef WS_AUDIO_CLIENT_H
#define WS_AUDIO_CLIENT_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/i2s_std.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Audio streaming state machine */
typedef enum {
    WS_STATE_IDLE = 0,       /* Waiting for WakeNet trigger */
    WS_STATE_STREAMING,      /* Mic audio being sent to Pi */
    WS_STATE_PROCESSING,     /* Waiting for Pi to process (ASR+LLM+TTS) */
    WS_STATE_PLAYING,        /* Playing TTS response on speaker */
} ws_audio_state_t;

/**
 * @brief Initialize WebSocket audio client.
 *        Creates WS connection, stream buffers, and background tasks.
 * @param uri         WebSocket server URI (e.g. "ws://192.168.11.29:8765")
 * @param spk_handle  I2S TX channel handle for speaker playback
 * @return ESP_OK on success
 */
esp_err_t ws_audio_client_init(const char *uri, i2s_chan_handle_t spk_handle);

/**
 * @brief Start streaming mic audio to Pi.
 *        Called after WakeNet detects wake word.
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE if not connected or already streaming
 */
esp_err_t ws_audio_start_stream(void);

/**
 * @brief Feed PCM audio data into the WebSocket stream buffer.
 *        Called from audio_feed_task() when streaming is active.
 * @param pcm_data    16-bit signed PCM samples (16kHz mono)
 * @param num_samples Number of samples in pcm_data
 */
void ws_audio_feed_pcm(const int16_t *pcm_data, int num_samples);

/**
 * @brief Check if currently streaming mic audio.
 * @return true if state is WS_STATE_STREAMING
 */
bool ws_audio_is_streaming(void);

/**
 * @brief Get current state of the audio client.
 * @return Current ws_audio_state_t
 */
ws_audio_state_t ws_audio_get_state(void);

/**
 * @brief Check if a follow-up conversation turn is currently pending.
 * @return true if follow-up active
 */
bool ws_audio_is_followup_pending(void);

#ifdef __cplusplus
}
#endif

#endif /* WS_AUDIO_CLIENT_H */
