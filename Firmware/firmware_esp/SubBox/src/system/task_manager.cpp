/**
 * @file task_manager.cpp
 * @brief FreeRTOS Task Architecture and Queue Coordinator Implementation
 */

#include "task_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nlu/normalizer/vietnamese_normalizer.h"
#include "nlu/intent/intent_parser.h"
#include "nlu/entity/entity_extractor.h"
#include "cJSON.h"
#include "subbox_led.h"

static const char* TAG = "TASK_MGR";

TaskManager::TaskManager(
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
) : m_audio_mgr(audio_mgr),
    m_transport(transport),
    m_audio_router(audio_router),
    m_tts_mgr(tts_mgr),
    m_context_mgr(context_mgr),
    m_registry(registry),
    m_router(router),
    m_rules(rules),
    m_room_mgr(room_mgr),
    m_mqtt(mqtt),
    m_utterance_queue(nullptr),
    m_command_queue(nullptr),
    m_response_queue(nullptr),
    m_h_audio_mgr(nullptr),
    m_h_nlu(nullptr),
    m_h_cmd(nullptr),
    m_h_tx(nullptr),
    m_h_dev_mgr(nullptr),
    m_h_telemetry(nullptr),
    m_h_system(nullptr) {
}

TaskManager::~TaskManager() {
    if (m_utterance_queue) vQueueDelete(m_utterance_queue);
    if (m_command_queue) vQueueDelete(m_command_queue);
    if (m_response_queue) vQueueDelete(m_response_queue);
}

bool TaskManager::init() {
    ESP_LOGI(TAG, "Creating SubBox FreeRTOS queues and task architecture...");

    m_utterance_queue = xQueueCreate(QUEUE_CAP_ASR_REQUESTS, sizeof(UtteranceQueueItem));
    m_command_queue   = xQueueCreate(QUEUE_CAP_COMMAND_REQUESTS, sizeof(CommandQueueItem));
    m_response_queue  = xQueueCreate(QUEUE_CAP_RESPONSE_AUDIO, sizeof(ResponseQueueItem));

    if (!m_utterance_queue || !m_command_queue || !m_response_queue) {
        ESP_LOGE(TAG, "Failed to allocate FreeRTOS inter-task communication queues!");
        return false;
    }

    if (m_mqtt) {
        m_mqtt->registerCommandCallback([this](const std::string&, const std::string& payload) {
            CommandQueueItem item{};
            if (payload.size() >= sizeof(item.gateway_command)) return;
            strcpy(item.gateway_command, payload.c_str());
            xQueueSend(m_command_queue, &item, 0);
        });
        m_mqtt->registerVoiceResponseCallback([this](const std::string&, const std::string& payload, const uint8_t*, size_t) {
            cJSON* root = cJSON_Parse(payload.c_str());
            if (!root) return;
            const cJSON* id = cJSON_GetObjectItem(root, "origin_node");
            const cJSON* text = cJSON_GetObjectItem(root, "voice_reply");
            if (cJSON_IsString(id) && cJSON_IsString(text)) queueResponse(id->valuestring, text->valuestring);
            cJSON_Delete(root);
        });
    }

    // Connect Audio Manager output to utterance queue
    m_transport->registerJsonCallback([this](const std::string& json) {
        cJSON* root = cJSON_Parse(json.c_str());
        if (!root) return;
        const cJSON* id = cJSON_GetObjectItem(root, "node_id");
        const cJSON* channels = cJSON_GetObjectItem(root, "channels");
        const cJSON* uid = cJSON_GetObjectItem(root, "hardware_uid");
        const cJSON* revision = cJSON_GetObjectItem(root, "config_version");
        if (cJSON_IsString(id) && cJSON_IsString(uid) && cJSON_IsNumber(revision) && cJSON_IsArray(channels)) {
            subbox_led_peer_seen();
            const cJSON* ch;
            cJSON_ArrayForEach(ch, channels) {
                const cJSON* number = cJSON_GetObjectItem(ch, "channel");
                const cJSON* state = cJSON_GetObjectItem(ch, "state");
                if (!cJSON_IsNumber(number) || !cJSON_IsString(state) ||
                    number->valueint < 1 || number->valueint > 2) continue;
                std::string key = id->valuestring;
                if (number->valueint != 1) key += "_CH" + std::to_string(number->valueint);
                ActionBoxNode node{};
                if (!m_registry->findNodeById(key, node)) {
                    node.node_id = key;
                    node.room = m_context_mgr->getSubboxRoom();
                    node.channel = number->valueint;
                    node.device = node.channel == 1 ? DeviceType::LIGHT : DeviceType::FAN;
                    node.has_relay = node.has_current_sensor = node.has_microphone = true;
                }
                node.hardware_uid = uid->valuestring;
                node.config_version = static_cast<uint32_t>(revision->valuedouble);
                const cJSON* label = cJSON_GetObjectItem(ch, "label");
                node.label = cJSON_IsString(label) ? label->valuestring : key;
                m_registry->registerNode(node);
                auto value = [ch](const char* name) {
                    const cJSON* field = cJSON_GetObjectItem(ch, name);
                    return cJSON_IsNumber(field) ? field->valueint : 0;
                };
                m_registry->updateTelemetry(key, strcmp(state->valuestring, "ON") == 0,
                    value("current_ma"), value("voltage_v"), value("power_w"), value("fault") != 0);
            }
        }
        if (m_mqtt) m_mqtt->publishEvent("actionbox", json);
        cJSON_Delete(root);
    });
    m_audio_mgr->registerUtteranceCallback([this](const std::string& node_id, const std::string& text) {
        this->queueUtterance(node_id, text);
    });

    // Spawn tasks across Dual-Core ESP32-S3:
    // Core 1 (DSP / AI / Audio): audio_manager, nlu, audio_tx
    // Core 0 (Network / System): command, device_manager, telemetry, system

    xTaskCreatePinnedToCore(audioManagerTask, "audio_mgr_task", TASK_STACK_AUDIO_MANAGER, this, TASK_PRIO_AUDIO_MANAGER, &m_h_audio_mgr, 1);
    xTaskCreatePinnedToCore(nluTask,          "nlu_task",       TASK_STACK_NLU,           this, TASK_PRIO_NLU,           &m_h_nlu,       1);
    xTaskCreatePinnedToCore(audioTxTask,      "audio_tx_task",  TASK_STACK_AUDIO_TX,      this, TASK_PRIO_AUDIO_TX,      &m_h_tx,        1);

    xTaskCreatePinnedToCore(commandTask,      "cmd_task",       TASK_STACK_COMMAND,       this, TASK_PRIO_COMMAND,       &m_h_cmd,       0);
    xTaskCreatePinnedToCore(deviceManagerTask,"dev_mgr_task",   TASK_STACK_DEVICE_MGR,   this, TASK_PRIO_DEVICE_MGR,   &m_h_dev_mgr,   0);
    xTaskCreatePinnedToCore(telemetryTask,    "telemetry_task", TASK_STACK_TELEMETRY,    this, TASK_PRIO_TELEMETRY,    &m_h_telemetry, 0);
    xTaskCreatePinnedToCore(systemTask,       "system_task",    TASK_STACK_CONSOLE,      this, 1,                       &m_h_system,    0);

    ESP_LOGI(TAG, "All SubBox FreeRTOS tasks spawned successfully.");
    return true;
}

