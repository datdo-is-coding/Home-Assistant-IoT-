/*
 * IMA-ADPCM Audio Codec — Header
 * DTV Smart Home — Shared Audio Compression for ESP-NOW (4:1 compression)
 */

#ifndef ADPCM_H
#define ADPCM_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int16_t valprev;   /* Previous output value */
    int8_t  index;     /* Index into stepsize table (0..88) */
} adpcm_state_t;

/**
 * @brief Initialize ADPCM state structure
 */
static inline void adpcm_init_state(adpcm_state_t *state) {
    if (state) {
        state->valprev = 0;
        state->index = 0;
    }
}

/**
 * @brief Encode a buffer of 16-bit linear PCM samples into 4-bit IMA-ADPCM.
 * @param in Pointer to 16-bit PCM samples
 * @param in_samples Number of 16-bit samples (must be even)
 * @param out Output buffer for packed ADPCM bytes (must be at least in_samples / 2 bytes)
 * @param state State tracking struct (updated across calls)
 * @return Number of encoded bytes written to out (in_samples / 2)
 */
int adpcm_encode(const int16_t *in, int in_samples, uint8_t *out, adpcm_state_t *state);

/**
 * @brief Decode a buffer of 4-bit IMA-ADPCM bytes into 16-bit linear PCM samples.
 * @param in Pointer to packed ADPCM bytes
 * @param in_bytes Number of ADPCM bytes
 * @param out Output buffer for 16-bit PCM samples (must be at least in_bytes * 2 samples)
 * @param state State tracking struct (updated across calls)
 * @return Number of decoded samples written to out (in_bytes * 2)
 */
int adpcm_decode(const uint8_t *in, int in_bytes, int16_t *out, adpcm_state_t *state);

#ifdef __cplusplus
}
#endif

#endif /* ADPCM_H */
