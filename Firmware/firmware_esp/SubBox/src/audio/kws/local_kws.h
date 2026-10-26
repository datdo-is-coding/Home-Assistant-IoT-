#pragma once

#include "asr_engine.h"
#include "kws_command.h"
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>

class MFCCExtractor;

// Runs the existing Vietnamese KWS model locally on SubBox PCM.
// Inference happens in the audio-manager task, never in the ESP-NOW callback.
class LocalKws : public ASREngine {
public:
    LocalKws();
    ~LocalKws() override;

    bool init() override;
    bool start() override;
    void setSourceNodeId(const char* node_id) override;
    void stop() override;
    void cancel() override;
    bool feedAudio(const int16_t* pcm, size_t samples) override;

    bool hasPartialResult() const override;
    bool hasFinalResult() const override;
    const char* getPartialResult() const override;
    const char* getFinalResult() const override;
    AsrResult getFinalResultDetailed() const override;
    void reset() override;

    bool isActive() const;

private:
    bool inferWindow(uint64_t now_ms);
    void appendSamples(const int16_t* pcm, size_t samples);
    std::string commandText() const;

    float* m_ring = nullptr;
    float* m_window = nullptr;
    float* m_mfcc = nullptr;
    float* m_pool_scratch = nullptr;
    float* m_dw_scratch = nullptr;
    std::unique_ptr<MFCCExtractor> m_extractor;

    size_t m_head = 0;
    size_t m_samples_since_step = 0;
    int m_last_class = -1;
    uint64_t m_last_class_ms = 0;

    KwsCommand m_command;
    std::string m_source_node_id;
    std::string m_partial;
    std::string m_final;
    bool m_active = false;
    bool m_has_final = false;
    bool m_inference_failed = false;

    mutable std::mutex m_mutex;
};
