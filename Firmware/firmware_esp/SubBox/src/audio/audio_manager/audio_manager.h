/**
 * @file audio_manager.h
 * @brief Multi-Source Audio Stream Manager & Best-Signal Selector for ActionBoxes
 */

#pragma once

#include <string>
#include <map>
#include <memory>
#include <mutex>
#include <functional>

#include "config/subbox_config.h"
#include "audio/audio_transport/audio_packet.h"
#include "audio/audio_buffer/audio_ring_buffer.h"
#include "audio/vad/vad_interface.h"
#include "audio/asr/asr_engine.h"

struct ActionBoxAudioChannel {
    std::string node_id;
    uint32_t    last_timestamp_ms;
    uint16_t    last_seq;
    uint32_t    packets_received;
    uint32_t    packets_lost;
    float       latest_rms;
    int64_t     latest_energy;
    bool        is_speaking;
    float       signal_quality; // 0.0 - 1.0 score
    std::shared_ptr<AudioRingBuffer> stream_buffer;
};

class AudioManager {
public:
    AudioManager(std::shared_ptr<VADInterface> vad, std::shared_ptr<ASREngine> asr);
    ~AudioManager();

    bool init();

    /**
     * @brief Ingest incoming audio packet from any ActionBox
     * @param packet Audio packet received from network transport
     */
    void ingestAudioPacket(const AudioPacket& packet);

    /**
     * @brief Periodic processing tick (called by audio_manager_task)
     * Performs source selection arbitration, VAD evaluation, and feeds active stream to ASR
     */
    void process();

    /**
     * @brief Register callback for when an utterance is finalized by ASR
     * @param cb Callback receiving (origin_node_id, decoded_transcript)
     */
    void registerUtteranceCallback(std::function<void(const std::string& node_id, const std::string& text)> cb);

    /**
     * @brief Get ActionBox node ID that initiated the last voice command
     */
    std::string getLastInputNodeId() const;

    /**
     * @brief Get currently locked active audio source (or empty if idle)
     */
    std::string getActiveSourceNodeId() const;

    /**
     * @brief Retrieve snapshot of channel statistics for diagnostic CLI
     */
    std::map<std::string, ActionBoxAudioChannel> getChannelSnapshots() const;

    /**
     * @brief Force reset of all audio streams and arbitrator
     */
    void reset();

private:
    void evaluateSourceSelection();
    void updateChannelMetrics(ActionBoxAudioChannel& ch, const AudioPacket& packet);

    std::shared_ptr<VADInterface> m_vad;
    std::shared_ptr<ASREngine>    m_asr;

    std::map<std::string, ActionBoxAudioChannel> m_channels;
    std::string m_active_source_node_id;
    std::string m_last_input_node_id;
    bool m_session_active;
    bool m_stream_end_received = false;
    bool m_asr_start_pending = false;
    bool m_session_failed = false;
    uint32_t m_session_generation = 0;

    mutable std::mutex m_mutex;
    std::function<void(const std::string&, const std::string&)> m_utterance_callback;
};
