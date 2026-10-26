#include "local_kws.h"

#include <algorithm>
#include <chrono>
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
// same floor so a low-confidence window can never reach sentence assembly.
constexpr float EXECUTION_CONFIDENCE = 0.75f;
constexpr uint64_t SAME_CLASS_DEDUP_MS = 700;
constexpr uint64_t INITIAL_LAST_MS = 0;

uint64_t nowMs() {
#if defined(ESP_PLATFORM)
    return static_cast<uint64_t>(esp_timer_get_time() / 1000);
#else
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
#endif
}

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
    free(m_ring);
    free(m_window);
    free(m_mfcc);
    free(m_pool_scratch);
    free(m_dw_scratch);
}

bool LocalKws::init() {
    if (!m_ring) m_ring = static_cast<float*>(kwsAlloc(sizeof(float) * TOTAL_SAMPLES));
    if (!m_window) m_window = static_cast<float*>(kwsAlloc(sizeof(float) * TOTAL_SAMPLES));
    if (!m_mfcc) m_mfcc = static_cast<float*>(kwsAlloc(sizeof(float) * NUM_FRAMES * NUM_MFCC_COEFFS));
    if (!m_pool_scratch) m_pool_scratch = static_cast<float*>(kwsAlloc(sizeof(float) * 16 * 49 * 6));
    if (!m_dw_scratch) m_dw_scratch = static_cast<float*>(kwsAlloc(sizeof(float) * 32 * 49 * 6));
    if (!m_ring || !m_window || !m_mfcc || !m_pool_scratch || !m_dw_scratch) {
#if defined(ESP_PLATFORM)
        ESP_LOGE(TAG, "Local KWS buffers unavailable");
#endif
        return false;
    }
    if (!m_extractor) m_extractor = std::make_unique<MFCCExtractor>();
    if (!m_extractor->init()) {
#if defined(ESP_PLATFORM)
        ESP_LOGE(TAG, "MFCC initialization failed");
#endif
        return false;
    }
    reset();
#if defined(ESP_PLATFORM)
    ESP_LOGI(TAG, "Local KWS ready (16 kHz, 1 s window, 250 ms stride)");
#endif
    return true;
}

bool LocalKws::start() {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_extractor || !m_ring) return false;
    memset(m_ring, 0, sizeof(float) * TOTAL_SAMPLES);
    memset(m_window, 0, sizeof(float) * TOTAL_SAMPLES);
    m_head = 0;
    m_samples_since_step = 0;
    m_last_class = -1;
    m_last_class_ms = INITIAL_LAST_MS;
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

void LocalKws::appendSamples(const int16_t* pcm, size_t samples) {
    for (size_t i = 0; i < samples; ++i) {
        m_ring[m_head] = static_cast<float>(pcm[i]) / 32768.0f;
        m_head = (m_head + 1) % TOTAL_SAMPLES;
    }
}

bool LocalKws::inferWindow(uint64_t now_ms) {
#if defined(ESP_PLATFORM)
    const int64_t started_us = esp_timer_get_time();
#endif
    for (size_t i = 0; i < TOTAL_SAMPLES; ++i) {
        m_window[i] = m_ring[(m_head + i) % TOTAL_SAMPLES];
    }
    m_extractor->extract(m_window, m_mfcc);

    float probabilities[NUM_CLASSES] = {};
    kws_run_inference_quantized(m_mfcc, probabilities, m_pool_scratch, m_dw_scratch);
#if defined(ESP_PLATFORM)
    ESP_LOGI(TAG, "KWS_WINDOW elapsed_us=%lld stride_ms=250 free_internal=%u free_psram=%u",
        static_cast<long long>(esp_timer_get_time() - started_us),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
#endif

    int top_class = 0;
    float top_probability = probabilities[0];
    for (int i = 1; i < NUM_CLASSES; ++i) {
        if (probabilities[i] > top_probability) {
            top_probability = probabilities[i];
            top_class = i;
        }
    }
    if (!std::isfinite(top_probability) || top_probability < 0.0f || top_probability > 1.0f) {
        return false;
    }

    const bool usable = top_class != CLASS_NOISE && top_class != CLASS_UNKNOWN &&
        top_probability >= EXECUTION_CONFIDENCE;
    if (usable) {
        const bool repeated = top_class == m_last_class &&
            now_ms - m_last_class_ms < SAME_CLASS_DEDUP_MS;
        if (!repeated) {
            m_command.add(top_class, top_probability);
            m_last_class = top_class;
            m_last_class_ms = now_ms;
        }
    }
    m_partial = m_command.text();
    return true;
}

bool LocalKws::feedAudio(const int16_t* pcm, size_t samples) {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_active) return false;
    if (!pcm || samples == 0) return true;


    size_t offset = 0;
    while (offset < samples) {
        const size_t capacity = STEP_SAMPLES - m_samples_since_step;
        const size_t take = std::min(capacity, samples - offset);
        appendSamples(pcm + offset, take);
        offset += take;
        m_samples_since_step += take;
        if (m_samples_since_step >= STEP_SAMPLES) {
            m_samples_since_step = 0;
            if (!inferWindow(nowMs())) {
                m_inference_failed = true;
                return false;
            }
        }
    }
    return true;
}

void LocalKws::stop() {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_active) return;
    if (m_samples_since_step > 0 && m_extractor) {
        // Catch a word ending between 250 ms boundaries. Duplicate windows
        // are filtered by same-class deduplication.
        if (!inferWindow(nowMs())) m_inference_failed = true;
    }

    m_final = m_inference_failed ? "__KWS_AUDIO_ERROR__" : commandText();
    m_has_final = true;
    m_active = false;
    m_samples_since_step = 0;
}

void LocalKws::cancel() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_active = false;
    m_final = "__KWS_AUDIO_ERROR__";
    m_has_final = true;
    m_partial.clear();
    m_samples_since_step = 0;
}

bool LocalKws::hasPartialResult() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_active && !m_partial.empty() && m_partial != "__KWS_EMPTY__" &&
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
    m_head = 0;
    m_samples_since_step = 0;
    m_last_class = -1;
    m_last_class_ms = INITIAL_LAST_MS;
    m_command.reset();
    m_partial.clear();
    m_final.clear();
    if (m_ring) memset(m_ring, 0, sizeof(float) * TOTAL_SAMPLES);
    if (m_window) memset(m_window, 0, sizeof(float) * TOTAL_SAMPLES);
}

bool LocalKws::isActive() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_active;
}

std::string LocalKws::commandText() const {
    return m_command.text();
}
