#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <vector>
#include <memory>
#include "esp_err.h"

enum class SoundType {
    WAKE,
    SUCCESS,
    ERROR,
    BOOTUP
};

class SoundPlayer {
public:
    static SoundPlayer& instance();

    esp_err_t init();

    bool play(SoundType type);

    bool playPcm(const int16_t* pcm, size_t samples);

    bool startPcmStream();

    bool streamPcmChunk(const int16_t* pcm, size_t samples);

    void finishPcmStream();

    bool isPlaying() const;

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
    volatile bool m_streaming_pcm;
    int64_t m_last_chunk_time_us;
    void* m_i2s_handle;
    void* m_queue;
    void* m_task_handle;
    void* m_mutex;
};
