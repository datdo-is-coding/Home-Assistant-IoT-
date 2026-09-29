#include "fallback_asr.h"
#include "esp_timer.h"

FallbackASR::FallbackASR(ASREngine* primary, ASREngine* offline)
    : primary_(primary), offline_(offline), use_offline_(false), last_ws_success_time_(0) {
}

bool FallbackASR::init() {
    bool ok1 = primary_ ? primary_->init() : false;
    bool ok2 = offline_ ? offline_->init() : false;
    return ok1 || ok2;
}

bool FallbackASR::start() {
    // Check if WebSocket has been lost for > 3s
    uint32_t now = esp_timer_get_time() / 1000;
    if (now - last_ws_success_time_ > 3000) {
        use_offline_ = true;
    } else {
        use_offline_ = false;
    }

    if (use_offline_ && offline_) return offline_->start();
    if (primary_) return primary_->start();
    return false;
}

void FallbackASR::stop() {
    if (use_offline_ && offline_) offline_->stop();
    else if (primary_) primary_->stop();
}

bool FallbackASR::feedAudio(const int16_t* pcm, size_t samples) {
    if (use_offline_ && offline_) return offline_->feedAudio(pcm, samples);
    if (primary_) return primary_->feedAudio(pcm, samples);
    return false;
}

bool FallbackASR::hasPartialResult() const {
    if (use_offline_ && offline_) return offline_->hasPartialResult();
    if (primary_) return primary_->hasPartialResult();
    return false;
}

bool FallbackASR::hasFinalResult() const {
    if (use_offline_ && offline_) return offline_->hasFinalResult();
    if (primary_) return primary_->hasFinalResult();
    return false;
}

const char* FallbackASR::getPartialResult() const {
    if (use_offline_ && offline_) return offline_->getPartialResult();
    if (primary_) return primary_->getPartialResult();
    return "";
}

const char* FallbackASR::getFinalResult() const {
    if (use_offline_ && offline_) return offline_->getFinalResult();
    if (primary_) return primary_->getFinalResult();
    return "";
}

ASREngine::AsrResult FallbackASR::getFinalResultDetailed() const {
    if (use_offline_ && offline_) {
        return { offline_->getFinalResult(), 0.9f, "offline_kws" };
    }
    if (primary_) {
        return { primary_->getFinalResult(), 1.0f, "gateway" };
    }
    return { "", 0.0f, "unknown" };
}

void FallbackASR::reset() {
    if (primary_) primary_->reset();
    if (offline_) offline_->reset();
}
