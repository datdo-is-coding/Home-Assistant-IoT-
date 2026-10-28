#include <stdio.h>
#include <string.h>
#include <memory>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_sntp.h"
#include "esp_netif.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_timer.h"
#include <ctime>

#include "config/subbox_config.h"
#include "config/board_pins.h"
#include "storage/nvs_manager.h"
#include "room/room_manager.h"
#include "audio/audio_transport/udp_audio_transport.h"
#include "audio/audio_transport/espnow_audio_transport.h"
#include "audio/audio_buffer/audio_ring_buffer.h"
#include "audio/vad/energy_vad.h"
#include "audio/asr/ws_asr.h"
#include "audio/kws/local_kws.h"
#include "audio/kws/kws_control.h"
#include "audio/audio_manager/audio_manager.h"
#include "audio/audio_output/audio_output_router.h"
#include "audio/audio_output/sound_player.h"
#include "tts/tts_manager.h"
#include "nlu/context/context_manager.h"
#include "actionbox/registry/actionbox_registry.h"
#include "actionbox/router/command_router.h"
#include "rules/rule_engine.h"
#include "mqtt/subbox_mqtt_client.h"
#include "system/task_manager.h"
#include "system/dev_console.h"
#include "hc_runtime.h"
#include "hc_ota.h"
#include "hc_factory.h"
#include "hc_provisioning.h"
static MqttClient* hc_mqtt=nullptr;
static std::shared_ptr<CoreKwsControl> core_kws;
static bool hc_application(uint8_t type,const uint8_t* data,size_t size) {
    return type==HC_ROOM_SNAPSHOT && core_kws && core_kws->configure(data,size);
}
static bool hc_uplink(const uint8_t* data,size_t length) { return hc_mqtt && hc_mqtt->publishCore(data,length); }

static const char *TAG = "SUBBOX_MAIN";

#include "freertos/event_groups.h"
#include "system/wifi_provisioning.h"
#include "system/subbox_led.h"
#include "system/gateway_discovery.h"

static int s_wifi_retry_count = 0;
static EventGroupHandle_t s_wifi_event_group = nullptr;
static const int WIFI_CONNECTED_BIT = BIT0;

static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                               int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Wi-Fi Station started, connecting to AP '%s'...", (const char*)arg);
        if (((const char*)arg)[0]) esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        subbox_led_set_wifi_connected(false);
        subbox_led_set_mqtt_connected(false);
        if (s_wifi_event_group) {
            xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        }
        s_wifi_retry_count++;
        ESP_LOGW(TAG, "Wi-Fi disconnected (attempt %d/5)...", s_wifi_retry_count);
        if (s_wifi_retry_count == 5 && !hc_provisioning_active()) {
            ESP_LOGW(TAG, "Wi-Fi connection failed 5 times; automatically starting SoftAP provisioning...");
            esp_err_t setup_err = hc_provisioning_start(true);
            if (setup_err != ESP_OK) {
                ESP_LOGW(TAG, "Setup unavailable (%s); continuing Wi-Fi recovery", esp_err_to_name(setup_err));
            }
        }
        // AP setup, including a failed/expired window, must not stop STA recovery.
        if (((const char*)arg)[0]) esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        s_wifi_retry_count = 0;
        ip_event_got_ip_t* event = (ip_event_got_ip_t*)event_data;
        ESP_LOGI(TAG, "SubBox Wi-Fi Connected! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        subbox_led_set_wifi_connected(true);
        if (s_wifi_event_group) {
            xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        }
        if (!esp_sntp_enabled()) {
            esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
            esp_sntp_setservername(0, "pool.ntp.org");
            esp_sntp_init();
        }
    }
}

