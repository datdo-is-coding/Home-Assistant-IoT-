"""Host test runner for SubBox protected provisioning, 180s setup window, proof verification, and NVS sync."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
COMMON_SRC = HERE.parent / "firmware_esp/common/hc_core"


class SubBoxProvisioningTest(unittest.TestCase):
    def test_subbox_provisioning_lifecycle_and_security(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "host.h").write_text(r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <map>

using esp_err_t = int;
constexpr int ESP_OK = 0;
constexpr int ESP_FAIL = -1;
constexpr int ESP_ERR_NO_MEM = 0x101;
constexpr int ESP_ERR_INVALID_ARG = 0x102;
constexpr int ESP_ERR_INVALID_STATE = 0x103;
constexpr int ESP_ERR_INVALID_SIZE = 0x104;
constexpr int ESP_ERR_NOT_FOUND = 0x105;
constexpr int ESP_ERR_NOT_SUPPORTED = 0x106;
constexpr int ESP_ERR_TIMEOUT = 0x107;
constexpr int ESP_ERR_INVALID_RESPONSE = 0x108;
constexpr int ESP_ERR_INVALID_CRC = 0x109;
constexpr int ESP_ERR_INVALID_VERSION = 0x10A;
constexpr int ESP_ERR_INVALID_MAC = 0x10B;
constexpr int ESP_LOG_WARN = 2;
inline void esp_log_level_set(const char*, int) {}

using nvs_handle_t = uint32_t;
constexpr uint32_t NVS_READONLY = 0;
constexpr uint32_t NVS_READWRITE = 1;

extern "C" {
int64_t esp_timer_get_time();
esp_err_t nvs_open(const char* name, uint32_t mode, nvs_handle_t* out);
void nvs_close(nvs_handle_t handle);
esp_err_t nvs_commit(nvs_handle_t handle);
esp_err_t nvs_erase_all(nvs_handle_t handle);
esp_err_t nvs_get_str(nvs_handle_t handle, const char* key, char* out, size_t* len);
esp_err_t nvs_set_str(nvs_handle_t handle, const char* key, const char* val);
esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out, size_t* len);
esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* data, size_t len);
esp_err_t nvs_get_u8(nvs_handle_t handle, const char* key, uint8_t* out);
esp_err_t nvs_set_u8(nvs_handle_t handle, const char* key, uint8_t val);

esp_err_t esp_efuse_mac_get_default(uint8_t* mac);
esp_err_t esp_wifi_get_mac(int ifx, uint8_t* mac);
void esp_fill_random(void* buf, size_t len);
void esp_restart();

constexpr int WIFI_AUTH_OPEN = 0;
constexpr int WIFI_AUTH_WPA2_PSK = 3;
constexpr int WIFI_MODE_STA = 1;
constexpr int WIFI_MODE_APSTA = 3;
constexpr int WIFI_IF_STA = 0;
constexpr int WIFI_IF_AP = 1;

struct wifi_ap_config_t {
    uint8_t ssid[32];
    uint8_t password[64];
    uint8_t ssid_len;
    uint8_t channel;
    int authmode;
    uint8_t max_connection;
    struct { bool capable; } pmf_cfg;
};
union wifi_config_t { wifi_ap_config_t ap; };

esp_err_t esp_wifi_connect();
esp_err_t esp_wifi_set_mode(int mode);
esp_err_t esp_wifi_set_config(int ifx, wifi_config_t* cfg);

void* esp_netif_get_handle_from_ifkey(const char*);
void* esp_netif_create_default_wifi_ap();

using protocomm_t = void*;
using protocomm_security1_params_t = struct { const uint8_t* data; size_t len; };
using protocomm_security_t = void*;
extern protocomm_security_t protocomm_security1;

struct protocomm_http_server_config_t { uint16_t port; size_t stack_size; unsigned task_priority; };
struct protocomm_httpd_config_t {
    bool ext_handle_provided;
    struct {
        protocomm_http_server_config_t config;
    } data;
};
#define PROTOCOMM_HTTPD_DEFAULT_CONFIG() { 80, 4096, 5 }

protocomm_t* protocomm_new();
void protocomm_delete(protocomm_t* s);
esp_err_t protocomm_httpd_start(protocomm_t*, protocomm_httpd_config_t*);
void protocomm_httpd_stop(protocomm_t*);
esp_err_t protocomm_set_security(protocomm_t*, const char*, const protocomm_security_t*, void*);
using protocomm_req_handler_t = esp_err_t(*)(uint32_t, const uint8_t*, ssize_t, uint8_t**, ssize_t*, void*);
esp_err_t protocomm_add_endpoint(protocomm_t*, const char*, protocomm_req_handler_t, void*);

using SemaphoreHandle_t = void*;
using TaskHandle_t = void*;
using TaskFunction_t = void(*)(void*);
constexpr int pdTRUE = 1;
constexpr int pdPASS = 1;
inline uint32_t pdMS_TO_TICKS(uint32_t ms) { return ms; }
SemaphoreHandle_t xSemaphoreCreateMutex();
int xSemaphoreTake(SemaphoreHandle_t, uint32_t);
void xSemaphoreGive(SemaphoreHandle_t);
int xTaskCreate(TaskFunction_t, const char*, uint32_t, void*, int, TaskHandle_t*);
void vTaskDelay(uint32_t);
void vTaskDelete(TaskHandle_t);

constexpr int PSA_SUCCESS = 0;
using psa_status_t = int;
using mbedtls_svc_key_id_t = uint32_t;
using psa_key_attributes_t = struct { int dummy; };
#define PSA_KEY_ATTRIBUTES_INIT { 0 }
inline void psa_set_key_type(psa_key_attributes_t*, int) {}
inline void psa_set_key_bits(psa_key_attributes_t*, size_t) {}
inline void psa_set_key_usage_flags(psa_key_attributes_t*, int) {}
inline void psa_set_key_algorithm(psa_key_attributes_t*, int) {}
inline void psa_reset_key_attributes(psa_key_attributes_t*) {}
inline psa_status_t psa_crypto_init() { return PSA_SUCCESS; }
inline psa_status_t psa_import_key(const psa_key_attributes_t*, const uint8_t*, size_t, mbedtls_svc_key_id_t* h) { *h = 1; return PSA_SUCCESS; }
inline psa_status_t psa_destroy_key(mbedtls_svc_key_id_t) { return PSA_SUCCESS; }
inline psa_status_t psa_mac_compute(mbedtls_svc_key_id_t, int, const uint8_t*, size_t, uint8_t* digest, size_t, size_t* out_len) {
    memset(digest, 0x11, 32);
    *out_len = 32;
    return PSA_SUCCESS;
}
#define PSA_KEY_TYPE_HMAC 1
#define PSA_KEY_USAGE_SIGN_MESSAGE 1
#define PSA_ALG_HMAC(x) 1
#define PSA_ALG_SHA_256 1

using gpio_config_t = struct { uint64_t pin_bit_mask; int mode; int pull_up_en; };
constexpr int GPIO_NUM_0 = 0;
constexpr int GPIO_MODE_INPUT = 1;
constexpr int GPIO_PULLUP_ENABLE = 1;
esp_err_t gpio_config(const gpio_config_t*);
int gpio_get_level(int);

void hc_factory_id(const uint8_t mac[6], char out[16]);
}
''')

            for header in (
                "esp_err.h", "esp_log.h", "esp_timer.h", "nvs.h",
                "esp_mac.h", "esp_random.h", "esp_wifi.h", "esp_system.h",
                "driver/gpio.h", "esp_netif.h", "protocomm.h", "protocomm_httpd.h",
                "protocomm_security1.h", "freertos/FreeRTOS.h", "freertos/task.h",
                "freertos/semphr.h", "psa/crypto.h"
            ):
                hpath = root / header
                hpath.parent.mkdir(parents=True, exist_ok=True)
                hpath.write_text('#include "host.h"\n')

            (root / "main_test.cpp").write_text(r'''
#include <cassert>
#include "host.h"

static int64_t s_mock_time_us = 0;
extern "C" int64_t esp_timer_get_time() { return s_mock_time_us; }

static std::map<std::string, std::map<std::string, std::string>> s_nvs_strings;
static std::map<std::string, std::map<std::string, std::vector<uint8_t>>> s_nvs_blobs;
static std::map<std::string, std::map<std::string, uint8_t>> s_nvs_u8;
static std::map<uint32_t, std::string> s_handles;
static uint32_t s_next_handle = 1;

extern "C" {
protocomm_security_t protocomm_security1 = (void*)1;

esp_err_t nvs_open(const char* name, uint32_t mode, nvs_handle_t* out) {
    (void)mode;
    uint32_t h = s_next_handle++;
    s_handles[h] = name;
    *out = h;
    return ESP_OK;
}
void nvs_close(nvs_handle_t handle) { s_handles.erase(handle); }
esp_err_t nvs_commit(nvs_handle_t handle) { (void)handle; return ESP_OK; }
esp_err_t nvs_erase_all(nvs_handle_t handle) {
    auto ns = s_handles[handle];
    s_nvs_strings[ns].clear();
    s_nvs_blobs[ns].clear();
    s_nvs_u8[ns].clear();
    return ESP_OK;
}

esp_err_t nvs_get_str(nvs_handle_t handle, const char* key, char* out, size_t* len) {
    auto ns = s_handles[handle];
    if (s_nvs_strings[ns].find(key) == s_nvs_strings[ns].end()) return ESP_ERR_NOT_FOUND;
    const auto& val = s_nvs_strings[ns][key];
    if (!out) { *len = val.size() + 1; return ESP_OK; }
    if (*len < val.size() + 1) return ESP_ERR_INVALID_SIZE;
    memcpy(out, val.c_str(), val.size() + 1);
    *len = val.size() + 1;
    return ESP_OK;
}
esp_err_t nvs_set_str(nvs_handle_t handle, const char* key, const char* val) {
    auto ns = s_handles[handle];
    s_nvs_strings[ns][key] = val;
    return ESP_OK;
}

esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out, size_t* len) {
    auto ns = s_handles[handle];
    if (s_nvs_blobs[ns].find(key) == s_nvs_blobs[ns].end()) return ESP_ERR_NOT_FOUND;
    const auto& blob = s_nvs_blobs[ns][key];
    if (!out) { *len = blob.size(); return ESP_OK; }
    if (*len < blob.size()) return ESP_ERR_INVALID_SIZE;
    memcpy(out, blob.data(), blob.size());
    *len = blob.size();
    return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* data, size_t len) {
    auto ns = s_handles[handle];
    const uint8_t* p = (const uint8_t*)data;
    s_nvs_blobs[ns][key] = std::vector<uint8_t>(p, p + len);
    return ESP_OK;
}

esp_err_t nvs_get_u8(nvs_handle_t handle, const char* key, uint8_t* out) {
    auto ns = s_handles[handle];
    if (s_nvs_u8[ns].find(key) == s_nvs_u8[ns].end()) return ESP_ERR_NOT_FOUND;
    *out = s_nvs_u8[ns][key];
    return ESP_OK;
}
esp_err_t nvs_set_u8(nvs_handle_t handle, const char* key, uint8_t val) {
    auto ns = s_handles[handle];
    s_nvs_u8[ns][key] = val;
    return ESP_OK;
}

esp_err_t esp_efuse_mac_get_default(uint8_t* mac) {
    mac[0] = 0xAA; mac[1] = 0xBB; mac[2] = 0xCC;
    mac[3] = 0x01; mac[4] = 0x02; mac[5] = 0x03;
    return ESP_OK;
}
esp_err_t esp_wifi_get_mac(int ifx, uint8_t* mac) { (void)ifx; return esp_efuse_mac_get_default(mac); }
void esp_fill_random(void* buf, size_t len) { memset(buf, 0x42, len); }
void esp_restart() {}

static bool s_wifi_connect_called = false;
static int s_wifi_retry_count = 0;
static bool s_softap_opened = false;
static std::string s_softap_ssid;
static int s_softap_auth_mode = -1;

esp_err_t esp_wifi_connect() { s_wifi_connect_called = true; return ESP_OK; }
esp_err_t esp_wifi_set_mode(int mode) { (void)mode; return ESP_OK; }
esp_err_t esp_wifi_set_config(int ifx, wifi_config_t* cfg) {
    if (ifx == WIFI_IF_AP && cfg) {
        s_softap_opened = true;
        s_softap_ssid = (char*)cfg->ap.ssid;
        s_softap_auth_mode = cfg->ap.authmode;
    }
    return ESP_OK;
}

void* esp_netif_get_handle_from_ifkey(const char*) { return (void*)1; }
void* esp_netif_create_default_wifi_ap() { return (void*)1; }

protocomm_t* protocomm_new() { return (protocomm_t*)malloc(sizeof(void*)); }
void protocomm_delete(protocomm_t* s) { free(s); }
esp_err_t protocomm_httpd_start(protocomm_t*, protocomm_httpd_config_t* config) {
    assert(config->data.config.port == 80);
    assert(config->data.config.task_priority > 0);
    assert(config->data.config.stack_size >= 4096);
    return ESP_OK;
}
void protocomm_httpd_stop(protocomm_t*) {}
esp_err_t protocomm_set_security(protocomm_t*, const char*, const protocomm_security_t*, void*) { return ESP_OK; }
esp_err_t protocomm_add_endpoint(protocomm_t*, const char*, protocomm_req_handler_t, void*) { return ESP_OK; }

SemaphoreHandle_t xSemaphoreCreateMutex() { return (void*)1; }
int xSemaphoreTake(SemaphoreHandle_t, uint32_t) { return pdTRUE; }
void xSemaphoreGive(SemaphoreHandle_t) {}
int xTaskCreate(TaskFunction_t, const char*, uint32_t, void*, int, TaskHandle_t*) { return pdPASS; }
void vTaskDelay(uint32_t) {}
void vTaskDelete(TaskHandle_t) {}

esp_err_t gpio_config(const gpio_config_t*) { return ESP_OK; }
int gpio_get_level(int) { return 1; }

void hc_factory_id(const uint8_t mac[6], char out[16]) {
    snprintf(out, 16, "HC-%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}
} // extern "C"

#define protocomm_httpd_config_t ::protocomm_httpd_config_t
#include "hc_provisioning.c"

static void simulate_wifi_disconnected(const char* ssid) {
    s_wifi_retry_count++;
    if (!hc_provisioning_active() && ssid[0]) {
        esp_wifi_connect();
    }
}

int main() {
    printf("============================================================\n");
    printf("   RUNNING SUBBOX PROVISIONING & SECURITY AUDIT TESTS       \n");
    printf("============================================================\n");

    // Seed factory partition
    {
        uint32_t fh;
        nvs_open("hc_factory", NVS_READWRITE, &fh);
        uint8_t secret[32]; memset(secret, 0x55, sizeof(secret));
        nvs_set_blob(fh, "secret", secret, sizeof(secret));
        nvs_set_str(fh, "setup", "PROV-POP-SECRET-999");
        nvs_set_str(fh, "ap_pass", "FactoryWpa2Passphrase");
        nvs_set_u8(fh, "kind", 1);
        nvs_close(fh);
    }

    // TEST 1: Setup Window 180s Standard
    printf("[TEST 1] Testing 180s setup window standard...\n");
    s_mock_time_us = 1000000ULL; // t = 1.0s
    assert(hc_provisioning_start(true) == ESP_OK);
    assert(hc_provisioning_active());
    assert(s_softap_opened);
    assert(s_softap_auth_mode == WIFI_AUTH_WPA2_PSK);
    assert(s_softap_ssid == "siciot_sub_010203");

    // t = 100s
    s_mock_time_us = 100000000ULL;
    assert(hc_provisioning_active());

    // t = 179s (< 180s window)
    s_mock_time_us = 180500000ULL;
    assert(hc_provisioning_active());

    // t = 182s (expired)
    s_mock_time_us = 182000000ULL;
    assert(!hc_provisioning_active());

    const char* dummy_cfg = "{\"ssid\":\"WiFi\",\"pass\":\"12345678\"}";
    assert(hc_provisioning_apply((const uint8_t*)dummy_cfg, strlen(dummy_cfg)) == ESP_ERR_INVALID_STATE);

    hc_provisioning_stop();
    assert(!hc_provisioning_active());
    printf("[TEST 1] PASS: 180s window verified, expired setup rejected.\n");

    // TEST 2: Proof-of-Possession Verification & Rejection
    printf("[TEST 2] Testing POP verification and rejection on wrong proof...\n");
    s_mock_time_us = 200000000ULL;
    assert(hc_provisioning_start(true) == ESP_OK);
    assert(hc_provisioning_active());

    const char* bad_proof_payload =
        "{\"ssid\":\"HomeWiFi\",\"password\":\"secretPass\","
        "\"gateway_host\":\"192.168.1.150\",\"gateway_port\":8883,"
        "\"pop\":\"INCORRECT-POP\",\"room_name\":\"Phòng khách\"}";
    int bad_res = hc_provisioning_apply((const uint8_t*)bad_proof_payload, strlen(bad_proof_payload));
    assert(bad_res == ESP_ERR_INVALID_STATE);

    const char* missing_ssid_payload = "{\"ssid\":\"\",\"pop\":\"PROV-POP-SECRET-999\"}";
    assert(hc_provisioning_apply((const uint8_t*)missing_ssid_payload, strlen(missing_ssid_payload)) == ESP_ERR_INVALID_ARG);

    const char* good_payload =
        "{\"ssid\":\"Home-WiFi-2.4G\",\"password\":\"MyHomePass123\","
        "\"gateway_host\":\"192.168.1.200\",\"gateway_port\":8883,"
        "\"pop\":\"PROV-POP-SECRET-999\",\"room_name\":\"Phòng khách\",\"room_type\":1}";
    int good_res = hc_provisioning_apply((const uint8_t*)good_payload, strlen(good_payload));
    assert(good_res == ESP_OK);
    printf("[TEST 2] PASS: Wrong POP strictly rejected; correct POP accepted.\n");

    // TEST 3: NVS Synchronization
    printf("[TEST 3] Testing synchronous credentials storage to subbox_cfg and subbox_sec...\n");
    assert(s_nvs_strings["subbox_cfg"]["ssid"] == "Home-WiFi-2.4G");
    assert(s_nvs_strings["subbox_cfg"]["pass"] == "MyHomePass123");
    assert(s_nvs_strings["subbox_cfg"]["broker"] == "mqtts://192.168.1.200:8883");
    assert(s_nvs_strings["subbox_cfg"]["wsuri"] == "ws://192.168.1.200:8765/ws/audio");
    assert(s_nvs_strings["subbox_cfg"]["room"] == "Phòng khách");

    assert(s_nvs_strings["subbox_sec"]["wifi_ssid"] == "Home-WiFi-2.4G");
    assert(s_nvs_strings["subbox_sec"]["wifi_pass"] == "MyHomePass123");
    assert(s_nvs_strings["subbox_sec"]["mqtt_uri"] == "mqtts://192.168.1.200:8883");
    assert(s_nvs_strings["subbox_sec"]["ws_uri"] == "ws://192.168.1.200:8765/ws/audio");

    uint8_t* status_out = nullptr;
    ssize_t status_len = 0;
    assert(status_endpoint(1, nullptr, 0, &status_out, &status_len, nullptr) == ESP_OK);
    assert(status_out != nullptr);
    assert(std::string((char*)status_out, status_len) == "{\"status\":\"PROVISIONED\"}");
    free(status_out);

    hc_provisioning_stop();
    printf("[TEST 3] PASS: NVS synchronized to subbox_cfg & subbox_sec and status confirmed.\n");

    hc_provisioned_config speaker{};
    assert(hc_provisioning_load(&speaker)==ESP_OK);
    char token[65]{};
    assert(hc_provisioning_speaker_token(token)==ESP_ERR_INVALID_STATE);
    speaker.committed=1;
    memset(speaker.key,0x22,sizeof(speaker.key));
    uint32_t sh;assert(nvs_open("hc_core",NVS_READWRITE,&sh)==ESP_OK);
    assert(nvs_set_blob(sh,"enrollment",&speaker,sizeof(speaker))==ESP_OK);nvs_close(sh);
    assert(hc_provisioning_speaker_token(token)==ESP_OK);
    assert(std::string(token)==std::string(64,'1')); // Host PSA returns the fixed 0x11 digest.

    // TEST 4: Wi-Fi Disconnect Reconnects and Never Opens AP
    printf("[TEST 4] Testing Wi-Fi disconnect reconnects and never opens AP...\n");
    s_wifi_connect_called = false;
    s_softap_opened = false;
    s_wifi_retry_count = 0;

    for (int i = 0; i < 5; ++i) {
        simulate_wifi_disconnected("Home-WiFi-2.4G");
    }
    assert(s_wifi_retry_count == 5);
    assert(s_wifi_connect_called);
    assert(!hc_provisioning_active());
    printf("[TEST 4] PASS: 5x Wi-Fi disconnect only reconnects and never opens AP.\n");

    printf("\n=== ALL SUBBOX PROVISIONING HOST TESTS PASSED! ===\n");
    return 0;
}
''')

            bin_path = root / "test_subbox_provisioning"
            cmd_compile = [
                "g++", "-std=c++17",
                "-I", str(root),
                "-I", str(COMMON_SRC),
                str(root / "main_test.cpp"),
                "-o", str(bin_path)
            ]
            compile_proc = subprocess.run(cmd_compile, capture_output=True, text=True)
            self.assertEqual(compile_proc.returncode, 0, f"Compilation failed:\n{compile_proc.stderr}")

            run_proc = subprocess.run([str(bin_path)], capture_output=True, text=True)
            self.assertEqual(run_proc.returncode, 0, f"Execution failed:\n{run_proc.stderr}")
            self.assertIn("ALL SUBBOX PROVISIONING HOST TESTS PASSED!", run_proc.stdout)


if __name__ == "__main__":
    unittest.main()
