/**
 * @file energy_vad.h
 * @brief Energy-Based Adaptive Voice Activity Detector
 */

#pragma once

#include "vad_interface.h"
#include "config/subbox_config.h"

class EnergyVAD : public VADInterface {
public:
    explicit EnergyVAD(
        int64_t initial_threshold = SUBBOX_VAD_INITIAL_ENERGY_THRESH,
        uint32_t silence_timeout_ms = SUBBOX_VAD_SILENCE_TIMEOUT_MS,
        uint32_t onset_frames = SUBBOX_VAD_SPEECH_ONSET_FRAMES,
        uint32_t max_duration_ms = SUBBOX_VAD_MAX_SPEECH_DURATION_MS
    );
    virtual ~EnergyVAD() = default;

    bool process(const int16_t* pcm, size_t count) override;
    bool speechStarted() const override { return m_speech_started; }
    bool speechEnded() const override { return m_speech_ended; }
    bool isSpeaking() const override { return m_is_speaking; }
    int64_t getEnergy() const override { return m_latest_energy; }
    void reset() override;

    void setThreshold(int64_t threshold) { m_threshold = threshold; }
    void setSilenceTimeout(uint32_t timeout_ms) { m_silence_timeout_ms = timeout_ms; }
    float getNoiseFloor() const { return m_noise_floor; }

private:
    int64_t m_threshold;
    uint32_t m_silence_timeout_ms;
    uint32_t m_onset_frames;
    uint32_t m_max_duration_ms;

    int64_t m_latest_energy;
    float m_noise_floor;
    bool m_is_speaking;
    bool m_speech_started;
    bool m_speech_ended;

    uint32_t m_consecutive_speech_frames;
    uint32_t m_consecutive_silence_ms;
    uint32_t m_total_speech_duration_ms;
};
