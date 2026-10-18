#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t audio_input_init(void);

esp_err_t audio_input_read_clean(int16_t *out_mono, int samples, float *out_rms);

void audio_input_flush_buffers(void);

bool audio_input_is_speech(float frame_rms);

#ifdef __cplusplus
}
#endif
