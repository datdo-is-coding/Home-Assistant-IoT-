/**
 * @file audio_manager.cpp
 * @brief Multi-Source Audio Stream Manager & Best-Signal Selector Implementation
 */

#include "audio_manager.h"
#include <cmath>
#include <cstring>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char* TAG = "AUDIO_MGR";

AudioManager::AudioManager(std::shared_ptr<VADInterface> vad, std::shared_ptr<ASREngine> asr)
    : m_vad(vad),
      m_asr(asr),
      m_session_active(false),
      m_utterance_callback(nullptr) {
}

AudioManager::~AudioManager() {
    reset();
}

bool AudioManager::init() {
    ESP_LOGI(TAG, "Initializing Multi-ActionBox Audio Manager (Capacity: %d nodes)...", SUBBOX_MAX_ACTIONBOXES_PER_ROOM);
    reset();
    return true;
}

void AudioManager::reset() {
    std::lock_guard<std::mutex> lock(m_mutex);
    ++m_session_generation;
    m_asr_start_pending = false;
    m_session_active = false;
    m_stream_end_received = false;
    m_active_source_node_id.clear();
    for (auto& pair : m_channels) {
        if (pair.second.stream_buffer) {
            pair.second.stream_buffer->clear();
        }
        pair.second.is_speaking = false;
    }
    if (m_vad) m_vad->reset();
    if (m_asr) m_asr->reset();
}

void AudioManager::registerUtteranceCallback(std::function<void(const std::string&, const std::string&)> cb) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_utterance_callback = cb;
}

std::string AudioManager::getLastInputNodeId() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_last_input_node_id;
}

std::string AudioManager::getActiveSourceNodeId() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_active_source_node_id;
}

std::map<std::string, ActionBoxAudioChannel> AudioManager::getChannelSnapshots() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_channels;
}

void AudioManager::updateChannelMetrics(ActionBoxAudioChannel& ch, const AudioPacket& packet) {
    ch.last_timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);

    // Packet loss detection
    if (ch.packets_received > 0) {
        uint16_t expected_seq = (ch.last_seq + 1) & 0xFFFF;
        if (packet.sequence_num > expected_seq) {
            uint16_t lost = packet.sequence_num - expected_seq;
            ch.packets_lost += lost;
            ESP_LOGW(TAG, "Node %s packet loss: %u packet(s) dropped (Expected %u, Got %u)",
                     ch.node_id.c_str(), lost, expected_seq, packet.sequence_num);
        }
    }
    ch.last_seq = packet.sequence_num;
    ch.packets_received++;

    // Calculate RMS and Energy of incoming chunk
    size_t samples = packet.payload_len / sizeof(int16_t);
    if (samples > 0) {
        const auto* pcm = reinterpret_cast<const int16_t*>(packet.payload);
        int64_t sum_sq = 0;
        for (size_t i = 0; i < samples; ++i) {
            int32_t s = pcm[i];
            sum_sq += (int64_t)s * s;
        }
        ch.latest_energy = sum_sq / (int64_t)samples;
        ch.latest_rms = sqrtf((float)ch.latest_energy);
    }

    // Calculate signal quality factor (combining packet reception ratio & SNR)
    uint32_t total_expected = ch.packets_received + ch.packets_lost;
    float packet_ratio = (total_expected > 0) ? (float)ch.packets_received / (float)total_expected : 1.0f;
    float level_score = std::min(1.0f, ch.latest_rms / 3000.0f);
    ch.signal_quality = 0.6f * packet_ratio + 0.4f * level_score;

    ch.is_speaking = (ch.latest_energy >= SUBBOX_VAD_INITIAL_ENERGY_THRESH);
}

