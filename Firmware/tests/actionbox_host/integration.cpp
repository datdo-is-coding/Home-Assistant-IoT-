#include "host_idf.h"
#include "nvs_storage.h"
#include "actionbox_protocol.h"
#include "safety_supervisor.h"
#include "bl0942.h"
#include "led_driver.h"
#include "cJSON.h"
#include <vector>

static std::vector<uint8_t> blob;
esp_err_t nvs_flash_init() { return ESP_OK; }
esp_err_t nvs_flash_erase() { assert(false && "Must preserve V1 configuration"); return ESP_FAIL; }
esp_err_t nvs_open(const char* name, int, int* handle) {
    assert(strcmp(name, "actionbox_v2") == 0); *handle = 1; return ESP_OK;
}
esp_err_t nvs_get_blob(int, const char*, void* out, size_t* size) {
    if (blob.empty()) return ESP_ERR_NOT_FOUND;
    if (blob.size() > *size) { *size = blob.size(); return ESP_ERR_INVALID_SIZE; }
    memcpy(out, blob.data(), blob.size()); *size = blob.size(); return ESP_OK;
}
esp_err_t nvs_set_blob(int, const char*, const void* bytes, size_t size) {
    auto* start = static_cast<const uint8_t*>(bytes); blob.assign(start, start + size); return ESP_OK;
}
esp_err_t nvs_commit(int) { return ESP_OK; }
esp_err_t nvs_erase_all(int) { blob.clear(); return ESP_OK; }
void nvs_close(int) {}
esp_err_t gpio_config(const gpio_config_t*) { return ESP_OK; }
esp_err_t gpio_set_level(int pin, uint32_t) { assert(pin >= 0 && pin < 49); return ESP_OK; }
extern "C" esp_err_t bl0942_read_channel(uint8_t, CurrentMeasurement* out) {
    *out = {}; out->validity = SENSOR_STATUS_VALID;
    out->timestamp_ms = esp_timer_get_time() / 1000;
    return ESP_OK;
}
extern "C" esp_err_t bl0942_get_latest_measurement(uint8_t, CurrentMeasurement* out) {
    *out = {UINT32_MAX, UINT32_MAX, INT32_MIN, UINT32_MAX, SENSOR_STATUS_VALID, false, 1, UINT32_MAX};
    return ESP_OK;
}
int main() {
    assert(nvs_storage_init() == ESP_OK);
    auto cfg = *nvs_storage_get_cached_config();
    assert(strcmp(cfg.channel_names[2], "Relay Channel 3") == 0);
    assert(cfg.startup_modes[2] == STARTUP_MODE_ALWAYS_OFF);
    assert(cfg.max_current_ma[2] == 10000);
    auto saved = blob;
    blob.resize(4);
    assert(nvs_storage_load_config(&cfg) == ESP_ERR_INVALID_VERSION);
    blob = saved;
    assert(nvs_storage_load_config(&cfg) == ESP_OK);
    cfg.last_states[2] = RELAY_STATE_ON;
    assert(nvs_storage_save_config(&cfg) == ESP_OK);
    assert(nvs_storage_load_config(&cfg) == ESP_OK && cfg.last_states[2] == RELAY_STATE_ON);

    assert(relay_driver_init() == ESP_OK);
    assert(led_driver_init() == ESP_OK);
    assert(safety_supervisor_init() == ESP_OK);
    assert(relay_on(3) != ESP_OK);
    CurrentMeasurement sample{};
    sample.timestamp_ms = esp_timer_get_time() / 1000;
    safety_process_measurement(3, &sample);
    assert(relay_on(3) == ESP_OK);
    sample.current_rms_ma = 16000;
    sample.timestamp_ms = esp_timer_get_time() / 1000;
    safety_process_measurement(3, &sample);
    assert(relay_get_state(3) == RELAY_STATE_OFF && relay_get_fault(3) == RELAY_FAULT_OVERCURRENT);
    assert(relay_on(3) != ESP_OK);
    assert(relay_clear_fault(3) == ESP_OK);
    sample.current_rms_ma = 0;
    sample.timestamp_ms = esp_timer_get_time() / 1000;
    safety_process_measurement(3, &sample);
    assert(relay_on(3) == ESP_OK);
    vTaskDelay(2100);
    safety_check_sensor_timeouts();
    assert(relay_get_state(3) == RELAY_STATE_OFF && relay_get_fault(3) == RELAY_FAULT_HARDWARE);

    protocol_init();
    char json[APP_TELEMETRY_BUFFER_SIZE];
    assert(protocol_serialize_telemetry(json, sizeof(json)) == ESP_OK);
    auto* telemetry = cJSON_Parse(json);
    auto* channels = cJSON_GetObjectItem(telemetry, "channels");
    assert(cJSON_GetArraySize(channels) == 3);
    assert(cJSON_GetObjectItem(cJSON_GetArrayItem(channels, 2), "channel")->valueint == 3);
    cJSON_Delete(telemetry);
    char alert[APP_FAULT_ALERT_BUFFER_SIZE];
    assert(protocol_serialize_fault_alert(3, RELAY_FAULT_OVERCURRENT, UINT32_MAX, alert, sizeof(alert)) == ESP_OK);
    for (int ch : {3, 4}) {
        snprintf(json, sizeof(json), "{\"protocol_version\":3,\"node_id\":\"%s\",\"hardware_uid\":\"%s\",\"config_version\":%u,\"request_id\":1,\"session_id\":7,\"cmd\":\"TURN_OFF\",\"channel\":%d}",
                 cfg.node_id, protocol_get_hardware_uid(), cfg.config_version, ch);
        ActionBoxCommand command{};
        assert(protocol_parse_command(json, &command) == (ch == 3 ? ESP_OK : ESP_ERR_INVALID_ARG));
    }
}
