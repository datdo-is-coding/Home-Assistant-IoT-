"""Run real SubBox claim/receive code with a deterministic radio and NVS boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'firmware_esp/SubBox/src'
CJSON = SRC.parent/'managed_components/espressif__cjson/cJSON'
class RegistrationTransportTest(unittest.TestCase):
    def test_discovery_claim_commit_and_reboot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'radio_host.h').write_text(r'''
#pragma once
#include "host_idf.h"
#include <map>
#include <set>
#include <vector>
#include <string>
#include <functional>
using TaskHandle_t=void*;
using QueueHandle_t=void*;
constexpr int pdPASS=1, WIFI_IF_STA=0, WIFI_SECOND_CHAN_NONE=0;
using wifi_second_chan_t=int;
inline QueueHandle_t xQueueCreate(int,size_t) {return reinterpret_cast<void*>(1);}
inline int xQueueSend(void*,const void*,int) {return 1;}
inline int xQueueReceive(void*,void*,int) {return 0;}
inline void vQueueDelete(void*) {}
inline int xTaskCreate(void(*)(void*),const char*,int,void*,int,void**) {return 1;}
inline void vTaskDelete(void*) {}
inline void esp_wifi_get_channel(uint8_t* c,int*) {*c=1;}
constexpr int WIFI_PS_NONE=0;
inline void esp_wifi_set_ps(int) {}
using esp_now_send_status_t=int;
constexpr int ESP_NOW_SEND_SUCCESS=0;
struct esp_now_recv_info_t {const uint8_t* src_addr;const uint8_t* des_addr;};
struct esp_now_peer_info_t {uint8_t peer_addr[6],lmk[16];int channel,ifidx;bool encrypt;};
inline std::map<std::string,esp_now_peer_info_t> radio_peers;
inline std::string mac_key(const uint8_t* mac) {return std::string((const char*)mac,6);}
inline int esp_now_add_peer(const esp_now_peer_info_t* p) {radio_peers[mac_key(p->peer_addr)]=*p;return 0;}
inline bool esp_now_is_peer_exist(const uint8_t* p) {return radio_peers.count(mac_key(p));}
inline int esp_now_get_peer(const uint8_t* p,esp_now_peer_info_t* out) {
 if(!radio_peers.count(mac_key(p))) return -1; *out=radio_peers[mac_key(p)];return 0;
}
int esp_now_send(const uint8_t*,const uint8_t*,size_t);
inline int esp_now_init() {return 0;}
inline void esp_now_deinit() {radio_peers.clear();}
inline void esp_now_unregister_recv_cb() {}
inline void esp_now_unregister_send_cb() {}
inline void esp_now_register_recv_cb(void(*)(const esp_now_recv_info_t*,const uint8_t*,int)) {}
inline void esp_now_register_send_cb(void(*)(const uint8_t*,int)) {}
inline bool hc_runtime_enabled() {return false;}
inline bool hc_runtime_trusted_peer(const uint8_t*) {return false;}
inline bool hc_runtime_receive_radio(const uint8_t*,const uint8_t*,size_t) {return false;}
inline uint32_t hc_runtime_peer_node_id(const uint8_t*) {return 0;}
inline bool hc_runtime_registered() {return false;}
''')
            for name in ['esp_err.h','esp_log.h','esp_wifi.h','esp_mac.h','esp_timer.h','esp_now.h','hc_runtime.h',
                         'freertos/FreeRTOS.h','freertos/task.h','freertos/queue.h','freertos/semphr.h']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "radio_host.h"\n')
            (root/'esp_idf_version.h').write_text('#define ESP_IDF_VERSION_VAL(a,b,c) ((a)*10000+(b)*100+(c))\n#define ESP_IDF_VERSION 50000\n')
            command=['g++','-std=c++17','-pthread','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
                '-I'+str(root),'-I'+str(ROOT/'tests/actionbox_host'),'-I'+str(SRC),
                '-I'+str(SRC.parent.parent/'common'),'-I'+str(CJSON),
                str(ROOT/'tests/registration_transport_host.cpp'),str(SRC/'audio/audio_transport/espnow_audio_transport.cpp'),
                str(CJSON/'cJSON.c'),'-o',str(root/'check')]
            build=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
