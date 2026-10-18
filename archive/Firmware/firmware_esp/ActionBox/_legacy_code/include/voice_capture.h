#ifndef VOICE_CAPTURE_H
#define VOICE_CAPTURE_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t voice_capture_init(void);

bool voice_capture_is_streaming(void);

void voice_capture_start_streaming(uint8_t trigger_source);

void voice_capture_stop_streaming(void);

#ifdef __cplusplus
}
#endif

#endif
