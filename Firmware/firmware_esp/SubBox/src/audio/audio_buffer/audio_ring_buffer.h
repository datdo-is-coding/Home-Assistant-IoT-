/**
 * @file audio_ring_buffer.h
 * @brief Thread-Safe PSRAM-Backed Circular Audio Buffer for PCM Streams
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include <mutex>
#include "esp_heap_caps.h"

class AudioRingBuffer {
public:
    explicit AudioRingBuffer(size_t capacity_samples = (128 * 1024));
    ~AudioRingBuffer();

    bool init();
    size_t write(const int16_t* samples, size_t count);
    size_t read(int16_t* destination, size_t max_count);
    size_t peek(int16_t* destination, size_t max_count) const;
    void advance(size_t count);
    void clear();

    size_t getAvailableSamples() const;
    size_t getFreeSamples() const;
    size_t getCapacity() const { return m_capacity; }

private:
    size_t m_capacity;
    int16_t* m_buffer;
    size_t m_head;
    size_t m_tail;
    size_t m_count;
    mutable std::mutex m_mutex;
    bool m_allocated_in_psram;
};
