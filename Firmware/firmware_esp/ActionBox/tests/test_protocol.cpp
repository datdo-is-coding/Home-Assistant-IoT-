#include "unity.h"
#include "actionbox_protocol.h"
#include "nvs_storage.h"
#include "bl0942.h"
#include "cJSON.h"
#include <stdio.h>
#include <string.h>

// These hardware seams do not actuate GPIO or access the board's live NVS.
static ActionBoxPersistentConfig config{};
extern "C" const ActionBoxPersistentConfig* nvs_storage_get_cached_config() { return &config; }
extern "C" RelayState relay_get_state(uint8_t) { return RELAY_STATE_OFF; }
extern "C" RelayFault relay_get_fault(uint8_t) { return RELAY_FAULT_NONE; }
extern "C" esp_err_t bl0942_get_latest_measurement(uint8_t, CurrentMeasurement* out) {
    *out = {}; out->validity = SENSOR_STATUS_VALID; return ESP_OK;
}

static void parse_boundaries() {
    char json[512];
    ActionBoxCommand command{};
    snprintf(json, sizeof(json), "{\"protocol_version\":3,\"node_id\":\"ABTEST\",\"hardware_uid\":\"%s\",\"config_version\":1,\"request_id\":1,\"session_id\":7,\"cmd\":\"TURN_OFF\",\"channel\":1}", protocol_get_hardware_uid());
    TEST_ASSERT_EQUAL(ESP_OK, protocol_parse_command(json, &command));
    cJSON* root = cJSON_Parse(json);
    cJSON_SetValuestring(cJSON_GetObjectItem(root, "cmd"), "TOGGLE");
    char* modified = cJSON_PrintUnformatted(root);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, protocol_parse_command(modified, &command));
    cJSON_free(modified);
    cJSON_SetValuestring(cJSON_GetObjectItem(root, "cmd"), "TURN_OFF");
    cJSON_SetValuestring(cJSON_GetObjectItem(root, "hardware_uid"), "FFFFFFFFFFFF");
    modified = cJSON_PrintUnformatted(root);
    TEST_ASSERT_EQUAL(ESP_ERR_NOT_FOUND, protocol_parse_command(modified, &command));
    cJSON_free(modified);
    cJSON_SetValuestring(cJSON_GetObjectItem(root, "hardware_uid"), protocol_get_hardware_uid());
    cJSON_SetNumberValue(cJSON_GetObjectItem(root, "config_version"), 2);
    modified = cJSON_PrintUnformatted(root);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_VERSION, protocol_parse_command(modified, &command));
    cJSON_free(modified);
    cJSON_SetNumberValue(cJSON_GetObjectItem(root, "config_version"), 1);
    cJSON_SetNumberValue(cJSON_GetObjectItem(root, "session_id"), 0);
    modified = cJSON_PrintUnformatted(root);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, protocol_parse_command(modified, &command));
    cJSON_free(modified); cJSON_Delete(root);
}

static void response_identity_and_session_cache() {
    ActionBoxResponse response{};
    response.version = 3; response.session_id = 7; response.request_id = 1;
    strcpy(response.node_id, config.node_id); strcpy(response.status, "OK"); strcpy(response.state, "OFF");
    char json[768], cached[768];
    TEST_ASSERT_EQUAL(ESP_OK, protocol_serialize_response(&response, json, sizeof(json)));
    cJSON* root = cJSON_Parse(json);
    TEST_ASSERT_EQUAL_STRING("ACK", cJSON_GetObjectItem(root, "type")->valuestring);
    TEST_ASSERT_EQUAL_STRING(protocol_get_hardware_uid(), cJSON_GetObjectItem(root, "hardware_uid")->valuestring);
    TEST_ASSERT_EQUAL(3, cJSON_GetObjectItem(root, "protocol_version")->valueint);
    TEST_ASSERT_EQUAL(1, cJSON_GetObjectItem(root, "config_version")->valueint);
    TEST_ASSERT_TRUE(protocol_is_duplicate_request(1, 7, cached, sizeof(cached)));
    TEST_ASSERT_EQUAL_STRING(json, cached);
    TEST_ASSERT_FALSE(protocol_is_duplicate_request(1, 8, cached, sizeof(cached)));
    cJSON_Delete(root);
}

extern "C" void app_main() {
    strcpy(config.node_id, "ABTEST"); config.config_version = 1;
    protocol_init();
    UNITY_BEGIN();
    RUN_TEST(parse_boundaries);
    RUN_TEST(response_identity_and_session_cache);
    UNITY_END();
}