void AudioManager::ingestAudioPacket(const AudioPacket& packet) {
    if (strlen(packet.source_node_id) == 0) return;

    std::lock_guard<std::mutex> lock(m_mutex);
    std::string node_id = packet.source_node_id;

    // Handle explicit STREAM_END from ActionBox
    if (packet.msg_type == AUDIO_MSG_TYPE_STREAM_END) {
        if (m_session_active && m_active_source_node_id == node_id) {
            m_stream_end_received = true;
            ESP_LOGI(TAG, "🛑 [STREAM_END] ActionBox %s signalled speech end", node_id.c_str());
        }
        return;
    }

    // Locate or register channel entry
    auto it = m_channels.find(node_id);
    if (it == m_channels.end()) {
        if (m_channels.size() >= SUBBOX_MAX_ACTIONBOXES_PER_ROOM) {
            ESP_LOGW(TAG, "Room ActionBox limit reached (%d), ignoring new node: %s",
                     SUBBOX_MAX_ACTIONBOXES_PER_ROOM, node_id.c_str());
            return;
        }

        ActionBoxAudioChannel new_ch;
        new_ch.node_id = node_id;
        new_ch.last_timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        new_ch.last_seq = packet.sequence_num;
        new_ch.packets_received = 0;
        new_ch.packets_lost = 0;
        new_ch.latest_rms = 0.0f;
        new_ch.latest_energy = 0;
        new_ch.is_speaking = false;
        new_ch.signal_quality = 1.0f;
        new_ch.stream_buffer = std::make_shared<AudioRingBuffer>(64 * 1024); // 64K samples (~4s)
        new_ch.stream_buffer->init();

        it = m_channels.emplace(node_id, std::move(new_ch)).first;
        ESP_LOGI(TAG, "Registered new audio stream channel for ActionBox: %s", node_id.c_str());
    }

    // If packet is explicit STREAM_START, prioritize this node and begin ASR session
    if (packet.msg_type == AUDIO_MSG_TYPE_STREAM_START && !m_session_active) {
        m_active_source_node_id = node_id;
        m_last_input_node_id = node_id;
        m_session_active = true;
        m_stream_end_received = false;
        it->second.stream_buffer->clear();
        ++m_session_generation;
        m_asr_start_pending = true;
        m_session_failed = false;
        if (m_vad) m_vad->reset();
        ESP_LOGI(TAG, "🎙️ [STREAM_START] Explicit session lock onto ActionBox: %s (ASR started)", node_id.c_str());
        return;
    }

    if (!packet.payload_len) return;

    ActionBoxAudioChannel& ch = it->second;
    updateChannelMetrics(ch, packet);

    // Buffer PCM samples into channel's ring buffer
    size_t samples = packet.payload_len / sizeof(int16_t);
    const auto* pcm = reinterpret_cast<const int16_t*>(packet.payload);
    ch.stream_buffer->write(pcm, samples);
}

void AudioManager::evaluateSourceSelection() {
    if (m_session_active) return; // Stay locked until active utterance concludes

    std::string best_candidate;
    float best_score = -1.0f;

    for (const auto& pair : m_channels) {
        const auto& ch = pair.second;
        if (ch.is_speaking && ch.stream_buffer->getAvailableSamples() >= SUBBOX_AUDIO_FRAME_SAMPLES) {
            // Arbitration Score: Signal Quality * Energy
            float score = ch.signal_quality * (float)ch.latest_energy;
            if (score > best_score) {
                best_score = score;
                best_candidate = ch.node_id;
            }
        }
    }

    if (!best_candidate.empty() && best_score > 0.0f) {
        m_active_source_node_id = best_candidate;
        m_last_input_node_id = best_candidate;
        m_session_active = true;
        m_stream_end_received = false;
        ++m_session_generation;
        m_asr_start_pending = true;
        m_session_failed = false;
        if (m_vad) m_vad->reset();

        ESP_LOGI(TAG, "🎙️ Source Arbitrator selected best active ActionBox: %s (RMS=%.1f, Score=%.0f)",
                 best_candidate.c_str(), m_channels[best_candidate].latest_rms, best_score);
    }
}

