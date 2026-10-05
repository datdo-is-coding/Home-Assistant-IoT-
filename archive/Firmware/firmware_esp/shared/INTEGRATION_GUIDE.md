# Firmware tích hợp Compact Protocol (WebSocket + MQTT)

## Tóm tắt
ESP32-S3 (voice) đã giữ **1 WS tới Pi4:8765** cho mic PCM. Relay bây giờ đi **chung socket đó**
bằng TEXT frame `{"t":"rl","ch":1,"s":1,"seq":n}` (~27B) — không mở thêm socket, không vỡ luồng mic.
Node relay thuần (WROOM) không có WS vẫn dùng MQTT `smarthome/cmd/{id}` với cùng payload.

Firmware mẫu nằm ở `shared/node_prov.{h,c}` — dùng chung cho mọi node. Chỉ cần copy 2 file
vào `Esp32S3_Master/include` & `src` (và WROOM project tương tự) + thêm 3 patch dưới đây.

---

## 1) Tích hợp NVS provision (boot)

Trong `main.c` — trước khi gọi `mqtt_relay_init` / `ws_audio_client_init`:

```c
#include "node_prov.h"

void app_main(void) {
    nvs_flash_init();
    // GPIO relay đã init trong node_prov (hoặc gọi prov_load trước)
    gpio_config(... RL1=4, RL2=5 active-LOW ...); // nếu chưa có
    bool hasCfg = prov_load();
    if (!hasCfg) ESP_LOGW("MAIN","Fresh node — will announce as PENDING");
    // các init còn lại ...
}
```

`g_prov.node_id / room / rl1 / rl2 / cfg_version` sẵn sàng ngay sau `prov_load()`.

## 2) Patch ws_audio_client.c — nhận relay ngay trên socket audio

Trong `handle_ws_text_message(const char *data, int len)` (dòng ~275), thêm nhánh compact trên cùng:

```c
static void handle_ws_text_message(const char *data, int len) {
    // --- compact relay: {"t":"rl","ch":1,"s":1,"seq":12} ---
    cJSON *root = cJSON_ParseWithLength(data, len);
    if (!root) return;
    cJSON *t = cJSON_GetObjectItem(root, "t");
    if (t && cJSON_IsString(t)) {
        if (strcmp(t->valuestring, "rl")==0) {
            int ch  = cJSON_GetObjectItem(root,"ch")->valueint;
            int s   = cJSON_GetObjectItem(root,"s")->valueint;
            int seq = cJSON_GetObjectItem(root,"seq") ? cJSON_GetObjectItem(root,"seq")->valueint : 0;
            int rc = prov_handle_relay_cmd(ch, s, seq);
            if (rc==0) {
                char ack[96]; int n = prov_build_ack(ack, sizeof(ack), seq);
                esp_websocket_client_send_text(ws_client, ack, n, pdMS_TO_TICKS(500));
            }
            cJSON_Delete(root); return;
        }
        if (strcmp(t->valuestring,"cfg")==0) {
            const char *nid = cJSON_GetObjectItem(root,"id")->valuestring;
            const char *room= cJSON_GetObjectItem(root,"room")->valuestring;
            const char *r1  = cJSON_GetObjectItem(root,"rl1")?cJSON_GetObjectItem(root,"rl1")->valuestring:"";
            const char *r2  = cJSON_GetObjectItem(root,"rl2")?cJSON_GetObjectItem(root,"rl2")->valuestring:"";
            int v = cJSON_GetObjectItem(root,"v")->valueint;
            prov_save_cfg(nid, room, r1, r2, (uint16_t)v);
            esp_restart(); // áp dụng config mới
            cJSON_Delete(root); return;
        }
        // "hello_ok" / "pending" từ gateway có thể bỏ qua (chỉ để sync state WS)
    }
    cJSON_Delete(root);
    // ... phần legacy audio_start/audio_end/transcript cũ giữ nguyên bên dưới ...
}
```

