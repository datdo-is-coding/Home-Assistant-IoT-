/**
 * @file tts_manager.cpp
 * @brief SubBox TTS Coordinator & Local Audio Response Generator Implementation
 */

#include "tts_manager.h"
#include <cmath>
#include "esp_log.h"

static const char* TAG = "TTS_MGR";

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

TTSManager::TTSManager(std::shared_ptr<AudioOutputRouter> router)
    : m_router(router) {
}

bool TTSManager::init() {
    ESP_LOGI(TAG, "TTS Manager initialized (Ready for Pi4 streaming & local chime feedback).");
    return true;
}

void TTSManager::generateChime(std::vector<int16_t>& pcm_out, float freq_hz, float duration_s) {
    size_t samples = (size_t)(duration_s * SUBBOX_AUDIO_SAMPLE_RATE);
    pcm_out.resize(samples);

    float angular_freq = 2.0f * (float)M_PI * freq_hz / (float)SUBBOX_AUDIO_SAMPLE_RATE;
    float decay_rate = 4.0f / (float)samples;

    for (size_t i = 0; i < samples; ++i) {
        float env = expf(-decay_rate * (float)i); // Smooth exponential decay
        float wave = sinf(angular_freq * (float)i);
        pcm_out[i] = (int16_t)(wave * env * 12000.0f); // ~35% volume
    }
}

bool TTSManager::synthesize(const char* text, std::vector<int16_t>& pcm_out) {
    if (!text || strlen(text) == 0) return false;

    ESP_LOGI(TAG, "Synthesizing audio prompt for: \"%s\"", text);

    // Initial version generates dual-tone melodic chime acknowledgment
    std::vector<int16_t> tone1, tone2;
    generateChime(tone1, 880.0f, 0.15f); // High chime (A5)
    generateChime(tone2, 587.3f, 0.35f); // Low resolution chime (D5)

    pcm_out.clear();
    pcm_out.reserve(tone1.size() + tone2.size());
    pcm_out.insert(pcm_out.end(), tone1.begin(), tone1.end());
    pcm_out.insert(pcm_out.end(), tone2.begin(), tone2.end());

    return true;
}

bool TTSManager::speakResponse(const char* target_node_id, const std::string& text) {
    std::vector<int16_t> pcm;
    if (!synthesize(text.c_str(), pcm) || pcm.empty()) {
        return false;
    }

    if (m_router) {
        return m_router->sendAudioResponse(
            target_node_id,
            reinterpret_cast<const uint8_t*>(pcm.data()),
            pcm.size() * sizeof(int16_t)
        );
    }
    return false;
}

bool TTSManager::playConfirmationChime(const char* target_node_id) {
    return speakResponse(target_node_id, "ACK_CHIME");
}

bool TTSManager::forwardPi4Audio(const char* target_node_id, const uint8_t* pcm_bytes, size_t len) {
    if (!m_router || !pcm_bytes || len == 0) return false;

    ESP_LOGI(TAG, "Streaming external Pi4 TTS audio to ActionBox: %s (%u bytes)",
             target_node_id ? target_node_id : "[LAST_INPUT]", (unsigned)len);

    return m_router->sendAudioResponse(target_node_id, pcm_bytes, len);
}
