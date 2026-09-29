/**
 * @file audio_transport.h
 * @brief Abstract Audio Transport Interface for Decoupled Network Layer
 */

#pragma once

#include <functional>
#include <string>
#include "audio_packet.h"

class AudioTransport {
public:
    virtual ~AudioTransport() = default;

    /**
     * @brief Initialize socket / network hardware
     * @return true on success
     */
    virtual bool init() = 0;

    /**
     * @brief Transmit audio packet to a specific target ActionBox
     * @param target_node_id ActionBox identifier or IP/MAC string
     * @param packet Audio packet containing payload
     * @return true if successfully dispatched
     */
    virtual bool sendAudio(const char* target_node_id, const AudioPacket& packet) = 0;
    virtual bool sendCommand(const char* target_node_id, const std::string& json_cmd, std::string* response = nullptr) { return false; }
    virtual void registerJsonCallback(std::function<void(const std::string&)> callback) {}

    /**
     * @brief Register callback function for incoming audio packets
     * @param callback Function receiving validated AudioPacket
     */
    virtual void registerRxCallback(std::function<void(const AudioPacket&)> callback) = 0;

    /**
     * @brief Stop transport and release socket resources
     */
    virtual void stop() = 0;

    /**
     * @brief Check if transport is currently active and connected
     */
    virtual bool isRunning() const = 0;
};
