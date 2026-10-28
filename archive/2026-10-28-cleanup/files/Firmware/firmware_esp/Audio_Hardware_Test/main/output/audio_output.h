#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CHIME_WAKE = 0,
    CHIME_STOP,
    CHIME_STARTUP,
} chime_type_t;

esp_err_t audio_output_init(void);

void audio_output_play_chime(chime_type_t type);

void audio_output_play_voice(const int16_t *samples, int sample_count);

void audio_output_set_mute(bool mute);

#ifdef __cplusplus
}
#endif
