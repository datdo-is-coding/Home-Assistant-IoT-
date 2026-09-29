/**
 * @file vad_interface.h
 * @brief Replaceable Voice Activity Detection (VAD) Interface
 */

#pragma once

#include <stdint.h>
#include <stddef.h>

class VADInterface {
public:
    virtual ~VADInterface() = default;

    /**
     * @brief Process an audio frame of 16-bit PCM samples
     * @param pcm Pointer to 16-bit mono PCM samples
     * @param count Number of samples in frame (e.g. 160 samples = 10ms @ 16kHz)
     * @return true if speech is actively detected in this frame
     */
    virtual bool process(const int16_t* pcm, size_t count) = 0;

    /**
     * @brief Check if transition to speech onset has just occurred
     */
    virtual bool speechStarted() const = 0;

    /**
     * @brief Check if transition to speech end (silence timeout) has occurred
     */
    virtual bool speechEnded() const = 0;

    /**
     * @brief Check if currently in an active speech state
     */
    virtual bool isSpeaking() const = 0;

    /**
     * @brief Get current calculated frame energy / confidence
     */
    virtual int64_t getEnergy() const = 0;

    /**
     * @brief Reset internal state and silence timers
     */
    virtual void reset() = 0;
};
