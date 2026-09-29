/**
 * @file energy_vad.cpp
 * @brief Energy-Based Adaptive Voice Activity Detector Implementation
 */

#include "energy_vad.h"
#include <cmath>
#include <algorithm>
#include "esp_log.h"

static const char* TAG = "ENERGY_VAD";

EnergyVAD::EnergyVAD(int64_t initial_threshold, uint32_t silence_timeout_ms, uint32_t onset_frames, uint32_t max_duration_ms)
    : m_threshold(initial_threshold),
      m_silence_timeout_ms(silence_timeout_ms),
      m_onset_frames(onset_frames),
      m_max_duration_ms(max_duration_ms),
      m_latest_energy(0),
      m_noise_floor(300000.0f),
      m_is_speaking(false),
      m_speech_started(false),
      m_speech_ended(false),
      m_consecutive_speech_frames(0),
      m_consecutive_silence_ms(0),
      m_total_speech_duration_ms(0) {
}

void EnergyVAD::reset() {
    m_is_speaking = false;
    m_speech_started = false;
    m_speech_ended = false;
    m_consecutive_speech_frames = 0;
    m_consecutive_silence_ms = 0;
    m_total_speech_duration_ms = 0;
    m_latest_energy = 0;
}

bool EnergyVAD::process(const int16_t* pcm, size_t count) {
    m_speech_started = false;
    m_speech_ended = false;

    if (!pcm || count == 0) return m_is_speaking;

    // Calculate Mean Square Energy
    int64_t sum_sq = 0;
    for (size_t i = 0; i < count; ++i) {
        int32_t val = pcm[i];
        sum_sq += (int64_t)val * val;
    }
    m_latest_energy = sum_sq / (int64_t)count;

    // Duration of this audio chunk in milliseconds (assuming 16kHz)
    uint32_t chunk_ms = (uint32_t)(count * 1000 / SUBBOX_AUDIO_SAMPLE_RATE);
    if (chunk_ms == 0) chunk_ms = 10;

    // Dynamic threshold based on adaptive noise floor
    int64_t active_threshold = std::max(m_threshold, (int64_t)(m_noise_floor * 3.5f));

    if (!m_is_speaking) {
        // Track background noise floor when not speaking (exponential moving average)
        if (m_latest_energy < active_threshold) {
            m_noise_floor = m_noise_floor * 0.95f + (float)m_latest_energy * 0.05f;
        }

        // Check for speech onset
        if (m_latest_energy >= active_threshold) {
            m_consecutive_speech_frames++;
            if (m_consecutive_speech_frames >= m_onset_frames) {
                m_is_speaking = true;
                m_speech_started = true;
                m_consecutive_silence_ms = 0;
                m_total_speech_duration_ms = chunk_ms * m_onset_frames;
                ESP_LOGI(TAG, "Speech Onset detected (Energy=%lld, NoiseFloor=%.0f)",
                         (long long)m_latest_energy, m_noise_floor);
            }
        } else {
            if (m_consecutive_speech_frames > 0) {
                m_consecutive_speech_frames--;
            }
        }
    } else {
        // Actively speaking
        m_total_speech_duration_ms += chunk_ms;

        if (m_latest_energy < (active_threshold * 4 / 10)) {
            m_consecutive_silence_ms += chunk_ms;
        } else {
            m_consecutive_silence_ms = 0;
        }

        bool silence_timeout = (m_consecutive_silence_ms >= m_silence_timeout_ms);
        bool max_duration_reached = (m_total_speech_duration_ms >= m_max_duration_ms);

        if (silence_timeout || max_duration_reached) {
            m_is_speaking = false;
            m_speech_ended = true;
            m_consecutive_speech_frames = 0;
            ESP_LOGI(TAG, "Speech End detected: %s (Duration=%ums, Silence=%ums)",
                     silence_timeout ? "1.5s Silence" : "Max 10s Window",
                     m_total_speech_duration_ms, m_consecutive_silence_ms);
        }
    }

    return m_is_speaking;
}
