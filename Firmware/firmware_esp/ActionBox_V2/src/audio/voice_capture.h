#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t voice_capture_init(void);

bool voice_capture_is_streaming(void);
bool voice_capture_request_followup(void);

void voice_capture_start_streaming(uint8_t trigger_source);

void voice_capture_stop_streaming(void);

void voice_capture_set_vad_threshold(int64_t energy_threshold);

void voice_capture_get_diagnostics(float *out_rms, bool *out_is_speech);

#ifdef __cplusplus
}
#endif
