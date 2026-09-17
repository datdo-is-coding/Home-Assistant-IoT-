# Khung dữ liệu Gateway ↔ ESP32 — Nhẹ nhất, đầy đủ, dùng chung WebSocket audio

> Nguyên tắc: **đường PCM nhị phân giữ nguyên 100%** (không nhét control byte vào PCM).
> Điều khiển relay đi bằng **WebSocket TEXT frame (opcode 0x1)** xen kẽ giữa các BINARY frame —
> TCP/WS cho phép xen kẽ nên không nghẽn, không vỡ luồng mic đang chạy ổn định.
> Node không có WS (node relay thuần) dùng MQTT với cùng cấu trúc rút gọn.

## 1. Quy ước đặt tên (bắt buộc để chống ảo giác LLM)

```
fullname = {room}-{node_short}-{dev_short}
ví dụ: livingroom-node01-light | livingroom-node01-fan
       bedroom-node01-light    | bedroom-node01-fan
```

- `room`: slug không dấu: `livingroom | bedroom | kitchen | ...` (+ alias tiếng Việt).
- `node_short`: `node01 | node02 | master` (duy nhất trong room).
- `node_id`: `livingroom-node01` (= room + node_short). Là MQTT topic + WS id.
- `dev_short`: `light | fan | pump | ...` (1 từ, không dấu).
- ESP32 **phải nhớ** `rl1_name / rl2_name` trong NVS và **echo lại** mỗi lần hello/status.
  Gateway là source-of-truth, nhưng bản echo giúp phát hiện lệch cấu hình (`cfg_version`).

## 2. Tổng quan 3 kênh (chọn theo loại node)

| Node | Kênh điều khiển chính | Kênh fallback | Telemetry |
|---|---|---|---|
| Voice node (ESP32-S3, đã giữ WS audio 8765) | **WS TEXT** `{"t":"rl",...}` (~25 byte) | MQTT `smarthome/cmd/{node_id}` | MQTT `smarthome/tele/{node_id}` |
| Relay node thuần (ESP32/WROOM) | MQTT `smarthome/cmd/{node_id}` | — | MQTT + ESP-NOW nội bộ |

## 3. ESP32 → Gateway

### 3.1. HELLO (khi boot + mỗi 60s, WS TEXT hoặc MQTT `smarthome/hello`)

Chưa provision (node mới → Gateway đẩy vào hàng chờ WebUI):

```json
{"t":"hello","mac":"30:ED:A0:BD:69:D4","fw":"1.2.0","ip":"192.168.11.181","rssi":-62,"rl":[0,0],"cfg":null}
```

Đã provision (nhẹ, ~110 byte):

```json
{"t":"hello","id":"livingroom-node01","rl":[0,1],"cfg":3,"rssi":-62,"up":12345}
```

`cfg` = config_version do Gateway cấp. `cfg:null` = node mới.
`rl` = trạng thái thực tế GPIO [RL1, RL2] để Gateway đồng bộ UI ngay.

### 3.2. ACK / STATUS (sau khi thực thi lệnh, WS TEXT hoặc `smarthome/status/{node_id}`)

```json
{"t":"ack","id":"livingroom-node01","rl":[1,0],"seq":12}
```

`seq` echo lại lệnh để verify vòng kín + trừ trùng lệnh.

### 3.3. TELEMETRY (MQTT `smarthome/tele/{node_id}`, 2s/lần, key rút gọn)

```json
{"p":55.2,"v":221.5,"i":0.25,"e":1.203,"f":50.0,"pf":0.92}
```

p=P(W), v=V, i=A, e=kWh, f=Hz, pf=cosφ. Node không có PZEM gửi `{}`.

## 4. Gateway → ESP32

### 4.1. PROVISION / CẤU HÌNH (WS TEXT hoặc MQTT `smarthome/cfg/{mac}`, QoS1 + retain)

WebUI đăng ký xong → Gateway gửi 1 lần, node lưu NVS + reboot mềm:

```json
{"t":"cfg","id":"livingroom-node01","room":"livingroom","rl1":"light","rl2":"fan","v":3}
```

~75 byte. `v` = config_version, node lưu và gửi lại trong hello sau này.
Tên đầy đủ suy ra: `livingroom-node01-light`, `livingroom-node01-fan`.

### 4.2. RELAY CMD (WS TEXT trực tiếp trên socket audio, hoặc MQTT `smarthome/cmd/{node_id}`)

```json
{"t":"rl","ch":1,"s":1,"seq":12}
```

- `ch`: 1 | 2 (RL1/RL2). Không gửi tên string để nhẹ + tránh sai chính tả.
- `s`: 1=ON (kéo Active-LOW trong firmware), 0=OFF.
- `seq`: tăng đơn điệu, node bỏ qua seq trùng/lùi (chống lặp MQTT retain).
- Tổng **~27 byte** — rẻ hơn 1 frame PCM 640 byte ~24 lần, không ảnh hưởng audio.

Bản đầy đủ cho debug/log (gateway tự expand, không gửi xuống node):

```json
{"node_id":"livingroom-node01","fullname":"livingroom-node01-fan","channel":"ch2","gpio":5,"action":"turn_on"}
```

### 4.3. TTS AUDIO (giữ nguyên, không đổi)

```
Pi → ESP32 TEXT {"type":"audio_start","format":"pcm","sample_rate":16000,"size":N}
Pi → ESP32 BINARY [2048 byte PCM] ... sleep 35ms
Pi → ESP32 TEXT {"type":"audio_end"}
```

Relay TEXT frame được phép xen giữa các BINARY chunk — ESP32 phân biệt bằng opcode nên loa không rè.

## 5. Ví dụ round-trip hoàn chỉnh

```
1. Node mới boot → WS TEXT {"t":"hello","mac":"AA:..","cfg":null,...}
2. Gateway → WebUI SSE `pending_node` → user nhập: room=bedroom, RL1=light, RL2=fan
3. Gateway → node {"t":"cfg","id":"bedroom-node01","room":"bedroom","rl1":"light","rl2":"fan","v":1}
4. Node lưu NVS → reboot → hello {"t":"hello","id":"bedroom-node01","rl":[0,0],"cfg":1}
5. User nói "bật quạt phòng khách" → ASR → LLM {action:on, device:fan, room:livingroom}
   → resolver livingroom-node01/ch2 → WS {"t":"rl","ch":2,"s":1,"seq":7}
6. Node kéo GPIO5 LOW → {"t":"ack","id":"livingroom-node01","rl":[0,1],"seq":7}
7. Gateway verify ΔP + phát TTS "Đã bật quạt phòng khách ạ."
```

## 6. Vì sao không tách socket riêng?

- ESP32-S3 chỉ giữ 1 TLS/TCP WS ổn định tới Pi4:8765. Mở thêm socket = thêm RAM, thêm reconnect race.
- TEXT frame điều khiển <30 byte, tần suất thấp (vài giây/lần), PCM 640 byte/20ms chiếm băng thông chính — xen 1 TEXT frame không gây jitter đo được.
- Node relay thuần không có WS vẫn chạy MQTT song song, cùng schema rút gọn.
