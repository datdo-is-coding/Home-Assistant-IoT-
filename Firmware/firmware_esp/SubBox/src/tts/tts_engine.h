/**
 * @file tts_engine.h
 * @brief Replaceable Text-to-Speech (TTS) Engine Interface
 */

#pragma once

#include <vector>
#include <stdint.h>

class TTSEngine {
public:
    virtual ~TTSEngine() = default;

    /**
     * @brief Initialize TTS engine resources
     * @return true on success
     */
    virtual bool init() = 0;

    /**
     * @brief Synthesize speech PCM samples from text string
     * @param text Vietnamese UTF-8 text string to speak
     * @param pcm_out Output vector receiving 16kHz 16-bit mono PCM samples
     * @return true if synthesized successfully
     */
    virtual bool synthesize(const char* text, std::vector<int16_t>& pcm_out) = 0;
};
