set(app_sources
    "main.c"
    "input/audio_input.c"
    "input/trigger_manager.c"
    "output/audio_output.c"
    "output/esp_sound_assets.c"
    "output/status_indicator.c"
    "output/usb_stream.c"
)

idf_component_register(
    SRCS ${app_sources}

    INCLUDE_DIRS 
        "."
        "input"
        "output"
    REQUIRES
        nvs_flash
        driver
        esp_driver_gpio
        esp_driver_i2s
        esp_driver_usb_serial_jtag
        esp_timer
        esp_system
        spiffs
)

