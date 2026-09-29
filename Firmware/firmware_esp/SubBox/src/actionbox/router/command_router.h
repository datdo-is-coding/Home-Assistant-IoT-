/**
 * @file command_router.h
 * @brief Local vs Cross-Room Command Execution & Router
 */

#pragma once

#include <memory>
#include <string>
#include "nlu/context/context_manager.h"
#include "actionbox/registry/actionbox_registry.h"
#include "audio/audio_transport/audio_transport.h"
#include "audio/audio_output/audio_output_router.h"

// Forward declaration of MqttClient
class MqttClient;

struct ExecutionResult {
    bool        success;
    bool        is_cross_room;
    bool        forwarded_to_pi4;
    std::string response_text;
    std::string target_node_id;
};

class CommandRouter {
public:
    CommandRouter(
        std::shared_ptr<ActionBoxRegistry> registry,
        std::shared_ptr<ContextManager> context_mgr,
        std::shared_ptr<AudioOutputRouter> audio_router,
        std::shared_ptr<AudioTransport> transport
    );
    ~CommandRouter() = default;

    void setMqttClient(std::shared_ptr<MqttClient> mqtt_client);

    /**
     * @brief Route and execute a resolved NLU command
     * @param resolution Fully resolved CommandResolution
     * @return ExecutionResult containing response text and dispatch status
     */
    ExecutionResult route(const CommandResolution& resolution);

private:
    ExecutionResult executeLocalCommand(const CommandResolution& res, const ActionBoxNode& node);
    ExecutionResult forwardToPi4(const CommandResolution& res);
    ExecutionResult forwardCrossRoom(const CommandResolution& res);

    std::shared_ptr<ActionBoxRegistry> m_registry;
    std::shared_ptr<ContextManager>    m_context_mgr;
    std::shared_ptr<AudioOutputRouter> m_audio_router;
    std::shared_ptr<AudioTransport>    m_transport;
    std::shared_ptr<MqttClient>        m_mqtt_client;

    uint32_t m_request_counter;
};
