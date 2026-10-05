#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CHIME_WAKE = 0,             /* Crisp 'Ding-Dong' when Jarvis wakes up */
    CHIME_STOP,                 /* Soft boop when voice recording finishes */
    CHIME_STARTUP,              /* Ascending melody on boot */
} chime_type_t;

/**
 * @brief Initialize MAX98357A I2S speaker driver and SD mute control.
 */
esp_err_t audio_output_init(void);

/**
 * @brief Play a system chime with smooth envelope and auto-muting.
 */
void audio_output_play_chime(chime_type_t type);

/**
 * @brief Play back clean voice buffer through speaker with soft anti-pop ramp.
 *
 * @param samples Pointer to 16-bit mono 16kHz audio samples.
 * @param sample_count Number of samples.
 */
void audio_output_play_voice(const int16_t *samples, int sample_count);

/**
 * @brief Set hardware amplifier mute state (SPK_SD_GPIO).
 */
void audio_output_set_mute(bool mute);

#ifdef __cplusplus
}
#endif
