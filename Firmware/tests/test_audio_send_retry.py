"""Run the real ActionBox send boundary against a congested fake SDK queue."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'firmware_esp/ActionBox_V2/src/network/espnow_transport.cpp'


class AudioSendRetry(unittest.TestCase):
    def test_bounded_no_memory_retry_preserves_other_failures(self):
        source = SOURCE.read_text()
        function = source[source.index('esp_err_t espnow_transport_send_to('):source.index('static std::atomic<int64_t> s_pairing_deadline_us')]
        stubs = r'''
#include <cstdint>
#include <cstring>
#include <cassert>
#include <vector>
using esp_err_t=int;constexpr int ESP_OK=0,ESP_ERR_INVALID_ARG=1,ESP_ERR_TIMEOUT=2,ESP_ERR_INVALID_STATE=3,ESP_ERR_ESPNOW_NO_MEM=4;
constexpr int ESP_NOW_MAX_DATA_LEN_V2=1470,pdTRUE=1,portMAX_DELAY=0;void* s_transport_mutex=nullptr;uint8_t s_broadcast_mac[6]={255,255,255,255,255,255};
int sends=0,delays=0;bool trusted=true;std::vector<int> results;
int xSemaphoreTake(void*,int){return 1;}void xSemaphoreGive(void*){}
bool hc_runtime_enabled(){return true;}bool hc_runtime_trusted_peer(const uint8_t*){return trusted;}
bool is_control_packet(const uint8_t*,size_t){return false;}bool esp_now_is_peer_exist(const uint8_t*){return true;}
struct esp_now_peer_info_t{uint8_t peer_addr[6];int channel,ifidx;bool encrypt;};constexpr int WIFI_IF_STA=0;
void esp_now_add_peer(esp_now_peer_info_t*){}
int esp_now_send(const uint8_t*,const uint8_t*,size_t){return results[sends++];}
int pdMS_TO_TICKS(int n){return n;}void vTaskDelay(int n){assert(n==10);++delays;}
#define ESP_LOGE(...)
#define ESP_LOGW(...)
'''
        runner = r'''
int main(){uint8_t mac[6]={1},pcm[244]={};
results={ESP_ERR_ESPNOW_NO_MEM,ESP_OK};assert(espnow_transport_send_to(mac,pcm,244)==ESP_OK);assert(sends==2&&delays==1);
sends=delays=0;results={ESP_ERR_ESPNOW_NO_MEM,ESP_ERR_ESPNOW_NO_MEM,ESP_ERR_ESPNOW_NO_MEM};assert(espnow_transport_send_to(mac,pcm,244)==ESP_ERR_ESPNOW_NO_MEM);assert(sends==3&&delays==2);
sends=delays=0;results={ESP_ERR_INVALID_STATE};assert(espnow_transport_send_to(mac,pcm,244)==ESP_ERR_INVALID_STATE);assert(sends==1&&delays==0);
sends=0;trusted=false;assert(espnow_transport_send_to(mac,pcm,244)==ESP_ERR_INVALID_STATE);assert(sends==0);
}
'''
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'test.cpp').write_text(stubs+function+runner)
            subprocess.run(['g++','-std=c++17',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
