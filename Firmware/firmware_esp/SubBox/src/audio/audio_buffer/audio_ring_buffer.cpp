/**
 * @file audio_ring_buffer.cpp
 * @brief Thread-Safe PSRAM-Backed Circular Audio Buffer Implementation
 */

#include "audio_ring_buffer.h"
#include "esp_log.h"
#include <algorithm>
#include <cstring>

static const char* TAG = "AUDIO_BUF";

AudioRingBuffer::AudioRingBuffer(size_t capacity_samples)
    : m_capacity(capacity_samples),
      m_buffer(nullptr),
      m_head(0),
      m_tail(0),
      m_count(0),
      m_allocated_in_psram(false) {
}

AudioRingBuffer::~AudioRingBuffer() {
    clear();
    if (m_buffer) {
        free(m_buffer);
        m_buffer = nullptr;
    }
}

bool AudioRingBuffer::init() {
    if (m_buffer) return true;

    size_t bytes = m_capacity * sizeof(int16_t);

    // Attempt allocation in 16MB Octal PSRAM first
    m_buffer = static_cast<int16_t*>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (m_buffer) {
        m_allocated_in_psram = true;
        ESP_LOGI(TAG, "Allocated %u KB audio ring buffer in PSRAM", (unsigned)(bytes / 1024));
    } else {
        // Fallback to internal SRAM if PSRAM unavailable in test environment
        m_buffer = static_cast<int16_t*>(malloc(bytes));
        m_allocated_in_psram = false;
        if (m_buffer) {
            ESP_LOGW(TAG, "PSRAM allocation failed, allocated %u KB in internal SRAM", (unsigned)(bytes / 1024));
        } else {
            ESP_LOGE(TAG, "AudioRingBuffer allocation of %u bytes failed completely!", (unsigned)bytes);
            return false;
        }
    }

    clear();
    return true;
}

size_t AudioRingBuffer::write(const int16_t* samples, size_t count) {
    if (!m_buffer || !samples || !count) return 0;

    std::lock_guard<std::mutex> lock(m_mutex);

    size_t free_space = m_capacity - m_count;
    size_t to_write = std::min(count, free_space);

    if (to_write == 0) return 0;

    size_t first_chunk = std::min(to_write, m_capacity - m_head);
    std::memcpy(&m_buffer[m_head], samples, first_chunk * sizeof(int16_t));

    size_t second_chunk = to_write - first_chunk;
    if (second_chunk > 0) {
        std::memcpy(&m_buffer[0], samples + first_chunk, second_chunk * sizeof(int16_t));
    }

    m_head = (m_head + to_write) % m_capacity;
    m_count += to_write;

    return to_write;
}

size_t AudioRingBuffer::read(int16_t* destination, size_t max_count) {
    if (!m_buffer || !destination || !max_count) return 0;

    std::lock_guard<std::mutex> lock(m_mutex);

    size_t to_read = std::min(max_count, m_count);
    if (to_read == 0) return 0;

    size_t first_chunk = std::min(to_read, m_capacity - m_tail);
    std::memcpy(destination, &m_buffer[m_tail], first_chunk * sizeof(int16_t));

    size_t second_chunk = to_read - first_chunk;
    if (second_chunk > 0) {
        std::memcpy(destination + first_chunk, &m_buffer[0], second_chunk * sizeof(int16_t));
    }

    m_tail = (m_tail + to_read) % m_capacity;
    m_count -= to_read;

    return to_read;
}

size_t AudioRingBuffer::peek(int16_t* destination, size_t max_count) const {
    if (!m_buffer || !destination || !max_count) return 0;

    std::lock_guard<std::mutex> lock(m_mutex);

    size_t to_read = std::min(max_count, m_count);
    if (to_read == 0) return 0;

    size_t first_chunk = std::min(to_read, m_capacity - m_tail);
    std::memcpy(destination, &m_buffer[m_tail], first_chunk * sizeof(int16_t));

    size_t second_chunk = to_read - first_chunk;
    if (second_chunk > 0) {
        std::memcpy(destination + first_chunk, &m_buffer[0], second_chunk * sizeof(int16_t));
    }

    return to_read;
}

void AudioRingBuffer::advance(size_t count) {
    std::lock_guard<std::mutex> lock(m_mutex);
    size_t to_advance = std::min(count, m_count);
    m_tail = (m_tail + to_advance) % m_capacity;
    m_count -= to_advance;
}

void AudioRingBuffer::clear() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_head = 0;
    m_tail = 0;
    m_count = 0;
}

size_t AudioRingBuffer::getAvailableSamples() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_count;
}

size_t AudioRingBuffer::getFreeSamples() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_capacity - m_count;
}
