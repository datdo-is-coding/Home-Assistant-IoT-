#include "audio_output.h"
#include "../app_config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"

static const char *TAG = "AUDIO_OUT";

static i2s_chan_handle_t s_spk_tx_handle = NULL;

/* ─── Speaker Initialization ─────────────────────────────────────────── */

esp_err_t audio_output_init(void)
{
    /* 1. Configure Amp Enable (SD) GPIO */
    gpio_config_t sd_cfg = {
        .pin_bit_mask = (1ULL << SPK_SD_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&sd_cfg);
    gpio_set_level(SPK_SD_GPIO, 0); /* Start Muted */

    /* 2. Configure I2S1 Master Transmitter */
    i2s_chan_config_t chan_cfg = {
        .id = SPK_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &s_spk_tx_handle, NULL));

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SPK_I2S_GPIO_BCLK,
            .ws   = SPK_I2S_GPIO_WS,
            .dout = SPK_I2S_GPIO_DOUT,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {0},
        },
    };
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH; /* Duplicate mono to Left & Right */
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_spk_tx_handle, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(s_spk_tx_handle));

    ESP_LOGI(TAG, "✅ MAX98357A I2S Speaker Initialized (Muted in standby)");
    return ESP_OK;
}

void audio_output_set_mute(bool mute)
{
    gpio_set_level(SPK_SD_GPIO, mute ? 0 : 1);
}

#include "esp_sound_assets.h"

static void play_pcm_asset(const uint8_t *pcm_bytes, size_t len, float volume)
{
    if (!s_spk_tx_handle || !pcm_bytes || len == 0) return;

    /* Unmute amplifier */
    gpio_set_level(SPK_SD_GPIO, 1);
    vTaskDelay(pdMS_TO_TICKS(20));

    static int16_t s_play_chunk[AUDIO_FRAME_SAMPLES];
    const int16_t *src_samples = (const int16_t *)pcm_bytes;
    size_t total_samples = len / sizeof(int16_t);
    size_t samples_sent = 0;

    /* Anti-pop soft fade-in on first 80 samples, fade-out on last 120 samples */
    while (samples_sent < total_samples) {
        size_t chunk = total_samples - samples_sent;
        if (chunk > AUDIO_FRAME_SAMPLES) chunk = AUDIO_FRAME_SAMPLES;

        for (size_t i = 0; i < chunk; i++) {
            size_t idx = samples_sent + i;
            float env = 1.0f;
            if (idx < 80) {
                env = (float)idx / 80.0f;
            } else if (total_samples - idx < 120) {
                env = (float)(total_samples - idx) / 120.0f;
            }
            int32_t val = (int32_t)((float)src_samples[idx] * volume * env);
            if (val > 32767) val = 32767;
            if (val < -32768) val = -32768;
            s_play_chunk[i] = (int16_t)val;
        }

        size_t written = 0;
        i2s_channel_write(s_spk_tx_handle, s_play_chunk, chunk * sizeof(int16_t), &written, pdMS_TO_TICKS(100));
        samples_sent += chunk;
    }

    /* Trailing zero padding to clear DMA buffer without pop */
    int16_t silence[160] = {0};
    size_t written = 0;
    i2s_channel_write(s_spk_tx_handle, silence, sizeof(silence), &written, pdMS_TO_TICKS(50));
    vTaskDelay(pdMS_TO_TICKS(15));

    /* Mute amplifier */
    gpio_set_level(SPK_SD_GPIO, 0);
}

void audio_output_play_chime(chime_type_t type)
{
    if (type == CHIME_WAKE) {
        /* Only ONE gentle acoustic chime when starting to record (~0.45s) */
        ESP_LOGI(TAG, "🔔 [CHIME] Playing gentle 'listen_success' prompt...");
        size_t chime_len = (listen_success_pcm_len > 14400) ? 14400 : listen_success_pcm_len;
        play_pcm_asset(listen_success_pcm, chime_len, 0.45f);
    }
    /* Ensure amplifier is muted in standby */
    gpio_set_level(SPK_SD_GPIO, 0);
}



/* ─── Voice Playback ─────────────────────────────────────────────────── */

void audio_output_play_voice(const int16_t *samples, int sample_count)
{
    if (!s_spk_tx_handle || sample_count <= 0) return;

    /* Copy samples into a temporary local buffer for normalization & ramp */
    int16_t *play_buf = (int16_t *)malloc(sample_count * sizeof(int16_t));
    if (!play_buf) {
        ESP_LOGE(TAG, "Failed to allocate memory for playback normalization!");
        return;
    }
    memcpy(play_buf, samples, sample_count * sizeof(int16_t));

    /* Auto-normalize speech volume */
    int16_t max_amp = 0;
    for (int i = 0; i < sample_count; i++) {
        int16_t a = abs(play_buf[i]);
        if (a > max_amp) max_amp = a;
    }

    if (max_amp > 100 && max_amp < 18000) {
        float boost = 18000.0f / (float)max_amp;
        if (boost > 3.0f) boost = 3.0f;
        for (int i = 0; i < sample_count; i++) {
            int32_t val = (int32_t)((float)play_buf[i] * boost);
            if (val > 32767) val = 32767;
            if (val < -32768) val = -32768;
            play_buf[i] = (int16_t)val;
        }
    }

    /* Anti-pop soft ramp on edges */
    int fade_len = (sample_count < 80) ? sample_count : 80;
    for (int i = 0; i < fade_len; i++) {
        float f = (float)i / (float)fade_len;
        play_buf[i] = (int16_t)((float)play_buf[i] * f);
        int tail_idx = sample_count - 1 - i;
        play_buf[tail_idx] = (int16_t)((float)play_buf[tail_idx] * f);
    }

    /* Play cue chime */
    audio_output_play_chime(CHIME_STOP);
    vTaskDelay(pdMS_TO_TICKS(40));

    /* Unmute Amp */
    gpio_set_level(SPK_SD_GPIO, 1);
    vTaskDelay(pdMS_TO_TICKS(20));

    /* Stream to I2S speaker */
    int play_offset = 0;
    while (play_offset < sample_count) {
        int to_write = sample_count - play_offset;
        if (to_write > AUDIO_FRAME_SAMPLES) to_write = AUDIO_FRAME_SAMPLES;

        size_t written = 0;
        i2s_channel_write(s_spk_tx_handle, &play_buf[play_offset],
                          to_write * sizeof(int16_t), &written, pdMS_TO_TICKS(100));
        play_offset += to_write;
    }

    /* Drain DMA buffers with silence */
    int16_t drain_silence[AUDIO_FRAME_SAMPLES] = {0};
    size_t written = 0;
    i2s_channel_write(s_spk_tx_handle, drain_silence, sizeof(drain_silence), &written, pdMS_TO_TICKS(100));
    vTaskDelay(pdMS_TO_TICKS(40));

    /* Mute amplifier immediately */
    gpio_set_level(SPK_SD_GPIO, 0);

    free(play_buf);
    ESP_LOGI(TAG, "✅ Finished playing back %d samples.", sample_count);
}
