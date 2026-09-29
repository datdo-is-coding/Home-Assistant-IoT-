/**
 * @file tts_manager.h
 * @brief SubBox TTS Coordinator & Local Audio Response Generator
 */

#pragma once

#include <memory>
#include <string>
#include "tts_engine.h"
#include "audio/audio_output/audio_output_router.h"

class TTSManager : public TTSEngine {
public:
    explicit TTSManager(std::shared_ptr<AudioOutputRouter> router);
    virtual ~TTSManager() = default;

    bool init() override;
    bool synthesize(const char* text, std::vector<int16_t>& pcm_out) override;

    /**
     * @brief Synthesize and immediately dispatch response audio to target ActionBox
     * @param target_node_id ActionBox node ID (or nullptr to use last input node)
     * @param text Vietnamese text to speak
     * @return true on success
     */
    bool speakResponse(const char* target_node_id, const std::string& text);

    /**
     * @brief Forward synthesized audio received from Raspberry Pi 4 to ActionBox speaker
     * @param target_node_id ActionBox node ID
     * @param pcm_bytes Raw PCM audio payload
     * @param len Length in bytes
     */
    bool forwardPi4Audio(const char* target_node_id, const uint8_t* pcm_bytes, size_t len);

    /**
     * @brief Play pleasant confirmation chime tone ("Ding!") on ActionBox speaker
     * @param target_node_id ActionBox node ID
     */
    bool playConfirmationChime(const char* target_node_id);

private:
    void generateChime(std::vector<int16_t>& pcm_out, float freq_hz, float duration_s);

    std::shared_ptr<AudioOutputRouter> m_router;
};
