/**
 * @file dev_console.cpp
 * @brief Development Console & Interactive CLI Implementation
 */

#include "dev_console.h"
#include <cstdio>
#include <cstring>
#include "esp_log.h"
#include "nlu/normalizer/vietnamese_normalizer.h"
#include "nlu/intent/intent_parser.h"
#include "nlu/entity/entity_extractor.h"

static const char* TAG = "DEV_CONSOLE";

DevConsole::DevConsole(
    std::shared_ptr<ASREngine> asr,
    std::shared_ptr<AudioManager> audio_mgr,
    std::shared_ptr<ContextManager> context_mgr,
    std::shared_ptr<ActionBoxRegistry> registry,
    std::shared_ptr<CommandRouter> router,
    std::shared_ptr<RoomManager> room_mgr
) : m_asr(asr),
    m_audio_mgr(audio_mgr),
    m_context_mgr(context_mgr),
    m_registry(registry),
    m_router(router),
    m_room_mgr(room_mgr),
    m_task_handle(nullptr),
    m_running(false) {
}

DevConsole::~DevConsole() {
    m_running = false;
    if (m_task_handle) {
        vTaskDelay(pdMS_TO_TICKS(50));
        m_task_handle = nullptr;
    }
}

bool DevConsole::init() {
    m_running = true;
    BaseType_t res = xTaskCreatePinnedToCore(
        consoleTask,
        "dev_console",
        TASK_STACK_CONSOLE,
        this,
        TASK_PRIO_CONSOLE,
        &m_task_handle,
        0
    );
    return (res == pdPASS);
}

void DevConsole::consoleTask(void* pvParameters) {
    auto* self = static_cast<DevConsole*>(pvParameters);
    self->runConsoleLoop();
    vTaskDelete(NULL);
}

void DevConsole::runConsoleLoop() {
    ESP_LOGI(TAG, "SubBox Dev Console ready. Type 'HELP' for commands.");
    char line_buf[256];
    size_t idx = 0;

    while (m_running) {
        int c = getchar();
        if (c != EOF && c != 0xFF) {
            if (c == '\r' || c == '\n') {
                if (idx > 0) {
                    line_buf[idx] = '\0';
                    processLine(line_buf);
                    idx = 0;
                }
            } else if (c == '\b' || c == 127) {
                if (idx > 0) {
                    idx--;
                    printf("\b \b");
                }
            } else if (idx < sizeof(line_buf) - 1) {
                line_buf[idx++] = static_cast<char>(c);
                putchar(c);
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(50));
        }
    }
}

void DevConsole::processLine(const std::string& line) {
    if (line.empty()) return;
    printf("\n");

    if (line.rfind("CMD ", 0) == 0) {
        std::string raw_phrase = line.substr(4);
        std::string norm = VietnameseNormalizer::normalize(raw_phrase);
        IntentType intent = IntentParser::parse(norm);
        ParsedEntities entities = EntityExtractor::extract(norm);
        CommandResolution res = m_context_mgr->resolve(norm, "CLI_DEV", intent, entities);
        ExecutionResult exec = m_router->route(res);

        printf("--------------------------------------------------\n");
        printf("[CMD DIRECT INJECTION]\n");
        printf("  Raw Input   : %s\n", raw_phrase.c_str());
        printf("  Normalized  : %s\n", norm.c_str());
        printf("  Intent      : %s\n", intentToString(res.intent));
        printf("  Device      : %s\n", deviceToString(res.device));
        printf("  Target Room : %s\n", roomToString(res.target_room));
        printf("  Speaker Room: %s\n", roomToString(res.speaker_room));
        printf("  Success     : %s\n", exec.success ? "YES" : "NO");
        printf("  Response    : %s\n", exec.response_text.c_str());
        printf("--------------------------------------------------\n");
    }
    else if (line.rfind("SAY ", 0) == 0) {
        std::string phrase = line.substr(4);
        printf(">>> Processing Spoken Command: \"%s\"\n", phrase.c_str());
        processLine("CMD " + phrase);
    }
    else if (line == "STATUS") {
        printf("==================== SUBBOX SYSTEM STATUS ====================\n");
        printf("  SubBox ID    : %s\n", m_room_mgr->getSubBoxId().c_str());
        printf("  Local Room   : %s (%s)\n", m_room_mgr->getRoomName().c_str(), roomToString(m_room_mgr->getRoomType()));
        printf("  Active Audio : %s\n", m_audio_mgr->getActiveSourceNodeId().empty() ? "[IDLE]" : m_audio_mgr->getActiveSourceNodeId().c_str());
        printf("  Last Audio In: %s\n", m_audio_mgr->getLastInputNodeId().c_str());

        auto nodes = m_registry->getAllNodes();
        printf("  Registered ActionBoxes (%u):\n", (unsigned)nodes.size());
        for (const auto& n : nodes) {
            printf("    * %s: Room=%s, Dev=%s, Ch=%u, Relay=%s, Current=%lu mA, Online=%s\n",
                   n.node_id.c_str(), roomToString(n.room), deviceToString(n.device), n.channel,
                   n.relay_state ? "ON" : "OFF", (unsigned long)n.current_ma, n.is_online ? "YES" : "NO");
        }
        printf("==============================================================\n");
    }
    else if (line == "TEST_NLU") {
        runNluUnitTests();
    }
    else if (line == "HELP") {
        printf("SubBox CLI Available Commands:\n");
        printf("  CMD <text>  - Bypass ASR and test NLU/routing directly (e.g. 'CMD bật đèn phòng khách')\n");
        printf("  SAY <text>  - Inject speech transcript into ASR engine\n");
        printf("  STATUS      - Display room, audio, and ActionBox registry snapshot\n");
        printf("  TEST_NLU    - Execute comprehensive Vietnamese NLU unit test suite\n");
        printf("  HELP        - Display this menu\n");
    } else {
        printf("Unknown command. Type 'HELP' for available options.\n");
    }
}