static void print_banner(const SubBoxPersistentConfig& cfg) {
    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);

    uint32_t flash_size = 0;
    esp_flash_get_size(NULL, &flash_size);

    size_t free_sram  = heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024;
    size_t free_psram = heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024;

    ESP_LOGI(TAG, "===================");
    ESP_LOGI(TAG, "  SICHOME — SUBBOX");
    ESP_LOGI(TAG, "===================");
    ESP_LOGI(TAG, "  Firmware Name    : %s", SUBBOX_FW_NAME);
    ESP_LOGI(TAG, "  Firmware Version : %s", SUBBOX_FW_VERSION_STR);
    ESP_LOGI(TAG, "  Silicon Model    : ESP32-S3 (Rev %d, %d Cores)", chip_info.revision, chip_info.cores);
    ESP_LOGI(TAG, "  Flash Size       : %lu MB", (unsigned long)(flash_size / (1024 * 1024)));
    ESP_LOGI(TAG, "  PSRAM Available  : %u KB (Total: 16 MB Octal)", (unsigned)free_psram);
    ESP_LOGI(TAG, "  Internal SRAM    : %u KB", (unsigned)free_sram);
    ESP_LOGI(TAG, "  SubBox ID        : %s", cfg.subbox_id);
    ESP_LOGI(TAG, "  Assigned Room    : %s (%s)", cfg.room_name, roomToString(cfg.room_type));
    ESP_LOGI(TAG, "  Real ASR Engine  : Local Vietnamese KWS (SubBox)");
    ESP_LOGI(TAG, "  Audio Capacity   : Up to %d ActionBoxes per Room",
             SUBBOX_MAX_ACTIONBOXES_PER_ROOM);
    ESP_LOGI(TAG, "===============================================================");
}

static void wifi_init_sta(const char* ssid, const char* pass) {
    if (!s_wifi_event_group) {
        s_wifi_event_group = xEventGroupCreate();
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        (void*)ssid,
                                                        NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));

    wifi_config_t wifi_config = {};

    memcpy(wifi_config.sta.ssid, ssid, strnlen(ssid, sizeof(wifi_config.sta.ssid)));
    memcpy(wifi_config.sta.password, pass, strnlen(pass, sizeof(wifi_config.sta.password)));
    wifi_config.sta.threshold.authmode = pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    esp_wifi_set_ps(WIFI_PS_NONE);

    ESP_LOGI(TAG, "Wi-Fi Station started (SSID: %s).", ssid);
}

