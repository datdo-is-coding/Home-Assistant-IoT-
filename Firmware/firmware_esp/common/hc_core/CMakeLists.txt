idf_component_register(SRCS "hc_protocol.c" "hc_runtime.c" "hc_ota.c" "hc_provisioning.c" INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_event esp_timer esp_system mbedtls app_update protocomm esp_netif esp_driver_gpio)
