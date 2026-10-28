#ifndef AUDIO_FEEDBACK_H
#define AUDIO_FEEDBACK_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "driver/i2s_std.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    AUDIO_FB_BOOTUP = 0,
    AUDIO_FB_SUCCESS,
    AUDIO_FB_NOTI,
    AUDIO_FB_WRONG,

    AUDIO_FB_CONNECTED = AUDIO_FB_SUCCESS,
    AUDIO_FB_WAKEUP = AUDIO_FB_SUCCESS,
    AUDIO_FB_RECORDING_DONE = AUDIO_FB_SUCCESS,
    AUDIO_FB_TING = AUDIO_FB_SUCCESS,
    AUDIO_FB_ERROR = AUDIO_FB_WRONG,
    AUDIO_FB_DISCONNECT_REMIND = AUDIO_FB_WRONG,
} audio_feedback_type_t;

esp_err_t audio_feedback_init(i2s_chan_handle_t spk_handle);

void audio_feedback_play(audio_feedback_type_t type);

void audio_feedback_start_disconnect_loop(int interval_sec);

void audio_feedback_stop_disconnect_loop(void);

bool audio_feedback_lock(TickType_t timeout);

void audio_feedback_unlock(void);

#ifdef __cplusplus
}
#endif

#endif
