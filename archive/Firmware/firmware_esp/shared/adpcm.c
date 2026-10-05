/*
 * IMA-ADPCM Audio Codec — Implementation
 * DTV Smart Home — Shared Audio Compression for ESP-NOW (4:1 compression)
 */

#include "adpcm.h"

/* Intel/DVI/IMA ADPCM step size table (89 entries) */
static const int16_t step_table[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

/* Intel/DVI/IMA ADPCM index table (16 entries) */
static const int8_t index_table[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
};

static inline uint8_t adpcm_encode_sample(int16_t val, adpcm_state_t *state)
{
    int diff = val - state->valprev;
    uint8_t code = 0;
    int step = step_table[state->index];
    int vpdiff = step >> 3;

    if (diff < 0) {
        code |= 8;
        diff = -diff;
    }
    if (diff >= step) {
        code |= 4;
        diff -= step;
        vpdiff += step;
    }
    step >>= 1;
    if (diff >= step) {
        code |= 2;
        diff -= step;
        vpdiff += step;
    }
    step >>= 1;
    if (diff >= step) {
        code |= 1;
        vpdiff += step;
    }

    int32_t new_val = state->valprev;
    if (code & 8) {
        new_val -= vpdiff;
    } else {
        new_val += vpdiff;
    }

    if (new_val > 32767) new_val = 32767;
    else if (new_val < -32768) new_val = -32768;
    state->valprev = (int16_t)new_val;

    state->index += index_table[code & 0x0f];
    if (state->index < 0) state->index = 0;
    else if (state->index > 88) state->index = 88;

    return code & 0x0f;
}

static inline int16_t adpcm_decode_sample(uint8_t code, adpcm_state_t *state)
{
    int step = step_table[state->index];
    int vpdiff = step >> 3;

    if (code & 4) vpdiff += step;
    if (code & 2) vpdiff += (step >> 1);
    if (code & 1) vpdiff += (step >> 2);

    int32_t val = state->valprev;
    if (code & 8) {
        val -= vpdiff;
    } else {
        val += vpdiff;
    }

    if (val > 32767) val = 32767;
    else if (val < -32768) val = -32768;
    state->valprev = (int16_t)val;

    state->index += index_table[code & 0x0f];
    if (state->index < 0) state->index = 0;
    else if (state->index > 88) state->index = 88;

    return state->valprev;
}

int adpcm_encode(const int16_t *in, int in_samples, uint8_t *out, adpcm_state_t *state)
{
    if (!in || !out || !state || in_samples <= 0) return 0;

    int out_bytes = 0;
    for (int i = 0; i < in_samples; i += 2) {
        uint8_t nibble0 = adpcm_encode_sample(in[i], state);
        uint8_t nibble1 = 0;
        if (i + 1 < in_samples) {
            nibble1 = adpcm_encode_sample(in[i + 1], state);
        }
        out[out_bytes++] = (nibble0 & 0x0f) | ((nibble1 & 0x0f) << 4);
    }
    return out_bytes;
}

int adpcm_decode(const uint8_t *in, int in_bytes, int16_t *out, adpcm_state_t *state)
{
    if (!in || !out || !state || in_bytes <= 0) return 0;

    int out_samples = 0;
    for (int i = 0; i < in_bytes; i++) {
        uint8_t b = in[i];
        out[out_samples++] = adpcm_decode_sample(b & 0x0f, state);
        out[out_samples++] = adpcm_decode_sample((b >> 4) & 0x0f, state);
    }
    return out_samples;
}
