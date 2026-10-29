#include "local_kws.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

#include "kws_mfcc.h"
#include "kws_model_quantized.h"

#if defined(ESP_PLATFORM)
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#endif

#if defined(ESP_PLATFORM)
static const char* TAG = "LOCAL_KWS";
#endif

namespace {
// Conservative until measured on the target boards. KwsCommand repeats the
// same floor so a low-confidence word can never reach sentence assembly.
constexpr float EXECUTION_CONFIDENCE = 0.50f;
constexpr size_t VAD_FRAME_SAMPLES = SAMPLE_RATE * 20 / 1000;
constexpr size_t PREROLL_SAMPLES = SAMPLE_RATE * 100 / 1000;
constexpr size_t MIN_SPEECH_SAMPLES = SAMPLE_RATE * 80 / 1000;
constexpr size_t END_SILENCE_SAMPLES = SAMPLE_RATE * 60 / 1000;
constexpr size_t MAX_WORD_SAMPLES = TOTAL_SAMPLES;
constexpr size_t SEGMENT_CAPACITY = MAX_WORD_SAMPLES + 2 * PREROLL_SAMPLES;

void* kwsAlloc(size_t size) {
#if defined(ESP_PLATFORM)
    void* memory = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!memory) memory = malloc(size);
    return memory;
#else
    return malloc(size);
#endif
}
}

LocalKws::LocalKws() = default;

LocalKws::~LocalKws() {
    reset();
    free(m_segment);
    free(m_frame);
    free(m_window);
    free(m_mfcc);
    free(m_pool_scratch);
    free(m_dw_scratch);
}

bool LocalKws::init() {
    if (!m_segment) m_segment = static_cast<float*>(kwsAlloc(sizeof(float) * SEGMENT_CAPACITY));
    if (!m_frame) m_frame = static_cast<float*>(kwsAlloc(sizeof(float) * VAD_FRAME_SAMPLES));
    if (!m_window) m_window = static_cast<float*>(kwsAlloc(sizeof(float) * TOTAL_SAMPLES));
    if (!m_mfcc) m_mfcc = static_cast<float*>(kwsAlloc(sizeof(float) * NUM_FRAMES * NUM_MFCC_COEFFS));
    if (!m_pool_scratch) m_pool_scratch = static_cast<float*>(kwsAlloc(sizeof(float) * 16 * 49 * 6));
    if (!m_dw_scratch) m_dw_scratch = static_cast<float*>(kwsAlloc(sizeof(float) * 32 * 49 * 6));
    if (!m_segment || !m_frame || !m_window || !m_mfcc || !m_pool_scratch || !m_dw_scratch) {
#if defined(ESP_PLATFORM)
        ESP_LOGE(TAG, "Local KWS buffers unavailable");
#endif
        return false;
    }
    if (!m_extractor) m_extractor = std::make_unique<MFCCExtractor>();
    if (!m_extractor->init()) {
        m_extractor.reset();
#if defined(ESP_PLATFORM)
        ESP_LOGE(TAG, "MFCC initialization failed");
#endif
        return false;
    }
    reset();
#if defined(ESP_PLATFORM)
    ESP_LOGI(TAG, "Local KWS ready (word VAD 20 ms, preroll 100 ms/end 60 ms, centered 1 s)");
#endif
    return true;
}

bool LocalKws::start() {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_extractor || !m_segment || !m_frame || !m_window || !m_mfcc ||
        !m_pool_scratch || !m_dw_scratch) return false;
    memset(m_segment, 0, sizeof(float) * SEGMENT_CAPACITY);
    memset(m_window, 0, sizeof(float) * TOTAL_SAMPLES);
    m_segment_samples = PREROLL_SAMPLES;
    resetWord();
    m_frame_samples = 0;
    m_noise_rms = INITIAL_NOISE_RMS;
    m_command.reset();
    m_partial.clear();
    m_final.clear();

    m_active = true;
    m_has_final = false;
    m_inference_failed = false;
    return true;
}

void LocalKws::setSourceNodeId(const char* node_id) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_source_node_id = node_id ? node_id : "";
}

void LocalKws::resetWord() {
    // Carry the preceding 100 ms into the next onset, without copying onset twice.
    if (m_segment && m_segment_samples >= PREROLL_SAMPLES) {
        memmove(m_segment, m_segment + m_segment_samples - PREROLL_SAMPLES,
            sizeof(float) * PREROLL_SAMPLES);
    }
    m_segment_samples = PREROLL_SAMPLES;
    m_speech_samples = m_silence_samples = 0;
    m_word_active = false;
}

