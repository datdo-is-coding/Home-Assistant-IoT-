/**
 * @file udp_audio_transport.cpp
 * @brief High-Speed UDP Implementation of AudioTransport
 */

#include "udp_audio_transport.h"
#include "esp_log.h"
#include <cstring>
#include <cerrno>

static const char *TAG = "UDP_TRANSPORT";

UdpAudioTransport::UdpAudioTransport(uint16_t rx_port, uint16_t tx_port)
    : m_rx_port(rx_port),
      m_tx_port(tx_port),
      m_rx_socket(-1),
      m_tx_socket(-1),
      m_running(false),
      m_rx_task_handle(nullptr),
      m_rx_callback(nullptr) {
}

UdpAudioTransport::~UdpAudioTransport() {
    stop();
}

bool UdpAudioTransport::init() {
    if (m_running) return true;

    ESP_LOGI(TAG, "Initializing UDP Audio Transport on RX Port %u...", m_rx_port);

    m_rx_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (m_rx_socket < 0) {
        ESP_LOGE(TAG, "Unable to create RX socket: errno %d", errno);
        return false;
    }

    // Set receive timeout so loop can check m_running flag
    struct timeval timeout = {};
    timeout.tv_sec = 0;
    timeout.tv_usec = 200000; // 200ms
    setsockopt(m_rx_socket, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    // Enable socket address reuse
    int opt = 1;
    setsockopt(m_rx_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in bind_addr = {};
    bind_addr.sin_family = AF_INET;
    bind_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    bind_addr.sin_port = htons(m_rx_port);

    int err = bind(m_rx_socket, (struct sockaddr *)&bind_addr, sizeof(bind_addr));
    if (err < 0) {
        ESP_LOGE(TAG, "Socket unable to bind to port %u: errno %d", m_rx_port, errno);
        close(m_rx_socket);
        m_rx_socket = -1;
        return false;
    }

    // Create TX socket
    m_tx_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (m_tx_socket < 0) {
        ESP_LOGE(TAG, "Unable to create TX socket: errno %d", errno);
        close(m_rx_socket);
        m_rx_socket = -1;
        return false;
    }

    // Enable broadcast on TX socket
    int bcast_opt = 1;
    setsockopt(m_tx_socket, SOL_SOCKET, SO_BROADCAST, &bcast_opt, sizeof(bcast_opt));

    m_running = true;

    BaseType_t res = xTaskCreatePinnedToCore(
        rxTaskTrampoline,
        "udp_audio_rx",
        TASK_STACK_AUDIO_RX,
        this,
        TASK_PRIO_AUDIO_RX,
        &m_rx_task_handle,
        0 // Pin to Core 0 for networking
    );

    if (res != pdPASS) {
        ESP_LOGE(TAG, "Failed to create udp_audio_rx task!");
        stop();
        return false;
    }

    ESP_LOGI(TAG, "UDP Audio Transport operational (RX: %u, TX: %u)", m_rx_port, m_tx_port);
    return true;
}

void UdpAudioTransport::stop() {
    if (!m_running) return;
    ESP_LOGI(TAG, "Stopping UDP Audio Transport...");
    m_running = false;

    if (m_rx_socket >= 0) {
        shutdown(m_rx_socket, 0);
        close(m_rx_socket);
        m_rx_socket = -1;
    }

    if (m_tx_socket >= 0) {
        close(m_tx_socket);
        m_tx_socket = -1;
    }

    if (m_rx_task_handle) {
        vTaskDelay(pdMS_TO_TICKS(100));
        m_rx_task_handle = nullptr;
    }
}

void UdpAudioTransport::registerRxCallback(std::function<void(const AudioPacket&)> callback) {
    std::lock_guard<std::mutex> lock(m_callback_mutex);
    m_rx_callback = callback;
}

bool UdpAudioTransport::sendAudio(const char* target_node_id, const AudioPacket& packet) {
    if (m_tx_socket < 0 || !packet.payload_len) return false;

    struct sockaddr_in dest_addr = {};
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(m_tx_port);

    bool endpoint_found = false;
    if (target_node_id && strlen(target_node_id) > 0) {
        std::lock_guard<std::mutex> lock(m_endpoints_mutex);
        auto it = m_node_endpoints.find(target_node_id);
        if (it != m_node_endpoints.end()) {
            dest_addr.sin_addr = it->second.sin_addr;
            endpoint_found = true;
        }
    }

    if (!endpoint_found) {
        // Fallback: Broadcast to subnet
        dest_addr.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    }

    size_t packet_size = sizeof(AudioPacket) - (SUBBOX_AUDIO_MAX_PACKET_PAYLOAD - packet.payload_len);
    int sent = sendto(m_tx_socket, &packet, packet_size, 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    return (sent > 0);
}

void UdpAudioTransport::rxTaskTrampoline(void* pvParameters) {
    auto* self = static_cast<UdpAudioTransport*>(pvParameters);
    self->runRxLoop();
    vTaskDelete(NULL);
}

void UdpAudioTransport::runRxLoop() {
    uint8_t rx_buffer[sizeof(AudioPacket) + 64];
    struct sockaddr_in source_addr = {};
    socklen_t socklen = sizeof(source_addr);

    ESP_LOGI(TAG, "Audio RX listening loop active on socket %d", m_rx_socket);

    while (m_running) {
        int len = recvfrom(m_rx_socket, rx_buffer, sizeof(rx_buffer), 0, (struct sockaddr *)&source_addr, &socklen);

        if (len < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Timeout, normal idle poll
                continue;
            }
            if (m_running) {
                ESP_LOGW(TAG, "recvfrom error: %d", errno);
            }
            continue;
        }

        if (len < (int)(sizeof(AudioPacket) - SUBBOX_AUDIO_MAX_PACKET_PAYLOAD)) {
            ESP_LOGW(TAG, "Received truncated audio packet (%d bytes), dropping", len);
            continue;
        }

        const auto* pkt = reinterpret_cast<const AudioPacket*>(rx_buffer);

        if (pkt->version != AUDIO_PROTOCOL_VERSION) {
            ESP_LOGW(TAG, "Unsupported audio protocol version: %u, expected %u", pkt->version, AUDIO_PROTOCOL_VERSION);
            continue;
        }

        // Cache ActionBox network endpoint for downlink audio responses
        if (strlen(pkt->source_node_id) > 0) {
            std::lock_guard<std::mutex> lock(m_endpoints_mutex);
            m_node_endpoints[pkt->source_node_id] = source_addr;
        }

        // Deliver to audio pipeline
        std::function<void(const AudioPacket&)> cb_copy;
        {
            std::lock_guard<std::mutex> lock(m_callback_mutex);
            cb_copy = m_rx_callback;
        }

        if (cb_copy) {
            cb_copy(*pkt);
        }
    }

    ESP_LOGI(TAG, "Audio RX loop terminated.");
}
