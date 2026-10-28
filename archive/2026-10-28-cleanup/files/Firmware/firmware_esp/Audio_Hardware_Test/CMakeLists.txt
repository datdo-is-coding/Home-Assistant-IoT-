cmake_minimum_required(VERSION 3.16.0)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../../../archive/Firmware/firmware_esp/Esp32S3_Master/managed_components/espressif__esp-sr"
    "${CMAKE_CURRENT_LIST_DIR}/../../../archive/Firmware/firmware_esp/Esp32S3_Master/managed_components/espressif__esp-dsp"
    "${CMAKE_CURRENT_LIST_DIR}/../ActionBox/managed_components/espressif__cjson"
)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(Audio_Hardware_Test)
