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

#include "config/subbox_config.h"
#include "config/board_pins.h"
#include "storage/nvs_manager.h"
#include "room/room_manager.h"
#include "audio/audio_transport/udp_audio_transport.h"
#include "audio/audio_transport/espnow_audio_transport.h"
#include "audio/audio_buffer/audio_ring_buffer.h"
#include "audio/vad/energy_vad.h"
#include "audio/asr/ws_asr.h"
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
#include "hc_provisioning.h"
static MqttClient* hc_mqtt=nullptr;
static bool hc_uplink(const uint8_t* data,size_t length) { return hc_mqtt && hc_mqtt->publishCore(data,length); }

static const char *TAG = "SUBBOX_MAIN";

#include "system/wifi_provisioning.h"
#include "system/subbox_led.h"

static int s_wifi_retry_count = 0;

static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                               int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Wi-Fi Station started, connecting to AP '%s'...", (const char*)arg);
        if (((const char*)arg)[0]) esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        subbox_led_set_wifi_connected(false);
        subbox_led_set_mqtt_connected(false);
        s_wifi_retry_count++;
        ESP_LOGW(TAG, "Wi-Fi disconnected (attempt %d/5)...", s_wifi_retry_count);
        if (!hc_provisioning_active() && ((const char*)arg)[0]) esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        s_wifi_retry_count = 0;
        ip_event_got_ip_t* event = (ip_event_got_ip_t*)event_data;
        ESP_LOGI(TAG, "✅ SubBox Wi-Fi Connected! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        subbox_led_set_wifi_connected(true);
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

    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "  AETHERIA OS — SUBBOX / SUBGATEWAY LOCAL BRAIN (ESP32-S3)");
    ESP_LOGI(TAG, "===============================================================");
    ESP_LOGI(TAG, "  Firmware Name    : %s", SUBBOX_FW_NAME);
    ESP_LOGI(TAG, "  Firmware Version : %s", SUBBOX_FW_VERSION_STR);
    ESP_LOGI(TAG, "  Silicon Model    : ESP32-S3 (Rev %d, %d Cores)", chip_info.revision, chip_info.cores);
    ESP_LOGI(TAG, "  Flash Size       : %lu MB", (unsigned long)(flash_size / (1024 * 1024)));
    ESP_LOGI(TAG, "  PSRAM Available  : %u KB (Total: 16 MB Octal)", (unsigned)free_psram);
    ESP_LOGI(TAG, "  Internal SRAM    : %u KB", (unsigned)free_sram);
    ESP_LOGI(TAG, "  SubBox ID        : %s", cfg.subbox_id);
    ESP_LOGI(TAG, "  Assigned Room    : %s (%s)", cfg.room_name, roomToString(cfg.room_type));
    ESP_LOGI(TAG, "  Real ASR Engine  : Pi 4 Sherpa-ONNX Zipformer (ws://192.168.11.29:8765)");
    ESP_LOGI(TAG, "  Audio Capacity   : Up to %d ActionBoxes per Room",
             SUBBOX_MAX_ACTIONBOXES_PER_ROOM);
    ESP_LOGI(TAG, "===============================================================");
}

static void wifi_init_sta(const char* ssid, const char* pass) {
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

    SubBoxPersistentConfig cfg;
    NVSManager::loadConfig(cfg);

    size_t free_psram = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "Audio relay PSRAM available: %u KB; local ASR/NLU disabled", (unsigned)(free_psram / 1024));

    print_banner(cfg);

    hc_provisioned_config enrollment{};
    esp_err_t enrollment_result=hc_provisioning_load(&enrollment);
    if(enrollment_result==ESP_OK && enrollment.subbox){
        snprintf(cfg.subbox_id,sizeof(cfg.subbox_id),"%lu",(unsigned long)enrollment.node_id);
        snprintf(cfg.wifi_ssid,sizeof(cfg.wifi_ssid),"%s",enrollment.wifi_ssid);
        snprintf(cfg.wifi_pass,sizeof(cfg.wifi_pass),"%s",enrollment.wifi_password);
        snprintf(cfg.mqtt_broker_uri,sizeof(cfg.mqtt_broker_uri),"%s",enrollment.mqtt_uri);
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
        NVSManager::saveConfig(cfg);
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

    auto room_mgr = std::make_shared<RoomManager>(cfg.subbox_id, cfg.room_type);
    room_mgr->setRoomName(cfg.room_name);

    auto vad = std::make_shared<EnergyVAD>(
        SUBBOX_VAD_INITIAL_ENERGY_THRESH,
        SUBBOX_VAD_SILENCE_TIMEOUT_MS,
        SUBBOX_VAD_SPEECH_ONSET_FRAMES,
        SUBBOX_VAD_MAX_SPEECH_DURATION_MS
    );

    auto asr = std::make_shared<WsASR>(cfg.ws_gateway_uri, cfg.subbox_id);
    if (!asr->init()) ESP_LOGE(TAG, "Pi4 audio relay unavailable; voice control disabled until configured/restarted");

    auto audio_mgr = std::make_shared<AudioManager>(vad, asr);
    audio_mgr->init();

    auto transport = std::make_shared<EspNowAudioTransport>();

    auto audio_router = std::make_shared<AudioOutputRouter>(transport);

    auto tts_mgr = std::make_shared<TTSManager>(audio_router);
    tts_mgr->init();

    auto registry = std::make_shared<ActionBoxRegistry>();
    registry->loadDefaultRoomNodes(cfg.room_type);

    auto context_mgr = std::make_shared<ContextManager>(cfg.room_type);

    auto command_router = std::make_shared<CommandRouter>(registry, context_mgr, audio_router, transport);

    auto rule_engine = std::make_shared<RuleEngine>(registry);
    rule_engine->init();

    auto mqtt = std::make_shared<MqttClient>(cfg.mqtt_broker_uri, cfg.subbox_id);
    command_router->setMqttClient(mqtt);

    transport->registerRxCallback([audio_mgr](const AudioPacket& pkt) {
        audio_mgr->ingestAudioPacket(pkt);
    });

    if (!transport->init()) subbox_led_set_error(true);

    auto task_mgr = std::make_shared<TaskManager>(
        audio_mgr, transport, audio_router, tts_mgr,
        context_mgr, registry, command_router, rule_engine,
        room_mgr, mqtt
    );
    if (!task_mgr->init()) subbox_led_set_error(true);
    asr->registerFollowupCallback([task_mgr](const std::string& command) {
        if (!task_mgr->queueGatewayCommand(command)) ESP_LOGW(TAG, "Follow-up listen queue full");
    });

    hc_mqtt=mqtt.get();
    ESP_ERROR_CHECK(hc_runtime_init(true,hc_uplink,nullptr,nullptr));
    mqtt->init();
    hc_ota_health_ready();

    auto console = std::make_shared<DevConsole>(
        asr, audio_mgr, context_mgr, registry, command_router, room_mgr
    );
    console->init();

    ESP_LOGI(TAG, "SubBox Local Brain fully operational. Listening for ActionBox streams and console commands.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
