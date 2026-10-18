#pragma once

#include <string>
#include <memory>
#include <mutex>
#include "audio/audio_transport/audio_transport.h"

class AudioOutputRouter {
public:
    explicit AudioOutputRouter(std::shared_ptr<AudioTransport> transport);
    ~AudioOutputRouter() = default;

    bool sendAudioResponse(const char* target_node_id, const uint8_t* pcm_bytes, size_t len);

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
