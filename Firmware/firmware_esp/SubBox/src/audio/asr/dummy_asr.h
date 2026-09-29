/**
 * @file dummy_asr.h
 * @brief Development & Simulation ASR Implementation for Vietnamese Smart-Home
 */

#pragma once

#include "asr_engine.h"
#include <string>
#include <mutex>

class DummyASR : public ASREngine {
public:
    explicit DummyASR(const char* default_phrase = "bật đèn phòng ngủ");
    virtual ~DummyASR() = default;

    bool init() override;
    bool start() override;
    bool feedAudio(const int16_t* pcm, size_t samples) override;
    bool hasPartialResult() const override { return m_has_partial; }
    bool hasFinalResult() const override { return m_has_final; }
    const char* getPartialResult() const override;
    const char* getFinalResult() const override;
    void reset() override;

    /**
     * @brief Set custom phrase to decode upon receiving next audio stream
     */
    void setNextRecognitionResult(const char* phrase);

    /**
     * @brief Instantly inject simulated recognition result (e.g. from SAY CLI)
     */
    void injectInstantResult(const char* phrase);

private:
    std::string m_configured_phrase;
    std::string m_partial_result;
    std::string m_final_result;
    size_t m_samples_fed;
    bool m_has_partial;
    bool m_has_final;
    mutable std::mutex m_mutex;
};
