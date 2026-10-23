"""Exercise the actual capture loop with deterministic I2S and WakeNet boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/ActionBox_V2/src'

class VoiceCaptureTest(unittest.TestCase):
    def test_wake_gate_and_capture_without_background_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub = r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cassert>
#include <cstdlib>
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
inline int reads=0, read_limit=210, detects=0, wake_at=0, kws_calls=0, starts=0,chunks=0,ends=0;
inline int i2s_channel_read(void*,void*p,size_t n,size_t*out,int){if(reads++>=read_limit)throw Done{};memset(p,0,n);*out=n;return 0;}
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
inline int espnow_transport_send(const uint8_t*p,size_t){if(*p==0x20)++starts;else if(*p==0x21)++chunks;else if(*p==0x22)++ends;return 0;}
'''
            (root/'host.h').write_text(stub)
            for name in ['sdkconfig.h','esp_err.h','esp_log.h','esp_timer.h','esp_heap_caps.h','esp_wn_iface.h','esp_wn_models.h','model_path.h','board_pins.h','led_driver.h','espnow_transport.h','freertos/FreeRTOS.h','freertos/task.h','driver/i2s_std.h','driver/gpio.h']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "host.h"\n')
            (root/'check.cpp').write_text(r'''
#include "host.h"
#include "voice_capture.h"
#include "kws/kws_engine.h"
extern "C" esp_err_t kws_engine_init(){return 0;}
extern "C" void kws_engine_feed_samples(const int16_t*,size_t){}
extern "C" bool kws_engine_step(int*,float*){++kws_calls;return false;}
int main(){
 assert(voice_capture_init()==ESP_OK);
 assert(!voice_capture_request_followup()); // cannot start an unsolicited session
 try{capture_task(nullptr);}catch(Done&){}
 assert(detects>90 && "WakeNet must receive continuous 16 kHz audio");
 assert(kws_calls==0 && "Observation inference must not block microphone capture");
 assert(!voice_capture_is_streaming() && starts==0 && chunks==0);
 reads=0;detects=0;wake_at=1;read_limit=250;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==2 && chunks>0 && ends==3);
 assert(!voice_capture_is_streaming());
 assert(voice_capture_request_followup());
 reads=0;detects=0;wake_at=0;read_limit=450;
 try{capture_task(nullptr);}catch(Done&){}
 assert(starts==4 && ends==6 && !voice_capture_is_streaming());
 capture_time+=61000000;
 assert(!voice_capture_request_followup()); // expired wake-word session
}
''')
            binary=root/'check'
            subprocess.run(['g++','-std=c++20','-I'+str(root),'-I'+str(SRC/'audio'),'-I'+str(SRC/'protocol'),'-I'+str(SRC/'config'),'-I'+str(SRC/'drivers/relay'),'-I'+str(SRC/'drivers/current_sensor'),str(root/'check.cpp'),str(SRC/'audio/voice_capture.cpp'),'-o',str(binary)],check=True,text=True)
            subprocess.run([str(binary)],check=True,text=True)

if __name__=='__main__':unittest.main()
