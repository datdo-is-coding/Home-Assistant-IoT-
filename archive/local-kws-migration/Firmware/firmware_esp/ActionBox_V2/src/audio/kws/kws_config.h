#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SAMPLE_RATE 16000
#define AUDIO_WINDOW_MS 1000
#define AUDIO_STEP_MS 250

#define TOTAL_SAMPLES (SAMPLE_RATE * AUDIO_WINDOW_MS / 1000)
#define STEP_SAMPLES (SAMPLE_RATE * AUDIO_STEP_MS / 1000)

#define FRAME_LEN_SAMPLES 320
#define FRAME_STEP_SAMPLES 160
#define FFT_SIZE 512
#define NUM_MEL_FILTERS 32
#define NUM_MFCC_COEFFS 13
#define NUM_FRAMES 99

#define NORM_MEAN (-9.295776f)
#define NORM_STD (35.392517f)

#define NUM_CLASSES 10

enum KwsClassId {
    CLASS_BAT     = 0,
    CLASS_BEP     = 1,
    CLASS_KHACH   = 2,
    CLASS_NGU     = 3,
    CLASS_NOISE   = 4,
    CLASS_PHONG   = 5,
    CLASS_QUAT    = 6,
    CLASS_TAT     = 7,
    CLASS_UNKNOWN = 8,
    CLASS_DEN     = 9
};

static const char *const KWS_LABELS[NUM_CLASSES] = {
    "bật",
    "bếp",
    "khách",
    "ngủ",
    "noise",
    "phòng",
    "quạt",
    "tắt",
    "unknown",
    "đèn"
};

#define CONFIDENCE_THRESHOLD 0.40f
#define COOLDOWN_MS 500

#ifdef __cplusplus
}
#endif
