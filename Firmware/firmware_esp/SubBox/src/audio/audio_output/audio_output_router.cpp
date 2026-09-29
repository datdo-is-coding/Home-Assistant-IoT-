/**
 * @file audio_output_router.cpp
 * @brief Downlink Audio / TTS Router Implementation
 */

#include "audio_output_router.h"
#include <cstring>
#include <algorithm>
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "AUDIO_OUTPUT";

AudioOutputRouter::AudioOutputRouter(std::shared_ptr<AudioTransport> transport)
    : m_transport(transport),
      m_tx_seq(0) {
}

void AudioOutputRouter::setLastInputNodeId(const std::string& node_id) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_last_input_node_id = node_id;
}

std::string AudioOutputRouter::getLastSpeakerNodeId() const {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_last_speaker_node_id;
}

bool AudioOutputRouter::sendAudioResponse(const char* target_node_id, const uint8_t* pcm_bytes, size_t len) {
    if (!m_transport || !pcm_bytes || len == 0) return false;

    std::string destination;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (target_node_id && strlen(target_node_id) > 0) {
            destination = target_node_id;
        } else if (!m_last_input_node_id.empty()) {
            destination = m_last_input_node_id;
        } else {
            ESP_LOGW(TAG, "No target specified and no prior input node recorded, falling back to broadcast");
            destination = "";
        }
        m_last_speaker_node_id = destination;
    }

    ESP_LOGI(TAG, "Dispatching %u bytes response audio to ActionBox: %s",
             (unsigned)len, destination.empty() ? "[BROADCAST]" : destination.c_str());

    size_t offset = 0;
    while (offset < len) {
        size_t chunk_len = std::min((size_t)SUBBOX_AUDIO_MAX_PACKET_PAYLOAD, len - offset);

        AudioPacket pkt = {};
        pkt.version = AUDIO_PROTOCOL_VERSION;
        pkt.msg_type = AUDIO_MSG_TYPE_DOWNLINK_TTS;
        strncpy(pkt.source_node_id, SUBBOX_DEFAULT_ID, sizeof(pkt.source_node_id) - 1);
        pkt.sequence_num = ++m_tx_seq;
        pkt.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
        pkt.codec = AUDIO_CODEC_RAW_PCM;
        pkt.sample_rate = SUBBOX_AUDIO_SAMPLE_RATE;
        pkt.channels = SUBBOX_AUDIO_CHANNELS;
        pkt.payload_len = (uint16_t)chunk_len;
        std::memcpy(pkt.payload, pcm_bytes + offset, chunk_len);

        m_transport->sendAudio(destination.c_str(), pkt);
        offset += chunk_len;
    }

    return true;
}

bool AudioOutputRouter::broadcastAudioResponse(const uint8_t* pcm_bytes, size_t len) {
    return sendAudioResponse("", pcm_bytes, len);
}