bool LocalKws::processVadFrame(size_t samples) {
    float energy = 0.0f;
    for (size_t i = 0; i < samples; ++i) energy += m_frame[i] * m_frame[i];
    const float rms = std::sqrt(energy / samples);
    const float speech_threshold = m_noise_rms * 2.2f + 0.006f;
    const float silence_threshold = m_noise_rms * 1.3f + 0.002f;

    if (!m_word_active) {
        if (rms < speech_threshold) {
            m_noise_rms = 0.98f * m_noise_rms + 0.02f * rms;
            memmove(m_segment, m_segment + samples, sizeof(float) * (PREROLL_SAMPLES - samples));
            memcpy(m_segment + PREROLL_SAMPLES - samples, m_frame, sizeof(float) * samples);
            return true;
        }
        m_word_active = true;
#if defined(ESP_PLATFORM)
        ESP_LOGI(TAG, "KWS_VAD_START rms=%.4f noise=%.4f speech_threshold=%.4f silence_threshold=%.4f",
            static_cast<double>(rms), static_cast<double>(m_noise_rms),
            static_cast<double>(speech_threshold), static_cast<double>(silence_threshold));
#endif
    }

    if (m_segment_samples + samples > SEGMENT_CAPACITY) return false;
    memcpy(m_segment + m_segment_samples, m_frame, sizeof(float) * samples);
    m_segment_samples += samples;
    if (rms >= silence_threshold) {
        m_speech_samples += samples;
        m_silence_samples = 0;
    } else {
        m_silence_samples += samples;
    }
    // Bound a model window, not the utterance: continuous speech must keep listening.
    if (m_segment_samples - PREROLL_SAMPLES - m_silence_samples >= MAX_WORD_SAMPLES) {
#if defined(ESP_PLATFORM)
        ESP_LOGI(TAG, "KWS_VAD_LIMIT rms=%.4f silence_threshold=%.4f; infer window, continue stream",
            static_cast<double>(rms), static_cast<double>(silence_threshold));
#endif
        return finishWord();
    }
    if (m_silence_samples >= END_SILENCE_SAMPLES) return finishWord();
    return true;
}

bool LocalKws::finishWord() {
    if (m_speech_samples >= MIN_SPEECH_SAMPLES) {
        // STREAM_END may precede the silence tail: balance the preroll with zeros.
        const size_t desired_tail = PREROLL_SAMPLES - std::min(PREROLL_SAMPLES, m_silence_samples);
        const size_t max_tail = (SEGMENT_CAPACITY > m_segment_samples) ? (SEGMENT_CAPACITY - m_segment_samples) : 0;
        const size_t missing_tail = std::min(desired_tail, max_tail);
        if (missing_tail > 0) {
            memset(m_segment + m_segment_samples, 0, sizeof(float) * missing_tail);
            m_segment_samples += missing_tail;
        }
        if (!inferWord()) return false;
    }
    resetWord();
    return true;
}

