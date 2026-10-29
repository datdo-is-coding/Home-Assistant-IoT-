#include "audio_manager.h"
#include <cmath>
#include <cstring>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "audio_output/sound_player.h"

static const char* TAG = "AUDIO_MGR";

AudioManager::AudioManager(std::shared_ptr<VADInterface> vad, std::shared_ptr<ASREngine> asr, bool defer_pcm)
    : m_vad(vad),
      m_asr(asr),
      m_defer_pcm(defer_pcm),
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
    m_wake_source.clear();
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

    {
        uint16_t expected_seq = (ch.last_seq + 1) & 0xFF;
        if (packet.sequence_num != expected_seq) {
            m_session_failed = true;
            uint16_t lost = (packet.sequence_num - expected_seq) & 0xFF;
            ch.packets_lost += lost;
            ESP_LOGW(TAG, "Node %s packet loss: %u packet(s) dropped (Expected %u, Got %u)",
                     ch.node_id.c_str(), lost, expected_seq, packet.sequence_num);
        }
    }
    ch.last_seq = packet.sequence_num;
    ch.packets_received++;

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

    if (packet.msg_type == AUDIO_MSG_TYPE_WAKE) {
        const uint32_t now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
        if (!m_session_active && (m_wake_source != node_id || now - m_wake_time_ms >= 5000) &&
            SoundPlayer::instance().play(SoundType::WAKE)) {
            m_wake_source = node_id;
            m_wake_time_ms = now;
            ESP_LOGI(TAG, "Wake feedback queued for %s", node_id.c_str());
        }
        return;
    }

    if (packet.msg_type == AUDIO_MSG_TYPE_STREAM_END) {
        if (m_session_active && m_active_source_node_id == node_id) {
            const auto channel = m_channels.find(node_id);
            if (channel == m_channels.end() || packet.sequence_num != channel->second.last_seq)
                m_session_failed = true;
            m_stream_end_received = true;
            ESP_LOGI(TAG, "🛑 [STREAM_END] ActionBox %s signalled speech end", node_id.c_str());
        }
        return;
    }

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
        new_ch.stream_buffer = std::make_shared<AudioRingBuffer>((m_defer_pcm ? 96 : 64) * 1024);
        new_ch.stream_buffer->init();

        it = m_channels.emplace(node_id, std::move(new_ch)).first;
        ESP_LOGI(TAG, "Registered new audio stream channel for ActionBox: %s", node_id.c_str());
    }

    if (packet.msg_type == AUDIO_MSG_TYPE_STREAM_START && !m_session_active) {
        m_active_source_node_id = node_id;
        m_last_input_node_id = node_id;
        m_session_active = true;
        m_stream_end_received = false;
        it->second.stream_buffer->clear();
        it->second.last_seq = packet.sequence_num;
        it->second.packets_received = 0;
        it->second.packets_lost = 0;
        it->second.last_timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        ++m_session_generation;
        m_asr_start_pending = true;
        m_session_failed = false;
        if (m_vad) m_vad->reset();
        ESP_LOGI(TAG, "🎙️ [STREAM_START] Capture session locked onto ActionBox: %s", node_id.c_str());
        const uint32_t now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
        if (m_wake_source != node_id || now - m_wake_time_ms >= 5000)
            SoundPlayer::instance().play(SoundType::WAKE);
        m_wake_source.clear();
        return;
    }

    if (packet.msg_type != AUDIO_MSG_TYPE_STREAM_CHUNK || !packet.payload_len) return;
    // Only the selected microphone belongs to this wake-word/follow-up session.
    if (!m_session_active || m_active_source_node_id != node_id || m_stream_end_received) return;
    if (packet.payload_len > sizeof(packet.payload) || packet.payload_len % sizeof(int16_t)) {
        m_session_failed = true;
        return;
    }

    ActionBoxAudioChannel& ch = it->second;
    updateChannelMetrics(ch, packet);

    size_t samples = packet.payload_len / sizeof(int16_t);
    const auto* pcm = reinterpret_cast<const int16_t*>(packet.payload);
    if (ch.stream_buffer->write(pcm, samples) != samples) m_session_failed = true;
}

void AudioManager::evaluateSourceSelection() {
    if (m_session_active) return;

    std::string best_candidate;
    float best_score = -1.0f;

    for (const auto& pair : m_channels) {
        const auto& ch = pair.second;
        if (ch.is_speaking && ch.stream_buffer->getAvailableSamples() >= SUBBOX_AUDIO_FRAME_SAMPLES) {

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
        SoundPlayer::instance().play(SoundType::WAKE);
    }
}

void AudioManager::process() {
    std::unique_lock<std::mutex> lock(m_mutex);

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
    // Receive the complete radio utterance before competing with Wi-Fi uplink.
    if (m_defer_pcm) {
        const uint32_t now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
        if (now - it->second.last_timestamp_ms > 1200) m_session_failed = true;
        if (!m_stream_end_received && !m_session_failed) return;
        if (m_session_failed) {
            m_asr_start_pending = false;
            active_buffer->clear();
        }
    }
    if (m_asr_start_pending) {
        m_asr_start_pending = false;
        const std::string source_node_id = m_active_source_node_id;
        lock.unlock();
        if (m_asr) m_asr->setSourceNodeId(source_node_id.c_str());
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

        if (m_vad) {
            m_vad->process(frame, read_count);
        }

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

    bool speech_finished = false;
    uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    bool packet_silence = (uint32_t)(now_ms - it->second.last_timestamp_ms) > 1200;

    if (m_stream_end_received || m_session_failed) {
        speech_finished = true;
    } else if (packet_silence) {
        ESP_LOGI(TAG, "⏱️ Packet silence timeout (1.2s without audio chunks) from %s", m_active_source_node_id.c_str());
        speech_finished = true;
        m_session_failed = true;
    }

    if (speech_finished) {
        std::string final_text;
        const std::string finished_source = m_active_source_node_id;

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

        if (m_asr) {
            const bool failed = m_session_failed;
            lock.unlock();
            if (failed) m_asr->cancel();
            else m_asr->stop();
            const char* result = m_asr->getFinalResult();
            if (result && result[0]) final_text = result;
            lock.lock();
            if (generation != m_session_generation) return;
        }

        ESP_LOGI(TAG, "PCM relay %s for %s; final text: \"%s\"",
                 m_session_failed ? "cancelled" : "complete", finished_source.c_str(),
                 final_text.c_str());

        m_session_active = false;
        m_stream_end_received = false;
        m_active_source_node_id.clear();
        active_buffer->clear();
        it->second.is_speaking = false;

        auto callback = m_utterance_callback;
        lock.unlock();
        if (callback && !final_text.empty()) callback(finished_source, final_text);
        return;
    }
}
