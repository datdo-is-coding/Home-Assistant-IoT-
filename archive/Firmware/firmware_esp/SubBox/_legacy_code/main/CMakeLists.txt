FILE(GLOB app_sources ${CMAKE_CURRENT_SOURCE_DIR}/*.c)

idf_component_register(
    SRCS ${app_sources}
    INCLUDE_DIRS
        "."
        "../include"
    REQUIRES
        shared
        dtv_audio
        nvs_flash
        esp_wifi
        driver
        esp_driver_gpio
        esp_driver_uart
        esp_driver_i2s
        esp_driver_rmt
        esp_timer
        esp_event
        mqtt
        esp_websocket_client
        cjson
        esp_system
)

target_compile_definitions(${COMPONENT_LIB} PUBLIC
    T2_ZONE_CONTROLLER=1
    HAS_IR=1
    FW_VERSION_MAJOR=1
    FW_VERSION_MINOR=0
    FW_VERSION_PATCH=0
)
