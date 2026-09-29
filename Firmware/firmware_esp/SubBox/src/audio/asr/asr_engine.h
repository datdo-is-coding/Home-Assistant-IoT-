/**
 * @file asr_engine.h
 * @brief Replaceable Speech Recognition (ASR) Engine Interface
 */

#pragma once

#include <stdint.h>
#include <stddef.h>

class ASREngine {
public:
    virtual ~ASREngine() = default;

    /**
     * @brief Initialize ASR engine weights/model in PSRAM
     * @return true on success
     */
    virtual bool init() = 0;

    /**
     * @brief Start an active recognition session
     * @return true on success
     */
    virtual bool start() = 0;

    /**
     * @brief Notify engine that speech audio input has ended
     */
    virtual void stop() {}

    /**
     * @brief Feed 16-bit PCM audio samples to the acoustic model
     * @param pcm Array of 16-bit mono 16kHz audio samples
     * @param samples Sample count
     * @return true if samples were queued/consumed successfully
     */
    virtual bool feedAudio(const int16_t* pcm, size_t samples) = 0;

    /**
     * @brief Check if a partial/streaming transcript is available
     */
    virtual bool hasPartialResult() const = 0;

    /**
     * @brief Check if final end-of-speech transcript is available
     */
    virtual bool hasFinalResult() const = 0;

    /**
     * @brief Retrieve streaming partial recognition text
     */
    virtual const char* getPartialResult() const = 0;

    struct AsrResult {
        const char* text;
        float confidence;
        const char* source; // "gateway" or "offline_kws"
    };

    /**
     * @brief Retrieve final speech-to-text decoded string
     */
    virtual const char* getFinalResult() const = 0;

    /**
     * @brief Retrieve detailed final result
     */
    virtual AsrResult getFinalResultDetailed() const {
        return { getFinalResult(), 1.0f, "gateway" };
    }

    /**
     * @brief Reset internal decoder state and clear buffers
     */
    virtual void reset() = 0;
};