extern "C" void app_main(void) {

    subbox_led_init();

    ESP_ERROR_CHECK(NVSManager::init());
    ESP_ERROR_CHECK(hc_factory_apply());

    SubBoxPersistentConfig cfg;
    NVSManager::loadConfig(cfg);

    size_t free_psram = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "Audio relay PSRAM available: %u KB; local ASR/NLU disabled", (unsigned)(free_psram / 1024));

    print_banner(cfg);

    hc_provisioned_config enrollment{};
    esp_err_t enrollment_result=hc_provisioning_load(&enrollment);
    if(enrollment_result==ESP_OK && enrollment.subbox){
        // Keep the MAC-derived SB identity used by the Gateway, audio server and
        // KWS topics. The numeric hc_core node id is used only on hc/v1 topics.
        bool first_boot = (cfg.wifi_ssid[0] == 0);
        if (first_boot) {
            snprintf(cfg.wifi_ssid,sizeof(cfg.wifi_ssid),"%s",enrollment.wifi_ssid);
            snprintf(cfg.wifi_pass,sizeof(cfg.wifi_pass),"%s",enrollment.wifi_password);
            snprintf(cfg.mqtt_broker_uri,sizeof(cfg.mqtt_broker_uri),"%s",enrollment.mqtt_uri);
        }
        if (enrollment.room_id[0]) {
            snprintf(cfg.room_name, sizeof(cfg.room_name), "%s", enrollment.room_id);
        }
        if (cfg.ws_gateway_uri[0] == 0 && cfg.mqtt_broker_uri[0] != 0) {
            const char* proto = strstr(cfg.mqtt_broker_uri, "://");
            const char* host_start = proto ? proto + 3 : cfg.mqtt_broker_uri;
            char host[64] = {0};
            size_t hi = 0;
            while (host_start[hi] && host_start[hi] != ':' && host_start[hi] != '/' && hi < sizeof(host) - 1) {
                host[hi] = host_start[hi];
                hi++;
            }
            host[hi] = 0;
            if (hi > 0) {
                snprintf(cfg.ws_gateway_uri, sizeof(cfg.ws_gateway_uri), "ws://%s:8765/ws/audio", host);
            }
        }
        if (first_boot) {
            NVSManager::saveConfig(cfg);
        }
    }else if(cfg.wifi_ssid[0]==0){
        cfg.wifi_ssid[0]=cfg.wifi_pass[0]=cfg.mqtt_broker_uri[0]=0;
        ESP_LOGW(TAG,"Blank NVS / First setup detected: opening secure 180s provisioning window");
        hc_provisioning_start(true);
    }else{
        ESP_LOGI(TAG,"Factory enrollment absent: continuing with loaded NVS credentials (SSID '%s')",cfg.wifi_ssid);
    }
    memset(&enrollment,0,sizeof(enrollment));
    wifi_init_sta(cfg.wifi_ssid,cfg.wifi_pass);
    ESP_ERROR_CHECK(hc_provisioning_button_init(true));

    if (SoundPlayer::instance().init() == ESP_OK) {
        SoundPlayer::instance().play(SoundType::BOOTUP);
    }

    if (cfg.wifi_ssid[0] != '\0') {
        ESP_LOGI(TAG, "Waiting for Wi-Fi connection to discover Gateway...");
        EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdFALSE, pdMS_TO_TICKS(8000));
        if (bits & WIFI_CONNECTED_BIT) {
            ESP_LOGI(TAG, "Wi-Fi connected. Performing Gateway Discovery...");
            char discovered_ip[64] = {0};
            uint16_t ws_port = 8765;
            uint16_t mqtt_port = 8883;
            if (gateway_discover(discovered_ip, sizeof(discovered_ip), &ws_port, &mqtt_port, 3000)) {
                ESP_LOGI(TAG, "Gateway Discovered: IP %s (WS: %u, MQTT: %u)", discovered_ip, ws_port, mqtt_port);

                char new_ws_uri[128];
                char new_mqtt_uri[128];
                snprintf(new_ws_uri, sizeof(new_ws_uri), "ws://%s:%u/ws/audio",
                         discovered_ip, ws_port ? ws_port : 8765);
                if (mqtt_port == 8883) {
                    snprintf(new_mqtt_uri, sizeof(new_mqtt_uri), "mqtts://%s:%u",
                             discovered_ip, mqtt_port);
                } else {
                    // A local broker may use plain MQTT; devices still require TLS.
                    snprintf(new_mqtt_uri, sizeof(new_mqtt_uri), "%s", cfg.mqtt_broker_uri);
                    ESP_LOGW(TAG, "Discovery did not advertise MQTT TLS; retaining provisioned broker");
                }

                bool uri_changed = false;
                if (strcmp(cfg.ws_gateway_uri, new_ws_uri) != 0) {
                    strncpy(cfg.ws_gateway_uri, new_ws_uri, sizeof(cfg.ws_gateway_uri) - 1);
                    cfg.ws_gateway_uri[sizeof(cfg.ws_gateway_uri) - 1] = '\0';
                    uri_changed = true;
                }
                if (strcmp(cfg.mqtt_broker_uri, new_mqtt_uri) != 0) {
                    strncpy(cfg.mqtt_broker_uri, new_mqtt_uri, sizeof(cfg.mqtt_broker_uri) - 1);
                    cfg.mqtt_broker_uri[sizeof(cfg.mqtt_broker_uri) - 1] = '\0';
                    uri_changed = true;
                }
                if (uri_changed) {
                    NVSManager::saveConfig(cfg);
                    ESP_LOGI(TAG, "Gateway URIs updated & saved to NVS -> WS: %s, MQTT: %s",
                             cfg.ws_gateway_uri, cfg.mqtt_broker_uri);
                } else {
                    ESP_LOGI(TAG, "Configured URIs already matched discovered Gateway IP: %s", discovered_ip);
                }
            } else {
                ESP_LOGW(TAG, "Gateway discovery timed out; continuing with existing URIs.");
            }
        } else {
            ESP_LOGW(TAG, "Wi-Fi connection timed out waiting for gateway discovery; continuing.");
        }
    }

    auto room_mgr = std::make_shared<RoomManager>(cfg.subbox_id, cfg.room_type);
    room_mgr->setRoomName(cfg.room_name);

    auto vad = std::make_shared<EnergyVAD>(
        SUBBOX_VAD_INITIAL_ENERGY_THRESH,
        SUBBOX_VAD_SILENCE_TIMEOUT_MS,
        SUBBOX_VAD_SPEECH_ONSET_FRAMES,
        SUBBOX_VAD_MAX_SPEECH_DURATION_MS
    );

    auto local_kws = std::make_shared<LocalKws>();
    if (!local_kws->init()) subbox_led_set_error(true);

    // The WebSocket client is kept only for downstream TTS playback. Microphone
    // PCM never reaches it; recognition runs on local_kws above.
    auto asr = std::make_shared<WsASR>(cfg.ws_gateway_uri, cfg.subbox_id);
    if (!asr->init()) ESP_LOGE(TAG, "Pi4 playback unavailable; local KWS control continues without spoken replies");

    auto audio_mgr = std::make_shared<AudioManager>(vad, local_kws);
    audio_mgr->init();

    auto transport = std::make_shared<EspNowAudioTransport>();

    auto audio_router = std::make_shared<AudioOutputRouter>(transport);

    auto tts_mgr = std::make_shared<TTSManager>(audio_router);
    tts_mgr->init();

    auto registry = std::make_shared<ActionBoxRegistry>();

    auto context_mgr = std::make_shared<ContextManager>(cfg.room_type);

    auto command_router = std::make_shared<CommandRouter>(registry, context_mgr, audio_router, transport);

    auto rule_engine = std::make_shared<RuleEngine>(registry);
    rule_engine->init();

    auto mqtt = std::make_shared<MqttClient>(cfg.mqtt_broker_uri, cfg.subbox_id);
    command_router->setMqttClient(mqtt);

    const auto publish_kws = [mqtt](const std::string& kind, const std::string& data) {
        if (kind == "kws_result") return mqtt->publishEvent("kws_result", data);
        if (kind == "kws_config") return mqtt->publishEvent("kws_config", data);
        const std::string command_prefix = "kws_command/";
        const std::string ack_prefix = "kws_ack/";
        if (kind.rfind(command_prefix, 0) == 0) {
            return mqtt->publishRaw("home/kws/" + mqtt->nodeId() + "/" + kind.substr(command_prefix.size()) + "/command", data);
        }
        if (kind.rfind(ack_prefix, 0) == 0) {
            return mqtt->publishRaw("home/kws/" + mqtt->nodeId() + "/" + kind.substr(ack_prefix.size()) + "/ack", data);
        }
        return false;
    };
    const auto trusted_peer = [registry](const KwsPeer& peer) {
        for (const auto& node : registry->getAllNodes()) {
            const bool same_node = node.node_id == peer.node_id ||
                node.node_id.rfind(peer.node_id + "_CH", 0) == 0;
            if (!same_node || node.hardware_uid != peer.hardware_uid ||
                node.config_version != peer.config_version) continue;
            if (node.owner_epoch != 0 && peer.owner_epoch != 0 && node.owner_epoch != peer.owner_epoch) {
                return false;
            }
            return true;
        }
        return false;
    };
    const auto send_command = [transport](const KwsPeer& peer, const std::string& command, std::string& ack) {
        return transport->sendCommand(peer.node_id.c_str(), command, &ack);
    };
    const auto save_kws = [](const std::string& snapshot) {
        return NVSManager::saveKwsSnapshot(snapshot) == ESP_OK;
    };
    const auto listen_followup = [transport](const KwsPeer& peer, uint32_t session, uint32_t request) {
        cJSON* root = cJSON_CreateObject();
        if (!root) return false;
        cJSON_AddStringToObject(root, "node_id", peer.node_id.c_str());
        cJSON_AddStringToObject(root, "subbox_id", peer.subbox_id.c_str());
        cJSON_AddStringToObject(root, "hardware_uid", peer.hardware_uid.c_str());
        cJSON_AddNumberToObject(root, "config_version", peer.config_version);
        cJSON_AddNumberToObject(root, "owner_epoch", peer.owner_epoch);
        cJSON_AddNumberToObject(root, "protocol_version", 3);
        cJSON_AddNumberToObject(root, "session_id", session);
        cJSON_AddNumberToObject(root, "request_id", request);
        cJSON_AddStringToObject(root, "cmd", "LISTEN_FOLLOWUP");
        const std::string command = kwsEncode(root);
        cJSON_Delete(root);
        std::string ack;
        return transport->sendCommand(peer.node_id.c_str(), command, &ack);
    };
    const auto feedback = [](const char* status, const char*) {
        if (strcmp(status, "success") == 0) SoundPlayer::instance().play(SoundType::SUCCESS);
        else if (strcmp(status, "error") == 0) SoundPlayer::instance().play(SoundType::ERROR);
    };

    const uint32_t kws_session = esp_random() | 1;
    auto kws = std::make_shared<KwsControl>(
        std::string(cfg.subbox_id), kws_session, publish_kws, trusted_peer, send_command,
        save_kws, [] { return static_cast<uint64_t>(esp_timer_get_time()) / 1000; },
        listen_followup, feedback,
        [] { return static_cast<uint64_t>(std::time(nullptr)); }
    );
    std::string kws_snapshot;
    core_kws=std::make_shared<CoreKwsControl>(
        [](const uint8_t* data,size_t size){return hc_runtime_emit(HC_EVENT_REPORT,data,size);},
        save_kws, []{return static_cast<uint64_t>(std::time(nullptr))*1000;});
    if (NVSManager::loadKwsSnapshot(kws_snapshot) == ESP_OK) {
        if (core_kws->configure(reinterpret_cast<const uint8_t*>(kws_snapshot.data()),kws_snapshot.size(),false))
            ESP_LOGI(TAG,"Stored Core KWS snapshot restored");
        else if (!kws->restore(kws_snapshot)) ESP_LOGW(TAG, "Stored local KWS snapshot rejected");
        else ESP_LOGI(TAG, "Local KWS snapshot restored before network startup");
    }

    transport->registerRxCallback([audio_mgr](const AudioPacket& pkt) {
        audio_mgr->ingestAudioPacket(pkt);
    });

    if (!transport->init()) subbox_led_set_error(true);

    auto task_mgr = std::make_shared<TaskManager>(
        audio_mgr, transport, audio_router, tts_mgr,
        context_mgr, registry, command_router, rule_engine,
        room_mgr, mqtt, kws
    );
    task_mgr->setCoreKws(core_kws);
    if (!task_mgr->init()) subbox_led_set_error(true);
    asr->registerPlaybackDoneCallback([task_mgr](const std::string& payload) {
        if (!task_mgr->queueKwsPlaybackDone(payload)) ESP_LOGW(TAG, "KWS playback-done queue full");
    });

    hc_mqtt=mqtt.get();
    hc_runtime_set_application_handler(hc_application);
    ESP_ERROR_CHECK(hc_runtime_init(true,hc_uplink,nullptr,nullptr));
    mqtt->init();
    hc_ota_health_ready();

    auto console = std::make_shared<DevConsole>(
        local_kws, audio_mgr, context_mgr, registry, command_router, room_mgr
    );
    console->init();

    ESP_LOGI(TAG, "SubBox fully operational. Local KWS controls ActionBox; Pi4 provides structured replies.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
