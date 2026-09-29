file(GLOB_RECURSE app_sources 
    "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/*.c"
)

idf_component_register(
    SRCS ${app_sources}
    INCLUDE_DIRS
        "."
        "config"
        "audio"
        "audio/audio_manager"
        "audio/audio_transport"
        "audio/audio_buffer"
        "audio/vad"
        "audio/asr"
        "audio/audio_output"
        "nlu"
        "nlu/normalizer"
        "nlu/intent"
        "nlu/entity"
        "nlu/context"
        "actionbox"
        "actionbox/registry"
        "actionbox/protocol"
        "actionbox/router"
        "room"
        "rules"
        "mqtt"
        "tts"
        "storage"
        "system"
    REQUIRES
        nvs_flash
        esp_wifi
        esp_event
        esp_timer
        esp_system
        esp_driver_gpio
        esp_driver_uart
        espressif__mqtt
        espressif__cjson
        espressif__esp_websocket_client
        app_update
        bootloader_support
        esp_netif
        spi_flash
        lwip
        esp_http_server
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=stringop-truncation -Wno-stringop-truncation -Wno-error=missing-field-initializers -Wno-missing-field-initializers)