void AudioManager::process() {
    std::unique_lock<std::mutex> lock(m_mutex);

    evaluateSourceSelection();

    if (!m_session_active || m_active_source_node_id.empty()) {
        return;
    }

    auto it = m_channels.find(m_active_source_node_id);
    if (it == m_channels.end() || !it->second.stream_buffer) {
        m_session_active = false;
        m_stream_end_received = false;
        m_active_source_node_id.clear();
        return;
    }

    const auto active_buffer = it->second.stream_buffer;
    const uint32_t generation = m_session_generation;
    if (m_asr_start_pending) {
        m_asr_start_pending = false;
        lock.unlock();
        const bool started = m_asr && m_asr->start();
        lock.lock();
        if (generation != m_session_generation) return;
        if (!started) {
            m_session_active = false;
            m_stream_end_received = false;
            m_active_source_node_id.clear();
            active_buffer->clear();
            it->second.is_speaking = false;
            return;
        }
    }
    int16_t frame[SUBBOX_AUDIO_FRAME_SAMPLES];

    while (active_buffer->getAvailableSamples() >= SUBBOX_AUDIO_FRAME_SAMPLES) {
        size_t read_count = active_buffer->read(frame, SUBBOX_AUDIO_FRAME_SAMPLES);
        if (read_count != SUBBOX_AUDIO_FRAME_SAMPLES) break;

        // 1. Process VAD
        if (m_vad) {
            m_vad->process(frame, read_count);
        }

        // 2. Feed into ASR Engine
        if (m_asr) {
            lock.unlock();
            const bool sent = m_asr->feedAudio(frame, read_count);
            lock.lock();
            if (generation != m_session_generation) return;
            if (!sent) {
                m_session_failed = true;
                m_stream_end_received = true;
                active_buffer->clear();
                break;
            }
        }
        taskYIELD();
    }

    // 3. Check for End of Speech (Explicit ActionBox STREAM_END or VAD Silence Timeout 1.5s or ASR Final Trigger)
    bool speech_finished = false;
    if (m_stream_end_received) {
        speech_finished = true;
    } else if (m_vad && m_vad->speechEnded()) {
        speech_finished = true;
    } else if (m_asr && m_asr->hasFinalResult()) {
        speech_finished = true;
    }

    if (speech_finished) {
        // Drain any remaining fractional samples into ASR
        while (active_buffer->getAvailableSamples() > 0) {
            size_t rem = active_buffer->getAvailableSamples();
            if (rem > SUBBOX_AUDIO_FRAME_SAMPLES) rem = SUBBOX_AUDIO_FRAME_SAMPLES;
            size_t read_count = active_buffer->read(frame, rem);
            if (read_count > 0 && m_asr) {
                lock.unlock();
                const bool sent = m_asr->feedAudio(frame, read_count);
                lock.lock();
                if (generation != m_session_generation) return;
                if (!sent) {
                    m_session_failed = true;
                    active_buffer->clear();
                    break;
                }
            }
        }

        // Stop ASR feed (tells server to finalize)
        if (m_asr) {
            lock.unlock();
            m_asr->stop();
            lock.lock();
            if (generation != m_session_generation) return;
        }

        std::string final_text;
        // If final result is not immediately ready, await transcription
        if (m_asr && !m_asr->hasFinalResult()) {
            lock.unlock();
            for (int i = 0; i < 25; i++) { // Up to 2.5s wait
                vTaskDelay(pdMS_TO_TICKS(100));
                if (m_asr->hasFinalResult()) break;
            }
            lock.lock();
            if (generation != m_session_generation) return;
        }

        if (!m_session_failed && m_asr && m_asr->hasFinalResult()) {
            final_text = m_asr->getFinalResult();
        }

        std::string completed_node = m_active_source_node_id;

        // Release session lock
        m_session_active = false;
        m_stream_end_received = false;
        m_active_source_node_id.clear();
        active_buffer->clear();

        if (!final_text.empty()) {
            ESP_LOGI(TAG, "✅ Utterance complete from node %s: \"%s\"", completed_node.c_str(), final_text.c_str());

            auto cb = m_utterance_callback;
            lock.unlock(); // Unlock before dispatching to NLU

            if (cb) {
                cb(completed_node, final_text);
            }
            return;
        } else {
            ESP_LOGW(TAG, "⚠️ Utterance from %s completed with empty transcript", completed_node.c_str());
        }
    }
}
