/*
 * Audio Feedback Chime & Tone Synthesizer — Implementation
 * DTV Smart Home — ESP32-S3 Master
 */

#include "audio_feedback.h"

#include <math.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"

static const char *TAG = "AUDIO_FEEDBACK";

extern void speaker_enable(bool enable);

static i2s_chan_handle_t spk_tx_handle = NULL;
static SemaphoreHandle_t spk_hw_mutex = NULL;

esp_err_t audio_feedback_init(i2s_chan_handle_t spk_handle)
{
    spk_tx_handle = spk_handle;
    if (!spk_hw_mutex) {
        spk_hw_mutex = xSemaphoreCreateMutex();
    }
    ESP_LOGI(TAG, "Audio Feedback Synthesizer initialized");
    return ESP_OK;
}

bool audio_feedback_lock(TickType_t timeout)
{
    if (!spk_hw_mutex) return true;
    return (xSemaphoreTake(spk_hw_mutex, timeout) == pdTRUE);
}

void audio_feedback_unlock(void)
{
    if (spk_hw_mutex) {
        xSemaphoreGive(spk_hw_mutex);
    }
}

/**
 * @brief Synthesize and write a pure sine tone with linear attack/decay envelope.
 */
static void play_tone(float freq_hz, int duration_ms, float volume)
{
    if (!spk_tx_handle || freq_hz <= 0.0f || duration_ms <= 0) return;

    int num_samples = (16000 * duration_ms) / 1000;
    if (num_samples <= 0) return;

    int16_t *buf = (int16_t *)malloc(num_samples * sizeof(int16_t));
    if (!buf) {
        ESP_LOGE(TAG, "Failed to allocate buffer for tone generation");
        return;
    }

    float step = 2.0f * 3.1415926535f * freq_hz / 16000.0f;
    int ramp_len = num_samples / 4;
    if (ramp_len > 80) ramp_len = 80; /* ~5ms ramp attack / decay */

    for (int i = 0; i < num_samples; i++) {
        float sample = sinf(step * (float)i) * volume * 32767.0f;
        if (i < ramp_len) {
            sample *= ((float)i / (float)ramp_len);
        } else if (i > num_samples - ramp_len) {
            sample *= ((float)(num_samples - i) / (float)ramp_len);
        }
        buf[i] = (int16_t)sample;
    }

    size_t written = 0;
    i2s_channel_write(spk_tx_handle, buf, num_samples * sizeof(int16_t),
                      &written, pdMS_TO_TICKS(duration_ms + 100));

    free(buf);
}

void audio_feedback_play(audio_feedback_type_t type)
{
    if (!spk_tx_handle) {
        ESP_LOGW(TAG, "Cannot play feedback: speaker handle is NULL");
        return;
    }

    if (!audio_feedback_lock(pdMS_TO_TICKS(500))) {
        ESP_LOGW(TAG, "Speaker hardware is busy, skipping feedback tone %d", type);
        return;
    }

    /* 1. Power on / unmute MAX98357A amplifier via SP_SD (GPIO 2) */
    speaker_enable(true);
    vTaskDelay(pdMS_TO_TICKS(25)); /* Allow Amp output stage to settle smoothly */

    switch (type) {
    case AUDIO_FB_CONNECTED:
        /* Upward arpeggio: C5 (523Hz) -> E5 (659Hz) -> G5 (784Hz) */
        ESP_LOGI(TAG, "🔔 Playing feedback: CONNECTED (Chime)");
        play_tone(523.25f, 70, 0.40f);
        play_tone(659.25f, 70, 0.40f);
        play_tone(783.99f, 150, 0.45f);
        break;

    case AUDIO_FB_WAKEUP:
        /* Prompt "Ding!": A5 (880Hz) -> C6 (1046Hz) */
        ESP_LOGI(TAG, "🔔 Playing feedback: WAKEUP (Ding!)");
        play_tone(880.0f, 50, 0.45f);
        play_tone(1046.5f, 90, 0.50f);
        break;

    case AUDIO_FB_RECORDING_DONE:
        /* Gentle confirmation blip: E5 (659Hz) */
        ESP_LOGI(TAG, "🔔 Playing feedback: RECORDING_DONE (Tick)");
        play_tone(659.25f, 60, 0.35f);
        break;

    case AUDIO_FB_ERROR:
        /* Descending warning tone: 330Hz -> 220Hz */
        ESP_LOGI(TAG, "⚠️ Playing feedback: ERROR (Warning)");
        play_tone(329.6f, 100, 0.45f);
        play_tone(220.0f, 160, 0.45f);
        break;
    }

    /* 2. Flush DMA with zero samples so no DC bias or click remains */
    int16_t silence[128];
    memset(silence, 0, sizeof(silence));
    for (int i = 0; i < 4; i++) {
        size_t written = 0;
        i2s_channel_write(spk_tx_handle, silence, sizeof(silence), &written, pdMS_TO_TICKS(50));
    }
    vTaskDelay(pdMS_TO_TICKS(35)); /* Allow DMA to completely clock out zero samples */

    /* 3. Shut down / mute MAX98357A amplifier into 0.01uA sleep */
    speaker_enable(false);

    audio_feedback_unlock();
}
