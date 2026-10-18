cmake_minimum_required(VERSION 3.16.0)

set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../common/hc_core" "${CMAKE_CURRENT_LIST_DIR}/src")
set(SDKCONFIG_DEFAULTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.defaults")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ActionBox_V2)