bool TaskManager::queueUtterance(const std::string& origin_node_id, const std::string& text) {
    if (!m_utterance_queue || origin_node_id.size() >= sizeof(UtteranceQueueItem::origin_node_id) ||
        text.size() >= sizeof(UtteranceQueueItem::text)) return false;
    UtteranceQueueItem item = {};
    strncpy(item.origin_node_id, origin_node_id.c_str(), sizeof(item.origin_node_id) - 1);
    strncpy(item.text, text.c_str(), sizeof(item.text) - 1);
    return (xQueueSend(m_utterance_queue, &item, pdMS_TO_TICKS(50)) == pdTRUE);
}

bool TaskManager::queueCommand(const CommandResolution& res) {
    if (!m_command_queue) return false;
    CommandQueueItem item{};
    if (res.origin_node_id.size() >= sizeof(item.origin_node_id) ||
        res.error_reason.size() >= sizeof(item.error_reason) || res.raw_text.size() >= sizeof(item.raw_text)) return false;
    item.intent = res.intent;
    item.device = res.device;
    item.target_room = res.target_room;
    item.speaker_room = res.speaker_room;
    strcpy(item.origin_node_id, res.origin_node_id.c_str());
    item.has_value = res.has_value;
    item.value = res.value;
    item.resolved_via_context = res.resolved_via_context;
    item.is_valid = res.is_valid;
    strcpy(item.error_reason, res.error_reason.c_str());
    strcpy(item.raw_text, res.raw_text.c_str());
    return (xQueueSend(m_command_queue, &item, pdMS_TO_TICKS(50)) == pdTRUE);
}

bool TaskManager::queueResponse(const std::string& target_node_id, const std::string& text) {
    if (!m_response_queue) return false;
    ResponseQueueItem item = {};
    strncpy(item.target_node_id, target_node_id.c_str(), sizeof(item.target_node_id) - 1);
    strncpy(item.text, text.c_str(), sizeof(item.text) - 1);
    return (xQueueSend(m_response_queue, &item, pdMS_TO_TICKS(50)) == pdTRUE);
}