void DevConsole::runNluUnitTests() {
    printf("==============================================================\n");
    printf("          RUNNING VIETNAMESE NLU & CONTEXT UNIT TESTS         \n");
    printf("==============================================================\n");

    struct TestCase {
        const char* phrase;
        IntentType expected_intent;
        DeviceType expected_device;
        RoomType expected_room;
    };

    TestCase cases[] = {
        {"bật đèn phòng khách", IntentType::TURN_ON, DeviceType::LIGHT, RoomType::LIVING_ROOM},
        {"tắt quạt phòng ngủ", IntentType::TURN_OFF, DeviceType::FAN, RoomType::BEDROOM},
        {"bật điều hòa", IntentType::TURN_ON, DeviceType::AIR_CONDITIONER, RoomType::LIVING_ROOM}, // Inherits local room
        {"chỉnh nhiệt độ 26 độ", IntentType::SET_TEMPERATURE, DeviceType::AIR_CONDITIONER, RoomType::LIVING_ROOM},
        {"bật đèn phòng bếp", IntentType::TURN_ON, DeviceType::LIGHT, RoomType::KITCHEN}, // Cross-room
        {"nếu nhiệt độ phòng khách trên 30 độ thì bật quạt", IntentType::COMPLEX, DeviceType::NONE, RoomType::LIVING_ROOM},
        {"công suất tiêu thụ của đèn", IntentType::QUERY_POWER, DeviceType::LIGHT, RoomType::LIVING_ROOM},
        {"kiểm tra trạng thái quạt", IntentType::QUERY_STATE, DeviceType::FAN, RoomType::LIVING_ROOM}
    };

    int passed = 0;
    int total = sizeof(cases) / sizeof(cases[0]);

    for (int i = 0; i < total; ++i) {
        std::string norm = VietnameseNormalizer::normalize(cases[i].phrase);
        IntentType intent = IntentParser::parse(norm);
        ParsedEntities entities = EntityExtractor::extract(norm);
        CommandResolution res = m_context_mgr->resolve(norm, "TEST_SUITE", intent, entities);

        bool intent_ok = (res.intent == cases[i].expected_intent);
        bool device_ok = (cases[i].expected_device == DeviceType::NONE) || (res.device == cases[i].expected_device);
        bool room_ok   = (res.target_room == cases[i].expected_room);

        bool success = (intent_ok && device_ok && room_ok);
        if (success) {
            passed++;
            printf("  [PASS] Test %d: \"%s\"\n", i + 1, cases[i].phrase);
        } else {
            printf("  [FAIL] Test %d: \"%s\"\n", i + 1, cases[i].phrase);
            printf("         Expected Intent=%s, Got=%s\n", intentToString(cases[i].expected_intent), intentToString(res.intent));
            printf("         Expected Device=%s, Got=%s\n", deviceToString(cases[i].expected_device), deviceToString(res.device));
            printf("         Expected Room=%s,   Got=%s\n", roomToString(cases[i].expected_room), roomToString(res.target_room));
        }
    }

    // Pronoun Reference Context Test
    printf("--- Testing Pronoun Context Resolution (\"tắt nó\") ---\n");
    // Seed context with a fan command
    std::string seed = VietnameseNormalizer::normalize("bật quạt phòng ngủ");
    CommandResolution seed_res = m_context_mgr->resolve(seed, "TEST", IntentParser::parse(seed), EntityExtractor::extract(seed));
    m_context_mgr->commitResolution(seed_res);

    // Follow up with "tắt nó"
    std::string follow_up = VietnameseNormalizer::normalize("tắt nó");
    CommandResolution follow_res = m_context_mgr->resolve(follow_up, "TEST", IntentParser::parse(follow_up), EntityExtractor::extract(follow_up));

    if (follow_res.intent == IntentType::TURN_OFF &&
        follow_res.device == DeviceType::FAN &&
        follow_res.target_room == RoomType::BEDROOM &&
        follow_res.resolved_via_context) {
        passed++;
        printf("  [PASS] Pronoun Resolution: \"tắt nó\" -> TURN_OFF FAN in BEDROOM (Context Active)\n");
    } else {
        printf("  [FAIL] Pronoun Resolution failed! Device=%s, Room=%s\n",
               deviceToString(follow_res.device), roomToString(follow_res.target_room));
    }
    total++;

    printf("==============================================================\n");
    printf("   NLU Test Suite Summary: %d / %d Tests Passed (%.1f%%)\n",
           passed, total, (float)passed * 100.0f / (float)total);
    printf("==============================================================\n");
}
