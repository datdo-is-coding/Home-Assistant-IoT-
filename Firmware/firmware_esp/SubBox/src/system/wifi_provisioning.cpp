#include "wifi_provisioning.h"
#include "hc_provisioning.h"
#include "esp_log.h"

static const char *TAG = "WIFI_PROV";

esp_err_t wifi_provisioning_start(void) {
    ESP_LOGI(TAG, "Starting SubBox secure provisioning (180s, WPA2-PSK, POP protected)...");
    return hc_provisioning_start(true);
}

void wifi_provisioning_stop(void) {
    ESP_LOGI(TAG, "Stopping SubBox provisioning session...");
    hc_provisioning_stop();
}

bool wifi_provisioning_is_active(void) {
    return hc_provisioning_active();
}

