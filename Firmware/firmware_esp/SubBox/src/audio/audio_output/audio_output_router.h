/**
 * @file audio_output_router.h
 * @brief Downlink Audio / TTS Router to Specific ActionBox Speakers
 */

#pragma once

#include <string>
#include <memory>
#include <mutex>
#include "audio/audio_transport/audio_transport.h"

class AudioOutputRouter {
public:
    explicit AudioOutputRouter(std::shared_ptr<AudioTransport> transport);
    ~AudioOutputRouter() = default;

    /**
     * @brief Route response audio packets to specific or last-spoke ActionBox
     * @param target_node_id ActionBox node ID (or nullptr to use last input node)
     * @param pcm_bytes Raw PCM audio data buffer
     * @param len Buffer length in bytes
     * @return true if successfully dispatched
     */
    bool sendAudioResponse(const char* target_node_id, const uint8_t* pcm_bytes, size_t len);

    /**
     * @brief Broadcast audio response to all ActionBoxes in room
     */
    bool broadcastAudioResponse(const uint8_t* pcm_bytes, size_t len);

    void setLastInputNodeId(const std::string& node_id);
    std::string getLastSpeakerNodeId() const;

private:
    std::shared_ptr<AudioTransport> m_transport;
    std::string m_last_input_node_id;
    std::string m_last_speaker_node_id;
    uint16_t m_tx_seq;
    mutable std::mutex m_mutex;
};