void TaskManager::audioManagerTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "audio_manager_task started on Core 1.");

    while (1) {
        self->m_audio_mgr->process();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void TaskManager::nluTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "nlu_task started on Core 1.");
    UtteranceQueueItem item;

    while (1) {
        if (xQueueReceive(self->m_utterance_queue, &item, portMAX_DELAY) == pdTRUE) {
            ESP_LOGI(TAG, "🗣️ [NLU RAW INPUT] Text: \"%s\" | Origin: %s", item.text, item.origin_node_id);

            // 1. Vietnamese Text Normalization
            std::string normalized = VietnameseNormalizer::normalize(item.text);
            ESP_LOGI(TAG, "📝 [NLU NORMALIZED] Text: \"%s\"", normalized.c_str());

            // 2. Intent Parsing
            IntentType intent = IntentParser::parse(normalized);

            // 3. Entity Extraction
            ParsedEntities entities = EntityExtractor::extract(normalized);

            // 4. Context & Pronoun Resolution
            CommandResolution res = self->m_context_mgr->resolve(normalized, item.origin_node_id, intent, entities);
            ESP_LOGI(TAG, "🎯 [NLU RESOLUTION] Intent: %s | Device: %s | TargetRoom: %s | SpeakerRoom: %s (Valid=%d)",
                     intentToString(res.intent), deviceToString(res.device),
                     roomToString(res.target_room), roomToString(res.speaker_room), res.is_valid);

            // 5. Forward to Command Execution Task
            self->queueCommand(res);
        }
    }
}

void TaskManager::commandTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "command_task started on Core 0.");
    CommandQueueItem item;

    while (1) {
        if (xQueueReceive(self->m_command_queue, &item, portMAX_DELAY) == pdTRUE) {
            if (item.gateway_command[0]) {
                cJSON* root = cJSON_Parse(item.gateway_command);
                if (root) {
                    const cJSON* id = cJSON_GetObjectItem(root, "node_id");
                    ActionBoxNode node{};
                    if (cJSON_IsString(id) && self->m_registry->findNodeById(id->valuestring, node))
                        self->m_transport->sendCommand(id->valuestring, item.gateway_command);
                    cJSON_Delete(root);
                }
                continue;
            }
            CommandResolution res{item.intent, item.device, item.target_room,
                item.speaker_room, item.origin_node_id, item.has_value, item.value,
                item.resolved_via_context, item.is_valid, item.error_reason, item.raw_text};
            ExecutionResult exec = self->m_router->route(res);

            // If forwarded to Pi4, publish via MQTT
            if (exec.forwarded_to_pi4 && self->m_mqtt) {
                if (!self->m_mqtt->publishVoiceRequest(res.origin_node_id, res.raw_text))
                    exec.response_text = "Không kết nối được máy chủ xử lý.";
            }

            // Queue response audio / chime to ActionBox speaker only if speaker hardware exists
            ActionBoxNode target_node;
            bool has_spk = (self->m_registry->findNodeById(res.origin_node_id, target_node) && target_node.has_speaker);
            if (!exec.response_text.empty() && has_spk) {
                self->queueResponse(res.origin_node_id, exec.response_text);
            }
        }
    }
}

void TaskManager::audioTxTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "audio_tx_task started on Core 1.");
    ResponseQueueItem item;

    while (1) {
        if (xQueueReceive(self->m_response_queue, &item, portMAX_DELAY) == pdTRUE) {
            ESP_LOGI(TAG, "Audio TX: Delivering response to ActionBox %s -> \"%s\"",
                     item.target_node_id, item.text);

            self->m_tts_mgr->speakResponse(item.target_node_id, item.text);
        }
    }
}

void TaskManager::deviceManagerTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "device_manager_task started on Core 0.");

    while (1) {
        // Evaluate temperature rules only when a real sensor measurement is available.

        // Check ActionBox heartbeats
        self->m_registry->checkTimeouts(30000);

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void TaskManager::telemetryTask(void* pvParameters) {
    auto* self = static_cast<TaskManager*>(pvParameters);
    ESP_LOGI(TAG, "telemetry_task started on Core 0.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(5000));

        if (self->m_mqtt && self->m_mqtt->isConnected()) {
            std::string state_json = "{\"subbox_id\":\"" + self->m_room_mgr->getSubBoxId() +
                                     "\",\"room\":\"" + self->m_room_mgr->getRoomName() +
                                     "\",\"uptime_s\":" + std::to_string((uint32_t)(esp_timer_get_time() / 1000000ULL)) +
                                     ",\"status\":\"ONLINE\"}";
            self->m_mqtt->publishState(state_json);
        }
    }
}

void TaskManager::systemTask(void* pvParameters) {
    ESP_LOGI(TAG, "system_task active.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(15000));
        ESP_LOGI(TAG, "SubBox Health: Free SRAM=%lu KB, Free PSRAM=%lu KB",
                 (unsigned long)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
                 (unsigned long)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
    }
}
