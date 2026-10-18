#pragma once

#include <functional>
#include <string>
#include "audio_packet.h"

class AudioTransport {
public:
    virtual ~AudioTransport() = default;

    virtual bool init() = 0;

    virtual bool sendAudio(const char* target_node_id, const AudioPacket& packet) = 0;
    virtual bool sendCommand(const char* target_node_id, const std::string& json_cmd, std::string* response = nullptr) { return false; }
    virtual void registerJsonCallback(std::function<void(const std::string&)> callback) {}

    virtual void registerRxCallback(std::function<void(const AudioPacket&)> callback) = 0;

    virtual void stop() = 0;

    virtual bool isRunning() const = 0;
};
