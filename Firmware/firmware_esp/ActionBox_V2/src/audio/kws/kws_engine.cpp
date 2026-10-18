#include "kws_engine.h"
#include "kws_config.h"
#include "kws_mfcc.h"
#include "kws_model_quantized.h"
#include "actionbox_protocol.h"
#include "espnow_transport.h"

#include <string.h>
#include <stdio.h>
#include <atomic>
#include <new>
#include "esp_log.h"
#include "esp_timer.h"

#if defined(ESP_PLATFORM)
#include "esp_heap_caps.h"
static void* kws_alloc(size_t size) {
    void* ptr = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!ptr) ptr = malloc(size);
    return ptr;
}
#else
static void* kws_alloc(size_t size) {
    return malloc(size);
}
#endif

static const char *TAG = "KWS_ENGINE";

static float *s_audio_ring = NULL;
static float *s_audio_window = NULL;
static float *s_mfcc_buffer = NULL;
static MFCCExtractor *s_mfcc = NULL;
static float *s_pool1_buffer = NULL;
static float *s_dw_buffer = NULL;

static size_t s_ring_head = 0;
static size_t s_samples_since_last_infer = 0;
static std::atomic<bool> s_observation_mode{true};
static uint32_t s_last_detection_time = 0;
static bool s_first_detection = true;
static uint8_t s_event_seq = 0;
static uint32_t s_session_id = 0;

esp_err_t kws_engine_init(void) {
    if (!s_audio_ring) {
        s_audio_ring = (float*)kws_alloc(sizeof(float) * TOTAL_SAMPLES);
        if (!s_audio_ring) return ESP_ERR_NO_MEM;
    }
    if (!s_audio_window) {
        s_audio_window = (float*)kws_alloc(sizeof(float) * TOTAL_SAMPLES);
        if (!s_audio_window) return ESP_ERR_NO_MEM;
    }
    if (!s_mfcc_buffer) {
        s_mfcc_buffer = (float*)kws_alloc(sizeof(float) * NUM_FRAMES * NUM_MFCC_COEFFS);
        if (!s_mfcc_buffer) return ESP_ERR_NO_MEM;
    }
    if (!s_pool1_buffer) {
        s_pool1_buffer = (float*)kws_alloc(sizeof(float) * 16 * 49 * 6);
        if (!s_pool1_buffer) return ESP_ERR_NO_MEM;
    }
    if (!s_dw_buffer) {
        s_dw_buffer = (float*)kws_alloc(sizeof(float) * 32 * 49 * 6);
        if (!s_dw_buffer) return ESP_ERR_NO_MEM;
    }
    if (!s_mfcc) {
        void* mem = kws_alloc(sizeof(MFCCExtractor));
        if (!mem) {
            ESP_LOGE(TAG, "Failed to allocate memory for MFCCExtractor");
            return ESP_ERR_NO_MEM;
        }
        s_mfcc = new (mem) MFCCExtractor();
    }
    if (!s_mfcc->init()) {
        ESP_LOGE(TAG, "Failed to initialize MFCC extractor");
        return ESP_FAIL;
    }
    memset(s_audio_ring, 0, sizeof(float) * TOTAL_SAMPLES);
    s_ring_head = 0;
    s_samples_since_last_infer = 0;
    s_observation_mode.store(true);
    s_last_detection_time = 0;
    s_first_detection = true;
    s_event_seq = 0;
    s_session_id = (uint32_t)(esp_timer_get_time() & 0xFFFFFFFF);
    ESP_LOGI(TAG, "KWS engine initialized in Observation Mode (16kHz, INT8, stride=250ms)");
    return ESP_OK;
}

void kws_engine_feed_samples(const int16_t *pcm, size_t count) {
    if (!pcm || count == 0 || !s_audio_ring) return;
    for (size_t i = 0; i < count; i++) {
        s_audio_ring[s_ring_head] = (float)pcm[i] / 32768.0f;
        s_ring_head = (s_ring_head + 1) % TOTAL_SAMPLES;
    }
    s_samples_since_last_infer += count;
}

bool kws_engine_step(int *out_class_id, float *out_confidence) {
    if (!s_audio_ring || !s_audio_window || !s_mfcc_buffer || !s_mfcc) {
        if (out_class_id) *out_class_id = -1;
        if (out_confidence) *out_confidence = 0.0f;
        return false;
    }

    if (s_samples_since_last_infer < STEP_SAMPLES) {
        if (out_class_id) *out_class_id = -1;
        if (out_confidence) *out_confidence = 0.0f;
        return false;
    }
    s_samples_since_last_infer = (s_samples_since_last_infer >= STEP_SAMPLES + 2000)
                                     ? 0
                                     : (s_samples_since_last_infer - STEP_SAMPLES);

    for (size_t i = 0; i < TOTAL_SAMPLES; i++) {
        size_t idx = (s_ring_head + i) % TOTAL_SAMPLES;
        s_audio_window[i] = s_audio_ring[idx];
    }

    s_mfcc->extract(s_audio_window, s_mfcc_buffer);

    float probs[NUM_CLASSES];
    kws_run_inference_quantized(s_mfcc_buffer, probs, s_pool1_buffer, s_dw_buffer);

    int top_class = 0;
    float top_prob = probs[0];
    for (int i = 1; i < NUM_CLASSES; i++) {
        if (probs[i] > top_prob) {
            top_prob = probs[i];
            top_class = i;
        }
    }

    if (out_class_id) *out_class_id = top_class;
    if (out_confidence) *out_confidence = top_prob;

    uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    bool is_keyword = (top_class != CLASS_NOISE &&
                       top_class != CLASS_UNKNOWN &&
                       top_prob >= CONFIDENCE_THRESHOLD);
    bool cooldown_passed = s_first_detection || (now_ms - s_last_detection_time >= COOLDOWN_MS);

    if (is_keyword && cooldown_passed) {
        s_first_detection = false;
        s_last_detection_time = now_ms;

        if (s_observation_mode.load()) {
            ESP_LOGI(TAG, "[KWS OBSERVE] Detected keyword '%s' (id=%d, conf=%.2f) - OBSERVATION MODE ONLY (NO RELAY ACTUATION)",
                     KWS_LABELS[top_class], top_class, top_prob);

            ActionBoxKeywordEventPacket pkt = {};
            pkt.msg_type = MSG_TYPE_KEYWORD_EVENT;
            pkt.seq = ++s_event_seq;
            pkt.keyword_id = (uint8_t)top_class;
            pkt.confidence_pct = (uint8_t)(top_prob * 100.0f);
            pkt.session_id = s_session_id;
            pkt.rel_time_ms = now_ms;

            espnow_transport_send((const uint8_t *)&pkt, sizeof(pkt));

        }
        return true;
    }

    return false;
}

bool kws_engine_is_observation_mode(void) {
    return s_observation_mode.load();
}

void kws_engine_set_observation_mode(bool enable) {
    s_observation_mode.store(enable);
}
