#pragma once

#include <stdint.h>
#include <stddef.h>

class ASREngine {
public:
    virtual ~ASREngine() = default;

    virtual bool init() = 0;

    virtual bool start() = 0;

    virtual void setSourceNodeId(const char* node_id) {}

    virtual void stop() {}

    virtual void cancel() { reset(); }

    virtual bool feedAudio(const int16_t* pcm, size_t samples) = 0;

    virtual bool hasPartialResult() const = 0;

    virtual bool hasFinalResult() const = 0;

    virtual const char* getPartialResult() const = 0;

    struct AsrResult {
        const char* text;
        float confidence;
        const char* source;
    };

    virtual const char* getFinalResult() const = 0;

    virtual AsrResult getFinalResultDetailed() const {
        return { getFinalResult(), 1.0f, "gateway" };
    }

    virtual void reset() = 0;
};
