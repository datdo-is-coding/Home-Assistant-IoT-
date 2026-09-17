/*
 * Audio Feedback Chime & Tone Synthesizer — Implementation
 * DTV Smart Home — ESP32-S3 Master
 */

#include "audio_feedback.h"
#include "esp_sound_assets.h"

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
    ESP_LOGI(TAG, "Studio Acoustic Soundscapes Audio System initialized");
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
 * @brief Play a raw 16kHz 16-bit Mono PCM soundscape asset from flash via DMA SRAM bounce buffer.
 */
static void play_pcm_asset(const uint8_t *pcm_data, size_t pcm_len)
{
    if (!spk_tx_handle || !pcm_data || pcm_len == 0) return;

    uint8_t ram_chunk[1024];
    size_t offset = 0;
    while (offset < pcm_len) {
        size_t to_write = (pcm_len - offset > sizeof(ram_chunk)) ? sizeof(ram_chunk) : (pcm_len - offset);
        memcpy(ram_chunk, &pcm_data[offset], to_write);
        size_t bytes_written = 0;
        esp_err_t err = i2s_channel_write(spk_tx_handle, ram_chunk, to_write, &bytes_written, pdMS_TO_TICKS(500));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "I2S write warning: %s", esp_err_to_name(err));
            break;
        }
        offset += bytes_written;
    }
}

void audio_feedback_play(audio_feedback_type_t type)
{
    if (!spk_tx_handle) {
        ESP_LOGW(TAG, "Cannot play feedback: speaker handle is NULL");
        return;
    }

    if (!audio_feedback_lock(pdMS_TO_TICKS(500))) {
        ESP_LOGW(TAG, "Speaker hardware is busy, skipping sound type %d", type);
        return;
    }

    /* 1. Power on / unmute MAX98357A amplifier via SP_SD (GPIO 2) */
    speaker_enable(true);
    vTaskDelay(pdMS_TO_TICKS(25)); /* Allow Amp output stage to settle smoothly */

    switch (type) {
    case AUDIO_FB_BOOTUP:
        ESP_LOGI(TAG, "🚀 Playing sound: BOOTUP_SOUND (1.92s raw PCM, %d bytes)", (int)bootup_sound_pcm_len);
        play_pcm_asset(bootup_sound_pcm, bootup_sound_pcm_len);
        break;

    case AUDIO_FB_SUCCESS:
        ESP_LOGI(TAG, "✨ Playing sound: LISTEN_SUCCESS (1.15s raw PCM, %d bytes)", (int)listen_success_pcm_len);
        play_pcm_asset(listen_success_pcm, listen_success_pcm_len);
        break;

    case AUDIO_FB_NOTI:
        ESP_LOGI(TAG, "🔔 Playing sound: NEW_NOTI (2.40s raw PCM, %d bytes)", (int)new_noti_pcm_len);
        play_pcm_asset(new_noti_pcm, new_noti_pcm_len);
        break;

    case AUDIO_FB_WRONG:
        ESP_LOGI(TAG, "⚠️ Playing sound: WRONG_SOUND (1.27s raw PCM, %d bytes)", (int)wrong_sound_pcm_len);
        play_pcm_asset(wrong_sound_pcm, wrong_sound_pcm_len);
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

/* ─── Disconnect Periodic Reminder Loop (FreeRTOS Timer) ────────────────── */
#include "freertos/timers.h"
static TimerHandle_t disconnect_timer = NULL;

static void disconnect_timer_callback(TimerHandle_t xTimer)
{
    audio_feedback_play(AUDIO_FB_DISCONNECT_REMIND);
}

void audio_feedback_start_disconnect_loop(int interval_sec)
{
    if (interval_sec < 3) interval_sec = 8;
    if (!disconnect_timer) {
        disconnect_timer = xTimerCreate(
            "disc_remind_tmr",
            pdMS_TO_TICKS(interval_sec * 1000),
            pdTRUE,
            NULL,
            disconnect_timer_callback
        );
    } else {
        xTimerChangePeriod(disconnect_timer, pdMS_TO_TICKS(interval_sec * 1000), 0);
    }
    if (disconnect_timer && !xTimerIsTimerActive(disconnect_timer)) {
        xTimerStart(disconnect_timer, 0);
        ESP_LOGI(TAG, "🔔 Started disconnect periodic reminder loop (%d s)", interval_sec);
    }
}

void audio_feedback_stop_disconnect_loop(void)
{
    if (disconnect_timer && xTimerIsTimerActive(disconnect_timer)) {
        xTimerStop(disconnect_timer, 0);
        ESP_LOGI(TAG, "✅ Stopped disconnect periodic reminder loop (Connection restored)");
    }
}

