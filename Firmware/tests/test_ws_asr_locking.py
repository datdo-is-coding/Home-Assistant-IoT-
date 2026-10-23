"""Compile real WsASR; a receive callback must run during every socket send."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'


class WsAsrLockingTest(unittest.TestCase):
    def test_receive_state_is_not_locked_while_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stubs = {
                'esp_log.h': '#pragma once\n#define ESP_LOGI(...)\n#define ESP_LOGW(...)\n#define ESP_LOGE(...)\n#define ESP_LOGD(...)\n',
                'esp_timer.h': '#pragma once\n#include <cstdint>\ninline int64_t esp_timer_get_time(){return 1;}\n',
                'esp_random.h': '#pragma once\n#include <cstring>\ninline void esp_fill_random(void* p,size_t n){memset(p,0,n);}\n',
                'storage/security_config.h': '#pragma once\n#include <string>\nnamespace SecurityConfig {inline std::string get(const char*){return "";}}\n',
                'hc_runtime.h': '#pragma once\ninline bool hc_runtime_enabled(){return false;}\ninline bool hc_runtime_registered(){return false;}\ninline int hc_runtime_node_id(){return 1;}\n',
                'freertos/FreeRTOS.h': '#pragma once\n#define pdMS_TO_TICKS(n) (n)\n#define pdTRUE 1\n',
                'freertos/semphr.h': '#pragma once\nusing SemaphoreHandle_t=void*;\ninline void* xSemaphoreCreateBinary(){return (void*)1;}\ninline int xSemaphoreTake(void*,unsigned){return 0;}\ninline int xSemaphoreGive(void*){return 1;}\ninline void vSemaphoreDelete(void*){}\n',
                'audio_output/sound_player.h': '#pragma once\nenum class SoundType{ERROR,SUCCESS};\ninline bool playback_finished=false;\nclass SoundPlayer{public: static SoundPlayer& instance(){static SoundPlayer s;return s;} bool play(SoundType){return true;} bool startPcmStream(){playback_finished=false;return true;} void finishPcmStream(){playback_finished=true;} bool streamPcmChunk(const short*,size_t){return true;}};\n',
                'cJSON.h': '#pragma once\nstruct cJSON{char* valuestring;double valuedouble;};\ninline cJSON* cJSON_ParseWithLength(const char*,int){return nullptr;}\ninline cJSON* cJSON_GetObjectItem(cJSON*,const char*){return nullptr;}\ninline bool cJSON_IsString(cJSON*){return false;}\ninline bool cJSON_IsNumber(cJSON*){return false;}\ninline bool cJSON_IsTrue(cJSON*){return false;}\ninline void cJSON_Delete(cJSON*){}\n',
                'esp_websocket_client.h': r'''#pragma once
#include <cstddef>
#include <cstdint>
using esp_event_base_t=const char*;
using esp_err_t=int;
constexpr int ESP_OK=0;
inline const char* esp_err_to_name(int){return "error";}
enum {WEBSOCKET_EVENT_ANY,WEBSOCKET_EVENT_CONNECTED,WEBSOCKET_EVENT_CLOSED,
      WEBSOCKET_EVENT_DISCONNECTED,WEBSOCKET_EVENT_DATA,WEBSOCKET_EVENT_ERROR};
struct esp_websocket_event_data_t{int op_code;const char* data_ptr;int data_len;};
struct esp_websocket_client_config_t{const char *cert_pem,*headers,*uri;int buffer_size,
 reconnect_timeout_ms,network_timeout_ms,ping_interval_sec,pingpong_timeout_sec;
 bool disable_auto_reconnect,enable_close_reconnect;};
using Handler=void(*)(void*,esp_event_base_t,int32_t,void*);
struct Client{Handler handler;void* arg;};
using esp_websocket_client_handle_t=Client*;
inline Client* connected_client=nullptr;
inline Client* esp_websocket_client_init(esp_websocket_client_config_t*){return connected_client=new Client{};}
inline int esp_websocket_register_events(Client* c,int,Handler h,void* a){c->handler=h;c->arg=a;return 0;}
inline int esp_websocket_client_start(Client* c){c->handler(c->arg,"",WEBSOCKET_EVENT_CONNECTED,nullptr);return 0;}
inline void esp_websocket_client_stop(Client*){}
inline void esp_websocket_client_destroy(Client* c){delete c;}
int socket_send(const char*,int);
inline int esp_websocket_client_send_text(Client*,const char* p,int n,int){return socket_send(p,n);}
inline int esp_websocket_client_send_bin(Client*,const char* p,int n,int){return socket_send(p,n);}
''',
            }
            stubs.pop("cJSON.h")
            cjson = SRC.parent / "managed_components/espressif__cjson/cJSON"
            for name, content in stubs.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            (root / 'check.cpp').write_text(r'''
#include <cassert>
#include <thread>
#include <future>
#include <vector>
#include "audio/asr/ws_asr.h"
#include "audio_output/sound_player.h"
#include <cstring>
WsASR* current=nullptr;
std::vector<std::thread> callbacks;
bool blocked=false;
int send_count=0;
int socket_send(const char*,int n){
    if(current){
        ++send_count;
        std::promise<void> done;
        auto ready=done.get_future();
        callbacks.emplace_back([p=std::move(done)]() mutable {
            current->getLastConfidence(); p.set_value();
        });
        if(ready.wait_for(std::chrono::milliseconds(100))!=std::future_status::ready) blocked=true;
    }
    return n;
}
void join(){for(auto& t:callbacks)t.join();callbacks.clear();}
int main(){
    WsASR asr("ws://gateway:8765","SB1");assert(asr.init());
    current=&asr;asr.setSourceNodeId("AB1");
    assert(asr.start());join();
    short pcm[600]={};assert(asr.feedAudio(pcm,600));join();
    asr.stop();join(); // includes partial PCM flush, then STOP
    assert(send_count==4);
    assert(!blocked && "WsASR receive-state mutex held across WebSocket send");
    current=nullptr;
    int followups=0;
    asr.registerFollowupCallback([&](const std::string& command){
        assert(playback_finished); assert(command=="listen"); ++followups;
    });
    auto receive=[](const char* json){
        esp_websocket_event_data_t data{1,json,(int)strlen(json)};
        connected_client->handler(connected_client->arg,"",WEBSOCKET_EVENT_DATA,&data);
    };
    receive(R"({"type":"audio_end","follow_up":true,"follow_up_command":"listen"})");
    assert(followups==0);
    receive(R"({"type":"audio_start","format":"pcm"})");
    receive(R"({"type":"audio_end","follow_up":true,"follow_up_command":"listen"})");
    assert(followups==1);
    receive(R"({"type":"audio_end","follow_up":true,"follow_up_command":"listen"})");
    assert(followups==1); // repeated END must not reopen microphone

}
''')
            subprocess.run(['g++', '-std=c++17', '-pthread', '-I', str(root), '-I', str(SRC),
                            '-I', str(cjson), str(cjson / 'cJSON.c'),
                            str(root / 'check.cpp'), str(SRC / 'audio/asr/ws_asr.cpp'),
                            '-o', str(root / 'check')], check=True)
            subprocess.run([str(root / 'check')], check=True, timeout=5)