bool LocalKws::inferWord() {
#if defined(ESP_PLATFORM)
    const int64_t started_us = esp_timer_get_time();
#endif
    memset(m_window, 0, sizeof(float) * TOTAL_SAMPLES);
    if (m_segment_samples <= 2 * PREROLL_SAMPLES) {
        resetWord();
        return true;
    }
    const size_t word_samples = m_segment_samples - 2 * PREROLL_SAMPLES;
    size_t trim = 0;
    size_t retained = 0;
    size_t front = 0;

    if (word_samples >= TOTAL_SAMPLES) {
        trim = PREROLL_SAMPLES + (word_samples - TOTAL_SAMPLES) / 2;
        retained = TOTAL_SAMPLES;
        front = 0;
    } else {
        const size_t max_context = (TOTAL_SAMPLES - word_samples) / 2;
        const size_t context = std::min(PREROLL_SAMPLES, max_context);
        trim = PREROLL_SAMPLES - context;
        retained = m_segment_samples - trim * 2;
        if (retained > TOTAL_SAMPLES) retained = TOTAL_SAMPLES;
        front = (TOTAL_SAMPLES - retained) / 2;
    }
    if (trim + retained > m_segment_samples) retained = m_segment_samples - trim;
    if (front + retained > TOTAL_SAMPLES) retained = TOTAL_SAMPLES - front;
    memcpy(m_window + front, m_segment + trim, sizeof(float) * retained);
    m_extractor->extract(m_window, m_mfcc);

    float probabilities[NUM_CLASSES] = {};
    kws_run_inference_quantized(m_mfcc, probabilities, m_pool_scratch, m_dw_scratch);
#if defined(ESP_PLATFORM)
    ESP_LOGI(TAG, "KWS_WORD samples=%u speech_samples=%u pad_front=%u elapsed_us=%lld free_internal=%u free_psram=%u",
        static_cast<unsigned>(m_segment_samples), static_cast<unsigned>(m_speech_samples),
        static_cast<unsigned>(front),
        static_cast<long long>(esp_timer_get_time() - started_us),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
#endif

    int top_class = 0;
    float top_probability = probabilities[0];
    for (int i = 0; i < NUM_CLASSES; ++i) {
        if (!std::isfinite(probabilities[i]) || probabilities[i] < 0.0f || probabilities[i] > 1.0f) {
#if defined(ESP_PLATFORM)
            ESP_LOGE(TAG, "Invalid model probability at class %d", i);
#endif
            return false;
        }
        if (probabilities[i] > top_probability) {
            top_probability = probabilities[i];
            top_class = i;
        }
    }
    const bool usable = top_class != CLASS_NOISE && top_class != CLASS_UNKNOWN &&
        top_probability >= EXECUTION_CONFIDENCE;
#if defined(ESP_PLATFORM)
    ESP_LOGI(TAG, "KWS_RESULT class=%s confidence=%.3f accepted=%d",
        KWS_LABELS[top_class], static_cast<double>(top_probability), usable);
#endif
    if (usable) {
        m_command.add(top_class, top_probability);
    }
    m_partial = m_command.text();
    return true;
}

bool LocalKws::feedAudio(const int16_t* pcm, size_t samples) {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_active || m_inference_failed) return false;
    if (samples == 0) return true;
    if (!pcm) { m_inference_failed = true; return false; }

    size_t offset = 0;
    while (offset < samples) {
        const size_t capacity = VAD_FRAME_SAMPLES - m_frame_samples;
        const size_t take = std::min(capacity, samples - offset);
        for (size_t i = 0; i < take; ++i) {
            m_frame[m_frame_samples + i] = static_cast<float>(pcm[offset + i]) / 32768.0f;
        }
        offset += take;
        m_frame_samples += take;
        if (m_frame_samples == VAD_FRAME_SAMPLES) {
            m_frame_samples = 0;
            if (!processVadFrame(VAD_FRAME_SAMPLES)) {
                m_inference_failed = true;
#if defined(ESP_PLATFORM)
                ESP_LOGW(TAG, "KWS buffer/inference error; discard stream");
#endif
                return false;
            }
        }
    }
    return true;
}

void LocalKws::stop() {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_active) return;
    if (!m_inference_failed && m_frame_samples > 0) {
        if (!processVadFrame(m_frame_samples)) m_inference_failed = true;
    }
    if (!m_inference_failed && m_word_active && !finishWord()) m_inference_failed = true;

    m_final = m_inference_failed ? "__KWS_AUDIO_ERROR__" : commandText();
    m_has_final = true;
    m_active = false;
    m_frame_samples = 0;
}

void LocalKws::cancel() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_active = false;
    m_final = "__KWS_AUDIO_ERROR__";
    m_has_final = true;
    m_partial.clear();
    m_frame_samples = 0;
}

bool LocalKws::hasPartialResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_active && !m_inference_failed && !m_partial.empty() && m_partial != "__KWS_EMPTY__" &&
        m_partial != "__KWS_INVALID__";
}

bool LocalKws::hasFinalResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_has_final;
}

const char* LocalKws::getPartialResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_partial.c_str();
}

const char* LocalKws::getFinalResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_final.c_str();
}

ASREngine::AsrResult LocalKws::getFinalResultDetailed() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return {m_final.c_str(), 1.0f, "local_kws"};
}

void LocalKws::reset() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_active = false;
    m_has_final = false;
    m_inference_failed = false;
    m_frame_samples = 0;
    m_noise_rms = INITIAL_NOISE_RMS;
    m_command.reset();
    m_partial.clear();
    m_final.clear();
    if (m_segment) memset(m_segment, 0, sizeof(float) * SEGMENT_CAPACITY);
    m_segment_samples = PREROLL_SAMPLES;
    resetWord();
    if (m_window) memset(m_window, 0, sizeof(float) * TOTAL_SAMPLES);
}

bool LocalKws::isActive() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_active;
}

std::string LocalKws::commandText() const {
    return m_command.text();
}
