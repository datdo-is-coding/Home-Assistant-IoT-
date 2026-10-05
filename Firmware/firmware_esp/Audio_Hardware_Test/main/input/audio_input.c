#include "audio_input.h"
#include "../app_config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/i2s_std.h"

static const char *TAG = "AUDIO_IN";

static i2s_chan_handle_t s_mic_rx_handle = NULL;
static int s_mic_channel = 0; /* 0 for Left (L/R=GND), 1 for Right (L/R=VDD) */
static float s_ambient_rms = 30.0f;
static float s_gate_threshold = 50.0f;
static float s_gate_env = 0.0f;
static float s_gate_gain = 0.0f;

/* ─── Biquad Filter Implementation ────────────────────────────────────── */

typedef struct {
    float b0, b1, b2;
    float a1, a2;
    float x1, x2;
    float y1, y2;
} biquad_t;

static inline void biquad_init(biquad_t *f, float b0, float b1, float b2, float a1, float a2)
{
    f->b0 = b0; f->b1 = b1; f->b2 = b2;
    f->a1 = a1; f->a2 = a2;
    f->x1 = 0.0f; f->x2 = 0.0f; f->y1 = 0.0f; f->y2 = 0.0f;
}

static inline float biquad_step(biquad_t *f, float in)
{
    float out = f->b0 * in + f->b1 * f->x1 + f->b2 * f->x2 - f->a1 * f->y1 - f->a2 * f->y2;
    f->x2 = f->x1;
    f->x1 = in;
    f->y2 = f->y1;
    f->y1 = out;
    return out;
}

/* 4th-Order Filters */
static biquad_t s_hpf1, s_hpf2;
static biquad_t s_lpf1, s_lpf2;

/* ─── Audio Input Initialization ─────────────────────────────────────── */

esp_err_t audio_input_init(void)
{
    i2s_chan_config_t chan_cfg = {
        .id = MIC_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &s_mic_rx_handle));

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = MIC_I2S_GPIO_BCLK,
            .ws   = MIC_I2S_GPIO_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = MIC_I2S_GPIO_DIN,
            .invert_flags = {0},
        },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_mic_rx_handle, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(s_mic_rx_handle));

    /* Initialize 4th-Order Linkwitz-Riley HPF @ 180Hz (Fs=16kHz) */
    biquad_init(&s_hpf1, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);
    biquad_init(&s_hpf2, 0.9512454f, -1.9024908f, 0.9512454f, -1.9001124f, 0.9048693f);

    /* Initialize 4th-Order Linkwitz-Riley LPF @ 3400Hz (Fs=16kHz) */
    biquad_init(&s_lpf1, 0.2271180f, 0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);
    biquad_init(&s_lpf2, 0.2271180f, 0.4542359f, 0.2271180f, -0.2766646f, 0.1851365f);

    /* Flush initial startup settling noise */
    vTaskDelay(pdMS_TO_TICKS(100));
    audio_input_flush_buffers();

    /* Calibration: Detect microphone slot (Left vs Right) & calibrate noise floor */
    static int32_t s_cal_buf[AUDIO_FRAME_SAMPLES * 2];
    int64_t l_sum = 0, r_sum = 0;
    float sum_filtered_rms = 0.0f;
    int valid_frames = 0;

    for (int k = 0; k < 6; k++) {
        size_t bytes_read = 0;
        if (i2s_channel_read(s_mic_rx_handle, s_cal_buf, sizeof(s_cal_buf), &bytes_read, pdMS_TO_TICKS(50)) == ESP_OK && bytes_read > 0) {
            int mono_cnt = (bytes_read / sizeof(int32_t)) / 2;
            int64_t sum_sq = 0;
            for (int i = 0; i < mono_cnt; i++) {
                int32_t left_s  = s_cal_buf[i * 2];
                int32_t right_s = s_cal_buf[i * 2 + 1];
                l_sum += (int64_t)abs(left_s >> 16);
                r_sum += (int64_t)abs(right_s >> 16);

                float s = (float)(left_s >> 16);
                s = biquad_step(&s_hpf1, s);
                s = biquad_step(&s_hpf2, s);
                s = biquad_step(&s_lpf1, s);
                s = biquad_step(&s_lpf2, s);
                sum_sq += (int64_t)(s * s);
            }
            if (mono_cnt > 0) {
                sum_filtered_rms += sqrtf((float)(sum_sq / mono_cnt));
                valid_frames++;
            }
        }
    }

    s_mic_channel = (r_sum > l_sum * 2) ? 1 : 0;
    if (valid_frames > 0) {
        s_ambient_rms = sum_filtered_rms / valid_frames;
    }
    s_gate_threshold = s_ambient_rms * 1.8f;
    if (s_gate_threshold < 40.0f) s_gate_threshold = 40.0f;
    if (s_gate_threshold > 140.0f) s_gate_threshold = 140.0f;

    ESP_LOGI(TAG, "✅ Microphone Initialized | Slot: %s | Ambient RMS: %.1f | Gate Thresh: %.1f",
             s_mic_channel == 0 ? "LEFT (L/R=GND)" : "RIGHT (L/R=VDD)",
             s_ambient_rms, s_gate_threshold);

    return ESP_OK;
}

