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

    bool speakResponse(const char* target_node_id, const std::string& text);

    bool forwardPi4Audio(const char* target_node_id, const uint8_t* pcm_bytes, size_t len);

    bool playConfirmationChime(const char* target_node_id);

private:
    void generateChime(std::vector<int16_t>& pcm_out, float freq_hz, float duration_s);

    std::shared_ptr<AudioOutputRouter> m_router;
};
