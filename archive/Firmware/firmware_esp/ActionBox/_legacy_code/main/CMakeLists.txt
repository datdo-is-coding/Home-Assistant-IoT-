FILE(GLOB app_sources ${CMAKE_CURRENT_SOURCE_DIR}/*.c)

idf_component_register(
    SRCS ${app_sources}
    INCLUDE_DIRS
        "."
        "../include"
    REQUIRES
        shared
        nvs_flash
        esp_wifi
        driver
        esp_driver_gpio
        esp_driver_i2s
        esp_timer
        esp_event
        esp_system
)

target_compile_definitions(${COMPONENT_LIB} PUBLIC
    T1_ACTUATOR_NODE=1
    HAS_RELAY=1
    HAS_MIC=1
    HAS_WAKENET=0
    HAS_ADPCM=1
    FW_VERSION_MAJOR=1
    FW_VERSION_MINOR=0
    FW_VERSION_PATCH=0
)

target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=heap_caps_calloc"
    "-Wl,--wrap=heap_caps_malloc"
    "-Wl,--wrap=heap_caps_realloc"
    "-Wl,--wrap=malloc"
    "-Wl,--wrap=calloc"
    "-Wl,--wrap=dl_lib_calloc"
    "-Wl,--wrap=dl_lib_calloc_psram"
)
