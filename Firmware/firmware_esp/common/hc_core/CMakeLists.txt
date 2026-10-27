idf_component_register(SRCS "hc_protocol.c" "hc_runtime.c" "hc_ota.c" "hc_factory.c" "hc_ota_manifest.c" "hc_provisioning.c" INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_event esp_timer esp_system mbedtls app_update bootloader_support protocomm esp_netif esp_driver_gpio)

# Manufacturing data is supplied by an explicit private USB build only.
if(DEFINED HC_FACTORY_BOOTSTRAP_FILE AND NOT HC_FACTORY_BOOTSTRAP_FILE STREQUAL "")
    if(NOT EXISTS "${HC_FACTORY_BOOTSTRAP_FILE}")
        message(FATAL_ERROR "Missing private factory bootstrap bundle")
    endif()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE HC_FACTORY_BOOTSTRAP=1)
    target_add_binary_data(${COMPONENT_LIB} "${HC_FACTORY_BOOTSTRAP_FILE}" BINARY RENAME_TO hc_factory_bundle)
endif()
