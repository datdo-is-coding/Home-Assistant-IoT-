#pragma once

#include "asr_engine.h"

/**
 * @brief FallbackASR wraps an online ASR (WsASR) and a local KWS model.
 * It switches between WsASR (Gateway online) and local KWS model
 * (after 3s WebSocket loss). Only switches between utterances.
 */
class FallbackASR : public ASREngine {
public:
    FallbackASR(ASREngine* primary, ASREngine* offline);
    virtual ~FallbackASR() = default;

    bool init() override;
    bool start() override;
    void stop() override;
    bool feedAudio(const int16_t* pcm, size_t samples) override;
    bool hasPartialResult() const override;
    bool hasFinalResult() const override;
    const char* getPartialResult() const override;
    const char* getFinalResult() const override;
    AsrResult getFinalResultDetailed() const override;
    void reset() override;

private:
    ASREngine* primary_;
    ASREngine* offline_;
    bool use_offline_;
    uint32_t last_ws_success_time_;
    
    // 5 fixed commands + unknown + noise
    // "Aetheria bật đèn"
    // "Aetheria tắt đèn"
    // "Aetheria bật quạt"
    // "Aetheria tắt quạt"
    // "Aetheria tắt hết"
    // "unknown"
    // "noise"
};
