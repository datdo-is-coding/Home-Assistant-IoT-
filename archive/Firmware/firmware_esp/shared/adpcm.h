#ifndef ADPCM_H
#define ADPCM_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int16_t valprev;
    int8_t  index;
} adpcm_state_t;

static inline void adpcm_init_state(adpcm_state_t *state) {
    if (state) {
        state->valprev = 0;
        state->index = 0;
    }
}

int adpcm_encode(const int16_t *in, int in_samples, uint8_t *out, adpcm_state_t *state);

int adpcm_decode(const uint8_t *in, int in_bytes, int16_t *out, adpcm_state_t *state);

#ifdef __cplusplus
}
#endif

#endif
