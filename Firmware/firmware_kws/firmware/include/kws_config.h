#ifndef KWS_CONFIG_H
#define KWS_CONFIG_H

#include <driver/i2s.h>
#include <stdint.h>

#define I2S_PORT I2S_NUM_0
#define MIC_I2S_GPIO_BCLK GPIO_NUM_15
#define MIC_I2S_GPIO_WS GPIO_NUM_16
#define MIC_I2S_GPIO_DIN GPIO_NUM_8

#define RELAY_1_PIN GPIO_NUM_4
#define RELAY_2_PIN GPIO_NUM_5

#define RELAY_ON_LEVEL LOW
#define RELAY_OFF_LEVEL HIGH

#define LED_STATUS_PIN 2

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

#define USE_QUANTIZED_MODEL 1

#endif
