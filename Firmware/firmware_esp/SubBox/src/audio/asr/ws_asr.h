#pragma once

#include "asr_engine.h"
#include <string>
#include <mutex>
#include <atomic>
#include <functional>
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

class WsASR : public ASREngine {
public:
    using CommandResultCallback = std::function<void(const std::string& verify, const std::string& voice_reply)>;

    WsASR(const std::string& ws_uri, const std::string& node_id);
    ~WsASR() override;

    bool init() override;
    bool start() override;
    void setSourceNodeId(const char* node_id) override;
    void stop() override;
    void cancel() override;
    bool feedAudio(const int16_t* pcm, size_t samples) override;
    bool hasPartialResult() const override;
    bool hasFinalResult() const override;
    const char* getPartialResult() const override;
    const char* getFinalResult() const override;
    void reset() override;

    bool waitForFinalResult(uint32_t timeout_ms = 2500);

    bool isConnected() const { return m_connected.load(); }
    float getLastConfidence() const { std::lock_guard<std::mutex> lock(m_mutex); return m_confidence; }
    int64_t disconnectedAt() const { return m_disconnected_at.load(); }

    void registerCommandResultCallback(CommandResultCallback cb) {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_cmd_result_cb = cb;
    }
    void registerFollowupCallback(std::function<void(const std::string&)> cb) {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_followup_cb = cb;
    }

private:
    static void wsEventHandler(void* handler_args, esp_event_base_t base, int32_t event_id, void* event_data);
    void handleTextMessage(const char* data, int len);

    std::string m_uri;
    std::string m_ca, m_headers;
    std::atomic<int64_t> m_disconnected_at{0};
    std::string m_node_id;
    std::string m_source_node_id;
    esp_websocket_client_handle_t m_client;
    std::atomic<bool> m_connected;
    std::atomic<bool> m_streaming;
    std::atomic<bool> m_receiving_tts{false};

    mutable std::mutex m_mutex;
    // Receive callbacks need m_mutex even while a socket send is waiting.
    std::mutex m_send_mutex;
    CommandResultCallback m_cmd_result_cb;
    std::function<void(const std::string&)> m_followup_cb;
    std::string m_partial_result;
    std::string m_final_result;
    float m_confidence;
    std::atomic<bool> m_has_final;
    std::atomic<bool> m_has_partial;
    SemaphoreHandle_t m_result_sem;

    int16_t m_send_buf[480];
    size_t  m_send_buf_count;
};
