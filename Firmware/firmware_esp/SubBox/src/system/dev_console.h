/**
 * @file dev_console.h
 * @brief Development Console & Interactive CLI for SubBox
 */

#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <memory>
#include <string>
#include <functional>
#include "audio/asr/asr_engine.h"
#include "audio/audio_manager/audio_manager.h"
#include "nlu/context/context_manager.h"
#include "actionbox/registry/actionbox_registry.h"
#include "actionbox/router/command_router.h"
#include "room/room_manager.h"

class DevConsole {
public:
    DevConsole(
        std::shared_ptr<ASREngine> asr,
        std::shared_ptr<AudioManager> audio_mgr,
        std::shared_ptr<ContextManager> context_mgr,
        std::shared_ptr<ActionBoxRegistry> registry,
        std::shared_ptr<CommandRouter> router,
        std::shared_ptr<RoomManager> room_mgr
    );
    ~DevConsole();

    bool init();
    void processLine(const std::string& line);
    void runNluUnitTests();

private:
    static void consoleTask(void* pvParameters);
    void runConsoleLoop();

    std::shared_ptr<ASREngine>         m_asr;
    std::shared_ptr<AudioManager>      m_audio_mgr;
    std::shared_ptr<ContextManager>    m_context_mgr;
    std::shared_ptr<ActionBoxRegistry> m_registry;
    std::shared_ptr<CommandRouter>     m_router;
    std::shared_ptr<RoomManager>       m_room_mgr;

    TaskHandle_t m_task_handle;
    bool m_running;
};
