file(GLOB_RECURSE app_sources 
    "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/*.c"
)

idf_component_register(
    SRCS ${app_sources}
    INCLUDE_DIRS
        "."
        "config"
        "drivers/relay"
        "drivers/current_sensor"
        "drivers/button"
        "drivers/led"
        "protocol"
        "network"
        "device"
        "safety"
        "storage"
        "system"
        "audio"
    REQUIRES
        nvs_flash
        esp_wifi
        esp_event
        esp_timer
        esp_system
        esp_driver_gpio
        esp_driver_uart
        esp_driver_i2s
        driver
        espressif__cjson
        app_update
        bootloader_support
        esp_netif
        spi_flash
        espressif__esp-sr
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=stringop-truncation -Wno-stringop-truncation -Wno-error=missing-field-initializers -Wno-missing-field-initializers)
