/**
 * @file sound_player.h
 * @brief Zero-Latency Acoustic Feedback & I2S Speaker Driver for SubBox
 *
 * Provides instant sound cues (wake chime, success tone, error blip)
 * directly via local I2S amplifier (MAX98357A) on SubBox without TTS delay.
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <vector>
#include <memory>
#include "esp_err.h"

enum class SoundType {
    WAKE,       /**< "Hi ESP" wake word detected: crisp ascending double chime */
    SUCCESS,    /**< Command executed successfully: melodic bright confirmation triad */
    ERROR,      /**< Command unrecognized or failed: soft descending double blip */
    BOOTUP      /**< SubBox ready & connected: warm welcome chord */
};

class SoundPlayer {
public:
    static SoundPlayer& instance();

    /**
     * @brief Initialize I2S peripheral and amplifier shutdown GPIO
     * @return ESP_OK on success
     */
    esp_err_t init();

    /**
     * @brief Play synthesized acoustic feedback sound effect asynchronously
     * @param type Sound cue to play
     * @return true if queued/playing successfully
     */
    bool play(SoundType type);

    /**
     * @brief Play raw PCM audio data directly to speaker
     * @param pcm 16kHz, 16-bit signed mono samples
     * @param samples Sample count
     * @return true on success
     */
    bool playPcm(const int16_t* pcm, size_t samples);

    /**
     * @brief Check if sound is currently actively playing
     */
    bool isPlaying() const;

    /**
     * @brief Stop any active playback and mute amplifier
     */
    void stop();

private:
    SoundPlayer();
    ~SoundPlayer();

    SoundPlayer(const SoundPlayer&) = delete;
    SoundPlayer& operator=(const SoundPlayer&) = delete;

    void generateTone(std::vector<int16_t>& out, float freq_hz, float duration_s, float volume = 0.5f, float decay = 3.0f);
    void generateSilence(std::vector<int16_t>& out, float duration_s);

    void playRawInternal(const int16_t* pcm, size_t samples);
    static void playbackTask(void* pvParameters);

    void enableAmp(bool enable);

    bool m_initialized;
    volatile bool m_playing;
    void* m_i2s_handle;
    void* m_queue;
    void* m_task_handle;
    void* m_mutex;
};
