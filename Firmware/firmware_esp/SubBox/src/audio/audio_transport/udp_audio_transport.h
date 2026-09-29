/**
 * @file udp_audio_transport.h
 * @brief High-Speed UDP Implementation of AudioTransport for ActionBox Audio
 */

#pragma once

#include "audio_transport.h"
#include <map>
#include <string>
#include <mutex>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

class UdpAudioTransport : public AudioTransport {
public:
    UdpAudioTransport(uint16_t rx_port = SUBBOX_UDP_AUDIO_RX_PORT, uint16_t tx_port = SUBBOX_UDP_AUDIO_TX_PORT);
    virtual ~UdpAudioTransport();

    bool init() override;
    bool sendAudio(const char* target_node_id, const AudioPacket& packet) override;
    void registerRxCallback(std::function<void(const AudioPacket&)> callback) override;
    void stop() override;
    bool isRunning() const override { return m_running; }

private:
    static void rxTaskTrampoline(void* pvParameters);
    void runRxLoop();

    uint16_t m_rx_port;
    uint16_t m_tx_port;
    int m_rx_socket;
    int m_tx_socket;
    volatile bool m_running;
    TaskHandle_t m_rx_task_handle;

    std::function<void(const AudioPacket&)> m_rx_callback;
    std::mutex m_callback_mutex;

    // Node ID -> last known IPv4 address mapping
    std::map<std::string, struct sockaddr_in> m_node_endpoints;
    std::mutex m_endpoints_mutex;
};
