"""Run the actual Wi-Fi event handler against lost/restored router events."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class SubBoxWifiRecovery(unittest.TestCase):
    def test_setup_failure_or_active_hotspot_never_stops_station_recovery(self):
        source = (Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src/main.cpp').read_text()
        handler = source[source.index('static void wifi_event_handler('):source.index('static void print_banner(')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(r'''
#include <cassert>
#include <cstdint>
using esp_event_base_t = int;
using esp_err_t = int;
constexpr int ESP_OK=0, WIFI_EVENT=1, IP_EVENT=2, WIFI_EVENT_STA_START=1,
  WIFI_EVENT_STA_DISCONNECTED=2, IP_EVENT_STA_GOT_IP=3, WIFI_CONNECTED_BIT=1, SNTP_OPMODE_POLL=0;
#define ESP_LOGI(...)
#define ESP_LOGW(...)
inline const char* esp_err_to_name(int) { return "test error"; }
struct ip_event_got_ip_t { struct { int ip; } ip_info; };
static int s_wifi_retry_count=0, s_wifi_event_group=1, connections=0, setup_attempts=0;
static bool setup_active=false, setup_available=false, wifi_led=false;
void subbox_led_set_wifi_connected(bool v) { wifi_led=v; }
void subbox_led_set_mqtt_connected(bool) {}
void xEventGroupClearBits(int,int) {}
void xEventGroupSetBits(int,int) {}
bool hc_provisioning_active() { return setup_active; }
int hc_provisioning_start(bool) { ++setup_attempts; setup_active=setup_available; return setup_available?0:1; }
int esp_wifi_connect() { ++connections; return 0; }
bool esp_sntp_enabled() { return true; }
void esp_sntp_setoperatingmode(int) {}
void esp_sntp_setservername(int,const char*) {}
void esp_sntp_init() {}
''' + handler + r'''
int main() {
 char ssid[]="saved-wifi";
 for (bool available : {false, true}) {
  setup_available=available; setup_active=false; connections=setup_attempts=s_wifi_retry_count=0;
  for(int i=0;i<8;++i) wifi_event_handler(ssid,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,nullptr);
  assert(connections==8 && "Reconnect must continue even after missing factory setup or while AP is active");
  assert(setup_attempts==1 && "Do not repeatedly recreate a failed setup service");
  setup_active=false; // setup window expired before router returns
  wifi_event_handler(ssid,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,nullptr);
  assert(connections==9);
  ip_event_got_ip_t ip{};
  wifi_event_handler(ssid,IP_EVENT,IP_EVENT_STA_GOT_IP,&ip);
  assert(s_wifi_retry_count==0 && wifi_led);
 }
 char blank[]=""; connections=0;
 wifi_event_handler(blank,WIFI_EVENT,WIFI_EVENT_STA_DISCONNECTED,nullptr);
 assert(connections==0);
}
''')
            code=(root/'test.cpp').read_text().replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>')
            (root/'test.cpp').write_text(code)
            build=subprocess.run(['g++','-std=c++17',str(root/'test.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_discovery_cannot_downgrade_configured_tls_broker(self):
        source = (Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src/main.cpp').read_text()
        block = source[source.index('                char new_ws_uri[128];'):source.index('                bool uri_changed = false;')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(r'''#include <cassert>
#include <cstring>
#include <cstdio>
#include <cstdint>
#define ESP_LOGW(...)
int main() {
 struct { char mqtt_broker_uri[128]; } cfg{};
 strcpy(cfg.mqtt_broker_uri,"mqtts://trusted-gateway:8883");
 const char* discovered_ip="192.168.1.99";
 uint16_t ws_port=8765, mqtt_port=1883;
''' + block + r'''
 assert(strcmp(new_mqtt_uri,cfg.mqtt_broker_uri)==0);
}
''')
            build=subprocess.run(['g++','-std=c++17',str(root/'test.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
