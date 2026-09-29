/**
 * @file task_manager.h
 * @brief FreeRTOS Task Architecture and Queue Coordinator for SubBox
 */

#pragma once

#include <memory>
#include <string>
#include <type_traits>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#include "audio/audio_manager/audio_manager.h"
#include "audio/audio_transport/audio_transport.h"
#include "audio/audio_output/audio_output_router.h"
#include "tts/tts_manager.h"
#include "nlu/context/context_manager.h"
#include "actionbox/registry/actionbox_registry.h"
#include "actionbox/router/command_router.h"
#include "rules/rule_engine.h"
#include "room/room_manager.h"
#include "mqtt/subbox_mqtt_client.h"

struct UtteranceQueueItem {
    char origin_node_id[32];
    char text[256];
};

struct ResponseQueueItem {
    char target_node_id[32];
    char text[256];
};

// FreeRTOS queues copy bytes; never enqueue owning C++ objects.
struct CommandQueueItem {
    IntentType intent;
    DeviceType device;
    RoomType target_room;
    RoomType speaker_room;
    char origin_node_id[32];
    bool has_value;
    float value;
    bool resolved_via_context;
    bool is_valid;
    char error_reason[256];
    char raw_text[256];
    char gateway_command[384];
};
static_assert(std::is_trivially_copyable<CommandQueueItem>::value,
              "FreeRTOS command items must be trivially copyable");

class TaskManager {
public:
    TaskManager(
        std::shared_ptr<AudioManager> audio_mgr,
        std::shared_ptr<AudioTransport> transport,
        std::shared_ptr<AudioOutputRouter> audio_router,
        std::shared_ptr<TTSManager> tts_mgr,
        std::shared_ptr<ContextManager> context_mgr,
        std::shared_ptr<ActionBoxRegistry> registry,
        std::shared_ptr<CommandRouter> router,
        std::shared_ptr<RuleEngine> rules,
        std::shared_ptr<RoomManager> room_mgr,
        std::shared_ptr<MqttClient> mqtt
    );
    ~TaskManager();

    bool init();

    bool queueUtterance(const std::string& origin_node_id, const std::string& text);
    bool queueCommand(const CommandResolution& res);
    bool queueResponse(const std::string& target_node_id, const std::string& text);

private:
    static void audioManagerTask(void* pvParameters);
    static void nluTask(void* pvParameters);
    static void commandTask(void* pvParameters);
    static void audioTxTask(void* pvParameters);
    static void deviceManagerTask(void* pvParameters);
    static void telemetryTask(void* pvParameters);
    static void systemTask(void* pvParameters);

    std::shared_ptr<AudioManager>      m_audio_mgr;
    std::shared_ptr<AudioTransport>    m_transport;
    std::shared_ptr<AudioOutputRouter> m_audio_router;
    std::shared_ptr<TTSManager>        m_tts_mgr;
    std::shared_ptr<ContextManager>    m_context_mgr;
    std::shared_ptr<ActionBoxRegistry> m_registry;
    std::shared_ptr<CommandRouter>     m_router;
    std::shared_ptr<RuleEngine>        m_rules;
    std::shared_ptr<RoomManager>       m_room_mgr;
    std::shared_ptr<MqttClient>        m_mqtt;

    QueueHandle_t m_utterance_queue;
    QueueHandle_t m_command_queue;
    QueueHandle_t m_response_queue;

    TaskHandle_t m_h_audio_mgr;
    TaskHandle_t m_h_nlu;
    TaskHandle_t m_h_cmd;
    TaskHandle_t m_h_tx;
    TaskHandle_t m_h_dev_mgr;
    TaskHandle_t m_h_telemetry;
    TaskHandle_t m_h_system;
};
