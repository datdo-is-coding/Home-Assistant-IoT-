"""Exercise the real SubBox MQTT initializer with host transport/NVS doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'
CJSON = SRC.parent / 'managed_components/espressif__cjson/cJSON'


class SubBoxMqttTest(unittest.TestCase):
    def test_enrollment_broker_is_used_with_usb_trust_and_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'host.h').write_text(r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
using esp_err_t = int;
constexpr int ESP_OK = 0, ESP_EVENT_ANY_ID = -1;
using esp_event_base_t = const char*;
inline const char* esp_err_to_name(int) { return "error"; }
#define ESP_LOGI(...)
#define ESP_LOGW(...)
#define ESP_LOGE(...)
inline uint32_t esp_random() { return 1; }
using esp_mqtt_client_handle_t = void*;
enum esp_mqtt_event_id_t { MQTT_EVENT_CONNECTED, MQTT_EVENT_DISCONNECTED, MQTT_EVENT_DATA, MQTT_EVENT_ERROR };
struct esp_mqtt_event_t { int current_data_offset, data_len, total_data_len, topic_len; char *topic, *data; };
using esp_mqtt_event_handle_t = esp_mqtt_event_t*;
struct esp_mqtt_client_config_t {
    struct { struct { const char* certificate; } verification; struct { const char* uri; } address; } broker;
    struct { const char *client_id, *username; struct { const char* password; } authentication; } credentials;
    struct { int size; } buffer;
    struct { int reconnect_timeout_ms; } network;
};
inline std::string connected_uri, configured_ca, configured_user, configured_password;
inline esp_mqtt_client_handle_t esp_mqtt_client_init(const esp_mqtt_client_config_t* c) {
    connected_uri = c->broker.address.uri; configured_ca = c->broker.verification.certificate;
    configured_user = c->credentials.username; configured_password = c->credentials.authentication.password;
    return reinterpret_cast<void*>(1);
}
inline int esp_mqtt_client_register_event(void*, esp_mqtt_event_id_t, void(*)(void*,const char*,int32_t,void*),void*) { return 0; }
inline int esp_mqtt_client_start(void*) { return 0; }
inline int esp_mqtt_client_stop(void*) { return 0; }
inline int esp_mqtt_client_destroy(void*) { return 0; }
inline int esp_mqtt_client_subscribe(void*,const char*,int) { return 1; }
inline int esp_mqtt_client_publish(void*,const char*,const char*,int,int,int) { return 1; }
inline int esp_mqtt_client_enqueue(void*,const char*,const char*,int,int,int,bool) { return 1; }
inline bool hc_runtime_enabled() { return true; }
inline uint32_t hc_runtime_node_id() { return 1; }
inline bool hc_runtime_receive_mqtt(const uint8_t*,size_t) { return true; }
''')
            for header in ('esp_err.h', 'esp_event.h', 'mqtt_client.h', 'esp_log.h',
                           'esp_random.h', 'hc_runtime.h'):
                (root / header).write_text('#include "host.h"\n')
            (root / 'check.cpp').write_text(r'''
#include <cassert>
#include "host.h"
#include "mqtt/subbox_mqtt_client.h"
#include "storage/security_config.h"
#include "system/subbox_led.h"
bool trust_present = true;
namespace SecurityConfig {
std::string get(const char* key) {
    const std::string field(key);
    if (field == "mqtt_uri") return "mqtts://stale-usb-broker";
    if (field == "ca_pem") return trust_present ? "trusted-ca" : "";
    if (field == "mqtt_user") return "per-node-user";
    if (field == "mqtt_pass") return "per-node-password";
    return "";
}
}
extern "C" void subbox_led_set_mqtt_connected(bool) {}
extern "C" void subbox_led_set_mqtt_configured(bool) {}
int main() {
    {
        MqttClient client("mqtts://enrolled-broker", "1");
        assert(client.init());
        assert(connected_uri == "mqtts://enrolled-broker");
        assert(configured_ca == "trusted-ca");
        assert(configured_user == "per-node-user");
        assert(configured_password == "per-node-password");
    }
    connected_uri.clear();
    {
        MqttClient insecure("mqtt://insecure-broker", "1");
        assert(!insecure.init());
        assert(connected_uri.empty());
    }
    trust_present = false;
    MqttClient no_trust("mqtts://enrolled-broker", "1");
    assert(!no_trust.init());
    assert(connected_uri.empty());
}
''')
            subprocess.run([
                'g++', '-std=c++17', '-pthread', '-I', str(root), '-I', str(SRC),
                '-I', str(CJSON), str(root / 'check.cpp'),
                str(SRC / 'mqtt/subbox_mqtt_client.cpp'), str(CJSON / 'cJSON.c'),
                '-o', str(root / 'check')], check=True, capture_output=True, text=True)
            run = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
