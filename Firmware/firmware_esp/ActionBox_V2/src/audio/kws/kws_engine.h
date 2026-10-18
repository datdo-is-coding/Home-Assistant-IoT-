#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t kws_engine_init(void);

void kws_engine_feed_samples(const int16_t *pcm, size_t count);

bool kws_engine_step(int *out_class_id, float *out_confidence);

bool kws_engine_is_observation_mode(void);

void kws_engine_set_observation_mode(bool enable);

#ifdef __cplusplus
}
#endif
