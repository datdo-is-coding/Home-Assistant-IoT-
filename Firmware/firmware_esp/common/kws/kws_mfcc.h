#pragma once

#include <stdint.h>
#include <math.h>
#include "kws_config.h"

class MFCCExtractor {
public:
    MFCCExtractor();
    ~MFCCExtractor();

    bool init();

    void extract(const float* audio_in, float* mfcc_out);

private:
    float* m_emphasized;
    float hamming_window[FRAME_LEN_SAMPLES];
    float mel_filters[NUM_MEL_FILTERS][FFT_SIZE / 2 + 1];
    float dct_matrix[NUM_MFCC_COEFFS][NUM_MEL_FILTERS];
    float lifter[NUM_MFCC_COEFFS];

    void init_hamming();
    void init_mel_filterbank();
    void init_dct();
    void init_lifter();

    void rfft(const float* input, float* real_out, float* imag_out);
};
