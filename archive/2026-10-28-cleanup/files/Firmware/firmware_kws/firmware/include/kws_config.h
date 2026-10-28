#ifndef KWS_CONFIG_H
#define KWS_CONFIG_H

#include <driver/i2s.h>
#include <stdint.h>

// Microphone I2S Master RX (ActionBox V2: BCLK=IO47, WS=IO48, DIN=IO8)
#define I2S_PORT                I2S_NUM_0
#define MIC_I2S_GPIO_BCLK       GPIO_NUM_47
#define MIC_I2S_GPIO_WS         GPIO_NUM_48
#define MIC_I2S_GPIO_DIN        GPIO_NUM_8

// Speaker Amplifier Shutdown Pin (MAX98357 SD: LOW = shutdown)
#define SPEAKER_SD_PIN          GPIO_NUM_38

// Đèn LED chỉ báo (ActionBox V2: LED1 = IO3, LED2/Voice = IO2)
#define LED_1_PIN               3
#define LED_2_PIN               2
#define LED_STATUS_PIN          LED_2_PIN
#define LED_ACTIVE_LEVEL        HIGH

// Relay Latching Dual-Coil HKE3-LT-S (ActionBox V2: 3 kênh, xung kích 50ms)
#define RELAY_LATCH_PULSE_MS    50

// Kênh 1: ĐÈN
#define RELAY_1_SET_PIN         GPIO_NUM_16
#define RELAY_1_RESET_PIN       GPIO_NUM_15

// Kênh 2: QUẠT
#define RELAY_2_SET_PIN         GPIO_NUM_7
#define RELAY_2_RESET_PIN       GPIO_NUM_6

// Kênh 3: Dự phòng
#define RELAY_3_SET_PIN         GPIO_NUM_5
#define RELAY_3_RESET_PIN       GPIO_NUM_4

// Macro tương thích ngược
#define RELAY_1_PIN             RELAY_1_SET_PIN
#define RELAY_2_PIN             RELAY_2_SET_PIN
#define RELAY_ON_LEVEL          HIGH
#define RELAY_OFF_LEVEL         LOW

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
