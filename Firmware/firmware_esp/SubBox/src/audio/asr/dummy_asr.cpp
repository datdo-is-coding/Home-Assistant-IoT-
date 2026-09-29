/**
 * @file dummy_asr.cpp
 * @brief Development & Simulation ASR Implementation
 */

#include "dummy_asr.h"
#include "esp_log.h"

static const char* TAG = "DUMMY_ASR";

DummyASR::DummyASR(const char* default_phrase)
    : m_configured_phrase(default_phrase ? default_phrase : "bật đèn phòng khách"),
      m_samples_fed(0),
      m_has_partial(false),
      m_has_final(false) {
}

bool DummyASR::init() {
    ESP_LOGI(TAG, "Dummy ASR Engine initialized (Active Default: \"%s\")", m_configured_phrase.c_str());
    reset();
    return true;
}

bool DummyASR::start() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_samples_fed = 0;
    m_has_partial = false;
    m_has_final = false;
    m_partial_result.clear();
    m_final_result.clear();
    ESP_LOGI(TAG, "ASR session started. Listening for speech frames...");
    return true;
}

bool DummyASR::feedAudio(const int16_t* pcm, size_t samples) {
    if (!pcm || samples == 0) return false;

    std::lock_guard<std::mutex> lock(m_mutex);
    m_samples_fed += samples;

    // Simulate streaming partial decoding after 8000 samples (~500ms)
    if (m_samples_fed >= 8000 && !m_has_partial) {
        m_has_partial = true;
        // Take first words of configured phrase as partial transcript
        size_t space_pos = m_configured_phrase.find(' ');
        if (space_pos != std::string::npos) {
            size_t second_space = m_configured_phrase.find(' ', space_pos + 1);
            m_partial_result = (second_space != std::string::npos) ?
                               m_configured_phrase.substr(0, second_space) :
                               m_configured_phrase.substr(0, space_pos);
        } else {
            m_partial_result = m_configured_phrase;
        }
        ESP_LOGD(TAG, "ASR Partial Result: \"%s\"", m_partial_result.c_str());
    }

    // Simulate final result after 16000 samples (~1000ms speech)
    if (m_samples_fed >= 16000 && !m_has_final) {
        m_has_final = true;
        m_final_result = m_configured_phrase;
        ESP_LOGI(TAG, "ASR Final Result Decoded: \"%s\"", m_final_result.c_str());
    }

    return true;
}

const char* DummyASR::getPartialResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_partial_result.c_str();
}

const char* DummyASR::getFinalResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_final_result.c_str();
}

void DummyASR::reset() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_samples_fed = 0;
    m_has_partial = false;
    m_has_final = false;
    m_partial_result.clear();
    m_final_result.clear();
}

void DummyASR::setNextRecognitionResult(const char* phrase) {
    if (!phrase) return;
    std::lock_guard<std::mutex> lock(m_mutex);
    m_configured_phrase = phrase;
    ESP_LOGI(TAG, "Updated upcoming ASR phrase target: \"%s\"", m_configured_phrase.c_str());
}

void DummyASR::injectInstantResult(const char* phrase) {
    if (!phrase) return;
    std::lock_guard<std::mutex> lock(m_mutex);
    m_configured_phrase = phrase;
    m_final_result = phrase;
    m_has_final = true;
    m_has_partial = true;
    m_partial_result = phrase;
    ESP_LOGI(TAG, "Instant ASR Injected: \"%s\"", m_final_result.c_str());
}
