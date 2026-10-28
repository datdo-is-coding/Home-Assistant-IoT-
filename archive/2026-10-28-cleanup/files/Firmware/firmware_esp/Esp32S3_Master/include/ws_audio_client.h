#ifndef WS_AUDIO_CLIENT_H
#define WS_AUDIO_CLIENT_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/i2s_std.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    WS_STATE_IDLE = 0,
    WS_STATE_STREAMING,
    WS_STATE_PROCESSING,
    WS_STATE_PLAYING,
} ws_audio_state_t;

esp_err_t ws_audio_client_init(const char *uri, i2s_chan_handle_t spk_handle);

esp_err_t ws_audio_client_start(void);

esp_err_t ws_audio_start_stream(void);

void ws_audio_feed_pcm(const int16_t *pcm_data, int num_samples);

bool ws_audio_is_streaming(void);

ws_audio_state_t ws_audio_get_state(void);

bool ws_audio_is_followup_pending(void);

void ws_audio_client_reconnect(void);

void ws_audio_reset_state(void);

void ws_audio_set_state(ws_audio_state_t state);

bool ws_audio_is_speaker_busy(void);

#ifdef __cplusplus
}
#endif

#endif
