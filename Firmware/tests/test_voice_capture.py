"""Exercise the actual capture loop with deterministic I2S and WakeNet boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/ActionBox_V2/src'

class VoiceCaptureTest(unittest.TestCase):
    def test_wake_gate_and_capture_without_kws_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub = r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cassert>
#include <cstdlib>
#include <vector>
using esp_err_t=int;
constexpr int ESP_OK=0, ESP_ERR_NO_MEM=1, pdPASS=1;
inline const char* esp_err_to_name(int){return "error";}
#define ESP_LOGI(...)
#define ESP_LOGW(...)
#define ESP_LOGD(...)
#define ESP_LOGE(...)
#define pdMS_TO_TICKS(n) (n)
#define CONFIG_ACTIONBOX_ESPNOW_CHANNEL 11
inline void vTaskDelay(int){}
inline void vTaskDelete(void*){}
inline void (*capture_task)(void*);
inline int xTaskCreatePinnedToCore(void(*f)(void*),const char*,int,void*,int,void*,int){capture_task=f;return pdPASS;}
inline int64_t capture_time=1000000;
inline int64_t esp_timer_get_time(){return capture_time;}
#define BOARD_MIC_I2S_PORT 0
#define BOARD_PIN_MIC_BCLK 47
#define BOARD_PIN_MIC_WS 48
#define BOARD_PIN_MIC_DIN 8
constexpr int GPIO_PULLDOWN_ONLY=0;
inline void gpio_set_pull_mode(int,int){}
using i2s_chan_handle_t=void*;
constexpr int I2S_ROLE_MASTER=0,I2S_GPIO_UNUSED=-1,I2S_DATA_BIT_WIDTH_32BIT=32,I2S_SLOT_MODE_STEREO=2;
struct i2s_chan_config_t{int id,role,dma_desc_num,dma_frame_num;bool auto_clear;};
struct i2s_std_config_t{int clk_cfg,slot_cfg;struct{int mclk,bclk,ws,dout,din;struct{bool mclk_inv,bclk_inv,ws_inv;}invert_flags;}gpio_cfg;};
#define I2S_STD_CLK_DEFAULT_CONFIG(n) (n)
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(a,b) (a)
inline int i2s_new_channel(const i2s_chan_config_t*,void*,void**p){*p=(void*)1;return 0;}
inline int i2s_channel_init_std_mode(void*,const i2s_std_config_t*){return 0;}
inline int i2s_channel_enable(void*){return 0;}
struct Done{};
enum AudioMode { AUDIO_SILENCE, AUDIO_LOW_NOISE, AUDIO_SPEECH };
inline AudioMode audio_mode = AUDIO_LOW_NOISE;
inline uint32_t audio_sample_idx = 0;
inline int reads=0, read_limit=210, detects=0, wake_at=0, starts=0,chunks=0,ends=0,wakes=0;
inline std::vector<std::vector<uint8_t>> sent_chunks_payload;
inline int duplicate_chunk_count = 0;
inline int i2s_channel_read(void*,void*p,size_t n,size_t*out,int){
 if(reads++>=read_limit)throw Done{};
 int32_t* buf=(int32_t*)p;
 size_t count=n/sizeof(int32_t);
 for(size_t i=0;i<count;i+=2){
  int16_t val=0;
  if(audio_mode==AUDIO_SPEECH){
   val=((audio_sample_idx/8)%2==0)?10000:-10000;
  }else if(audio_mode==AUDIO_LOW_NOISE){
   val=((audio_sample_idx/8)%2==0)?30:-30;
  }
  audio_sample_idx++;
  buf[i]=((int32_t)val)<<14;
  buf[i+1]=((int32_t)val)<<14;
 }
 *out=n;
 return 0;
}
struct model_iface_data_t{};
struct srmodel_list_t{};
constexpr int DET_MODE_90=90,WAKENET_DETECTED=1;
#define ESP_WN_PREFIX "wn"
inline srmodel_list_t* esp_srmodel_init(const char*){static srmodel_list_t m;return &m;}
inline char* esp_srmodel_filter(srmodel_list_t*,const char*,const char*){static char n[]="wn9_hiesp";return n;}
struct esp_wn_iface_t{model_iface_data_t*(*create)(const char*,int);int(*get_samp_chunksize)(model_iface_data_t*);int(*get_samp_rate)(model_iface_data_t*);int(*detect)(model_iface_data_t*,int16_t*);};
inline const esp_wn_iface_t* esp_wn_handle_from_name(const char*){static esp_wn_iface_t w{
 [](const char*,int)->model_iface_data_t*{static model_iface_data_t m;return &m;},
 [](model_iface_data_t*){return 512;},[](model_iface_data_t*){return 16000;},
 [](model_iface_data_t*,int16_t*){return ++detects==wake_at?WAKENET_DETECTED:0;}};return &w;}
enum LedDriverPattern{LED_PATTERN_OFF,LED_PATTERN_ON};
inline void led_set_pattern(int,LedDriverPattern){}
inline int espnow_transport_send(const uint8_t*p,size_t len){
 if(*p==0x20)++starts;
 else if(*p==0x21){
  ++chunks;
  if(len>4){
   std::vector<uint8_t> payload(p+4, p+len);
   bool non_zero=false;
   for(uint8_t b:payload){if(b!=0){non_zero=true;break;}}
   if(non_zero && !sent_chunks_payload.empty() && sent_chunks_payload.back()==payload){
    ++duplicate_chunk_count;
   }
   sent_chunks_payload.push_back(std::move(payload));
  }
 }
 else if(*p==0x22)++ends;
 else if(*p==0x24){assert(len==6 && p[1]<=1);++wakes;}
 return 0;
}
'''
            (root/'host.h').write_text(stub)
            for name in ['sdkconfig.h','esp_err.h','esp_log.h','esp_timer.h','esp_heap_caps.h','esp_wn_iface.h','esp_wn_models.h','model_path.h','board_pins.h','led_driver.h','espnow_transport.h','freertos/FreeRTOS.h','freertos/task.h','driver/i2s_std.h','driver/gpio.h']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "host.h"\n')
            (root/'check.cpp').write_text(r'''
#include "host.h"
#include "voice_capture.h"
int main(){
 assert(voice_capture_init()==ESP_OK);
 assert(!voice_capture_request_followup()); // cannot start an unsolicited session
 try{capture_task(nullptr);}catch(Done&){}
 assert(detects>90 && "WakeNet must receive continuous 16 kHz audio");
 assert(!voice_capture_is_streaming() && starts==0 && chunks==0);
 reads=0;detects=0;wake_at=1;read_limit=13;
 try{capture_task(nullptr);}catch(Done&){}
 // Wake word detected: session is active, but energy comparison hasn't cut words yet
 assert(starts==0 && chunks==0 && ends==0 && voice_capture_is_streaming());
 assert(wakes==2); // Both wake announcements precede the first VAD/PCM frame.

 // Verify followup request succeeds while session is active and extends deadline:
 // Original deadline: capture_time (1000000) + 5000000 = 6000000.
 capture_time = 5500000;
 assert(voice_capture_request_followup() && "Followup request must succeed while session active");
 // New deadline is now 5500000 + 5000000 = 10500000.
 // Advance past original deadline: session must remain active
 capture_time = 7000000;
 reads=0;detects=0;wake_at=0;read_limit=50;audio_mode=AUDIO_LOW_NOISE;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==0 && chunks==0 && ends==0 && voice_capture_is_streaming());

 // Feeding high-energy samples (rms >= speech_thresh) triggers starts == 2 and chunks begin streaming
 audio_mode=AUDIO_SPEECH;
 reads=0;detects=0;wake_at=0;read_limit=25;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==2 && chunks>0 && ends==0 && voice_capture_is_streaming());
 // Verify no duplicate chunks were emitted at speech onset
 assert(duplicate_chunk_count==0 && "No duplicate chunks should be emitted");

 // A short pause must not split the utterance into individual words.
 audio_mode=AUDIO_SILENCE;
 reads=0;detects=0;wake_at=0;read_limit=25;
 try{capture_task(nullptr);}catch(Done&){}
 assert(ends==0 && voice_capture_is_streaming());
 // Only the full utterance silence endpoint closes the stream.
 reads=0;detects=0;wake_at=0;read_limit=125;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==2 && ends==3);
 assert(duplicate_chunk_count==0);
 assert(!voice_capture_is_streaming());

 // Session deadline was extended by 4s to catch next word; advance time to trigger session timeout
 capture_time+=5000000;
 reads=0;detects=0;wake_at=0;read_limit=5;
 try{capture_task(nullptr);}catch(Done&){}
 assert(!voice_capture_is_streaming());

 // Follow-up session test
 assert(voice_capture_request_followup());
 reads=0;detects=0;wake_at=0;read_limit=5;audio_mode=AUDIO_LOW_NOISE;
 try{capture_task(nullptr);}catch(Done&){}
 assert(voice_capture_is_streaming() && starts==2 && ends==3);
 assert(wakes==2); // Automatic follow-up must not play another wake chime.
 audio_mode=AUDIO_SPEECH;
 reads=0;detects=0;wake_at=0;read_limit=25;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==4 && chunks>0 && voice_capture_is_streaming());
 assert(duplicate_chunk_count==0);
 audio_mode=AUDIO_SILENCE;
 reads=0;detects=0;wake_at=0;read_limit=125;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==4 && ends==6);
 assert(duplicate_chunk_count==0);
 capture_time+=61000000;
 reads=0;detects=0;wake_at=0;read_limit=5;
 try{capture_task(nullptr);}catch(Done&){}
 assert(!voice_capture_is_streaming());
 assert(!voice_capture_request_followup()); // expired wake-word session

 // Button trigger test: sets s_wake_session_us and permits follow-up
 voice_capture_start_streaming(WAKE_TRIGGER_BUTTON);
 assert(wakes==4);
 assert(voice_capture_is_streaming());
 assert(voice_capture_request_followup());
 voice_capture_stop_streaming();
 assert(!voice_capture_is_streaming());
 // Follow-up within 60s of button press is permitted
 assert(voice_capture_request_followup());
 reads=0;detects=0;wake_at=0;read_limit=5;audio_mode=AUDIO_LOW_NOISE;
 try{capture_task(nullptr);}catch(Done&){}
 assert(voice_capture_is_streaming());
 voice_capture_stop_streaming();
 assert(!voice_capture_is_streaming());
 capture_time+=61000000;
 assert(!voice_capture_request_followup()); // expired button session
}
''')
            binary=root/'check'
            subprocess.run(['g++','-std=c++20','-I'+str(root),'-I'+str(SRC/'audio'),'-I'+str(SRC/'protocol'),'-I'+str(SRC/'config'),'-I'+str(SRC/'drivers/relay'),'-I'+str(SRC/'drivers/current_sensor'),str(root/'check.cpp'),str(SRC/'audio/voice_capture.cpp'),'-o',str(binary)],check=True,text=True)
            subprocess.run([str(binary)],check=True,text=True)

if __name__=='__main__':unittest.main()