void audio_input_flush_buffers(void)
{
    int32_t dummy[AUDIO_FRAME_SAMPLES * 2];
    size_t br = 0;
    for (int k = 0; k < 4; k++) {
        i2s_channel_read(s_mic_rx_handle, dummy, sizeof(dummy), &br, pdMS_TO_TICKS(30));
    }
}

float audio_input_get_ambient_rms(void)
{
    return s_ambient_rms;
}

esp_err_t audio_input_read_clean(int16_t *out_mono, int samples, float *out_rms)
{
    static int32_t s_raw_stereo[AUDIO_FRAME_SAMPLES * 2];
    size_t bytes_to_read = samples * 2 * sizeof(int32_t);
    if (bytes_to_read > sizeof(s_raw_stereo)) bytes_to_read = sizeof(s_raw_stereo);

    size_t bytes_read = 0;
    esp_err_t ret = i2s_channel_read(s_mic_rx_handle, s_raw_stereo, bytes_to_read,
                                     &bytes_read, pdMS_TO_TICKS(100));
    if (ret != ESP_OK || bytes_read == 0) {
        return ESP_FAIL;
    }

    int read_mono = (bytes_read / sizeof(int32_t)) / 2;
    if (read_mono > samples) read_mono = samples;

    int64_t sum_sq = 0;
    for (int i = 0; i < read_mono; i++) {
        /* Extract from locked channel */
        int32_t raw_32 = s_raw_stereo[i * 2 + s_mic_channel];
        float in_sample = (float)(raw_32 >> 16);

        /* 4th-Order Bandpass: 180Hz HPF + 3400Hz LPF */
        float s = biquad_step(&s_hpf1, in_sample);
        s = biquad_step(&s_hpf2, s);
        s = biquad_step(&s_lpf1, s);
        s = biquad_step(&s_lpf2, s);

        /* Envelope Follower */
        float abs_s = fabsf(s);
        if (abs_s > s_gate_env) {
            s_gate_env += 0.04f * (abs_s - s_gate_env);   /* Fast attack ~1.5ms */
        } else {
            s_gate_env += 0.001f * (abs_s - s_gate_env);  /* Smooth release ~60ms */
        }

        /* Downward Expander (Noise Gate down to true 0.0) */
        float target_gain = 0.0f;
        if (s_gate_env > s_gate_threshold * 1.5f) {
            target_gain = 1.0f;
        } else if (s_gate_env > s_gate_threshold) {
            target_gain = (s_gate_env - s_gate_threshold) / (0.5f * s_gate_threshold);
        } else {
            target_gain = 0.0f;
        }
        s_gate_gain += 0.02f * (target_gain - s_gate_gain);

        float clean = s * s_gate_gain;
        if (clean > 32767.0f) clean = 32767.0f;
        if (clean < -32768.0f) clean = -32768.0f;

        out_mono[i] = (int16_t)clean;
        sum_sq += (int64_t)out_mono[i] * out_mono[i];
    }

    if (out_rms) {
        *out_rms = sqrtf((float)(sum_sq / read_mono));
    }

    return ESP_OK;
}

bool audio_input_is_speech(float frame_rms)
{
    float speech_thresh = s_ambient_rms * 2.2f;
    if (speech_thresh < 120.0f) {
        speech_thresh = 120.0f;
    }
    return (frame_rms >= speech_thresh);
}