**Vì sao không vỡ audio:** ESP-IDF `esp_websocket_client` phân biệt TEXT vs BINARY bằng opcode WS;
PCM mic là `BINARY`, lệnh relay là `TEXT` → xen kẽ an toàn, không chen vào giữa frame PCM.
Gateway gửi TEXT relay (~27B) trong khi Pi đang stream PCM BINARY 2048B chunk — 2 loại frame cùng
TCP socket nhưng tách opcode, phí ~30B nên jitter không đo được.

## 3) Hello heartbeat (WS + MQTT)

Sau khi WS `CONNECTED` và sau mỗi 60s, gửi:

```c
char hello[160];
int rssi = ...; char ip[16]; uint32_t up = esp_timer_get_time()/1000000;
int n = prov_build_hello(hello, sizeof(hello), mac_str, FW_VER, ip, rssi, up);
esp_websocket_client_send_text(ws_client, hello, n, pdMS_TO_TICKS(500));
// đồng thời publish MQTT smarthome/hello (cho node không giữ WS)
esp_mqtt_client_publish(mqtt_client, "smarthome/hello", hello, 0, 1, 0);
```

Chưa provision (`cfg:null`) → Gateway đẩy vào **pending** và WebUI hiện form đăng ký.

## 4) Patch mqtt_relay.c — compact sub & NVS

```c
// subscribe compact
esp_mqtt_client_subscribe(mqtt_client, "smarthome/cmd/" NODE_ID, 1);
esp_mqtt_client_subscribe(mqtt_client, "smarthome/cfg/#", 1); // cfg/{mac} & cfg/{id}

// data callback
void handle_command(const char *data, int len) {
    cJSON *r=cJSON_ParseWithLength(data, len);
    if(!r) return;
    cJSON *t=cJSON_GetObjectItem(r,"t");
    if(t && strcmp(t->valuestring,"rl")==0) {
        int ch=cJSON_GetObjectItem(r,"ch")->valueint;
        int s=cJSON_GetObjectItem(r,"s")->valueint;
        int seq=cJSON_GetObjectItem(r,"seq")?cJSON_GetObjectItem(r,"seq")->valueint:0;
        if(prov_handle_relay_cmd(ch,s,seq)==0){
            char ack[96]; prov_build_ack(ack,sizeof(ack),seq);
            esp_mqtt_client_publish(mqtt_client, "smarthome/status/" NODE_ID, ack, 0, 1, 0);
        }
    } else if(t && strcmp(t->valuestring,"cfg")==0) {
        prov_save_cfg(cJSON_GetObjectItem(r,"id")->valuestring,
                      cJSON_GetObjectItem(r,"room")->valuestring,
                      cJSON_GetObjectItem(r,"rl1")?cJSON_GetObjectItem(r,"rl1")->valuestring:"",
                      cJSON_GetObjectItem(r,"rl2")?cJSON_GetObjectItem(r,"rl2")->valuestring:"",
                      cJSON_GetObjectItem(r,"v")->valueint);
        esp_restart();
    } else {
        // legacy {channel:"ch1", action:"turn_on"}
    }
    cJSON_Delete(r);
}
```

## 5) Wiring — không đổi
RL1 GPIO4 = đèn, RL2 GPIO5 = quạt (Active-LOW, PC817 cathode).

## 6) Kiểm tra nhanh
- Node mới boot → `{"t":"hello","mac":"..","cfg":null}` xuất hiện ở WebUI `Pending` trong <1s.
- Web đăng ký `livingroom / rl1=light / rl2=fan` → node nhận `{"t":"cfg",...}`, reboot, hello mới có `id=livingroom-node01`.
- Nói "bật quạt phòng khách" → WebUI log `livingroom-node01-fan: turn_on → success`, relay quạt chộp ngay, loa phát TTS.
- Ngắt WS (rút Wi-Fi test) → Gateway tự fallback MQTT, relay vẫn bấm được từ web.
