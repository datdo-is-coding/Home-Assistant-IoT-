/*
 * Audio Feedback Chime & Tone Synthesizer — Header
 * Generates clean PCM audio feedback signals (16kHz 16-bit Mono)
 * for ESP32-S3 I2S speaker (MAX98357A).
 *
 * Events:
 *   - Server Connected: Ascending 3-tone arpeggio
 *   - Wake Word ("Hi ESP"): Crisp "Ding!" prompt
 *   - Done Listening: Subtle confirmation blip
 *   - System Error / Disconnect: Low warning buzz
 */

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
    AUDIO_FB_BOOTUP = 0,        /* System bootup chime (bootup_sound, 1.92s) */
    AUDIO_FB_SUCCESS,           /* Recognition / connection success / stable (listen_success, 1.15s) */
    AUDIO_FB_NOTI,              /* Proactive notification / new alert (new_noti, 2.40s) */
    AUDIO_FB_WRONG,             /* Disconnect alert / unrecognized command / error (wrong_sound, 1.27s) */

    /* Aliases replacing old synthetic tones */
    AUDIO_FB_CONNECTED = AUDIO_FB_SUCCESS,
    AUDIO_FB_WAKEUP = AUDIO_FB_SUCCESS,
    AUDIO_FB_RECORDING_DONE = AUDIO_FB_SUCCESS,
    AUDIO_FB_TING = AUDIO_FB_SUCCESS,
    AUDIO_FB_ERROR = AUDIO_FB_WRONG,
    AUDIO_FB_DISCONNECT_REMIND = AUDIO_FB_WRONG,
} audio_feedback_type_t;

/**
 * @brief Initialize the audio feedback synthesizer.
 * @param spk_handle I2S TX channel handle for speaker
 * @return ESP_OK on success
 */
esp_err_t audio_feedback_init(i2s_chan_handle_t spk_handle);

/**
 * @brief Play an audio feedback cue through the speaker.
 *        Automatically enables the MAX98357A amplifier, plays the synthesized
 *        envelope-ramped waveform, flushes I2S DMA, and returns amplifier to shutdown.
 * @param type Feedback sound type to play
 */
void audio_feedback_play(audio_feedback_type_t type);

/**
 * @brief Start periodic gentle disconnect reminder loop (plays every interval_sec).
 */
void audio_feedback_start_disconnect_loop(int interval_sec);

/**
 * @brief Stop periodic disconnect reminder loop when connection is restored.
 */
void audio_feedback_stop_disconnect_loop(void);

/**
 * @brief Acquire speaker hardware lock (mutex) for exclusive access.
 */
bool audio_feedback_lock(TickType_t timeout);

/**
 * @brief Release speaker hardware lock.
 */
void audio_feedback_unlock(void);

#ifdef __cplusplus
}
#endif

#endif /* AUDIO_FEEDBACK_H */
