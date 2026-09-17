# DTV Smart Home & Energy IoT Hub — Tài Liệu Kiến Trúc & Thông Tin Hệ Thống Toàn Diện

> **Tài liệu cấu hình và hiện trạng kỹ thuật hệ thống**  
> **Dự án:** Hệ Thống Nhà Thông Minh Điều Khiển Giọng Nói Tiếng Việt & Giám Sát Năng Lượng Thông Minh Vòng Lặp Kín (Closed-Loop IoT).  
> **Cập nhật:** Ngày 17 tháng 09 năm 2026.

---

## 1. Tổng Quan Kiến Trúc Hệ Thống (System Overview)

Hệ thống được thiết kế theo mô hình **Điện toán phân tán (Edge-to-Gateway Computing)** kết hợp giữa vi điều khiển nhúng thời gian thực và máy chủ biên xử lý Trí tuệ Nhân tạo cục bộ (Local AI Edge Gateway).

```
   ┌────────────────────────────────────────────────────────┐
   │         ESP32 WROOM Energy Slave (PZEM-004T)           │
   │  - Đo V, I, P, E, Freq, PF lưới điện AC 220V           │
   └───────────────────────────┬────────────────────────────┘
                               │ ESP-NOW (Không dây ~1ms)
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │            ESP32-S3 Voice Master & Relay Hub           │
   │  - WakeNet "Hi ESP" (ESP-SR Offline)                   │
   │  - Mic INMP441 + Loa MAX98357A (I2S DMA)               │
   │  - 2-CH Relay Active-LOW (GPIO 4: Đèn, GPIO 5: Quạt)   │
   │  - Bộ tổng hợp âm báo Sine Synthesizer (Chime, Ding)   │
   │  - Mô hình TinyML AI phân tích bất thường sóng tải     │
   └───────────────▲────────────────────────▲───────────────┘
                   │                        │
       WebSocket   │ Audio Stream (16kHz)   │ MQTT (Control & Telemetry)
       Port 8765   │ Chunks / PCM           │ Port 1883 (EMQX)
                   ▼                        ▼
   ┌────────────────────────────────────────────────────────┐
   │       Raspberry Pi 4 Gateway (192.168.11.29)           │
   │  - ASR Engine: Sherpa-ONNX (Zipformer Transducer VN)   │
   │  - LLM Engine: llama-server + Qwen2.5-3B-Instruct      │
   │  - TTS Engine: Microsoft EdgeTTS (Hoài My Neural)      │
   │  - Closed-Loop Verifier: Xác thực biến thiên công suất │
   │  - 3-Tier Memory Engine: SQLite (Học mẫu thói quen)    │
   │  - Time-series DB: InfluxDB v2 (Đồ thị năng lượng)     │
   │  - Web Monitor Dashboard: Port 8000 (SSE Realtime)     │
   └────────────────────────────────────────────────────────┘
```

---

## 2. Phần Cứng & Sơ Đồ Đấu Nối Chi Tiết (Hardware Specifications)

### 2.1. ESP32-S3 Voice Master Node
* **Vi điều khiển:** ESP32-S3-WROOM-1 / ESP32-S3 N16R8 (16MB Flash, 8MB Octal PSRAM).
* **Địa chỉ MAC Wi-Fi STA:** `30:ED:A0:BD:69:D4`.
* **Địa chỉ IP mạng nội bộ:** `192.168.11.181` (SSID: `XIAOMI`).

#### Bảng Ánh Xạ Chân GPIO (Pinout Mapping):
| Chức năng | Chân GPIO | Chuẩn giao tiếp | Chi tiết đấu nối phần cứng |
| :--- | :--- | :--- | :--- |
| **Microphone INMP441** | **GPIO 15** | I2S0 BCLK | Bit Clock |
| | **GPIO 16** | I2S0 WS / LRC | Word Select (Left/Right Clock) |
| | **GPIO 8** | I2S0 DIN / SD | Serial Data IN (chuyển đổi 24-bit $\rightarrow$ 16-bit) |
| | *GND / 3.3V* | L/R Pin | Chọn kênh Trái (Left Channel) |
| **Speaker MAX98357A** | **GPIO 17** | I2S1 BCLK | Bit Clock phát loa |
| | **GPIO 18** | I2S1 WS / LRC | Word Select |
| | **GPIO 21** | I2S1 DOUT / DIN | Serial Data OUT từ ESP32 sang DAC |
| | **GPIO 2** | `SP_SD` | **Hardware Shutdown / Mute**. Mức `1`: Bật Amply; Mức `0`: Ngắt Amply về chế độ ngủ 0.01 µA để chống ù xì. |
| **Relay Kênh 1 (RL1)** | **GPIO 4** | GPIO Output | **Đèn phòng ngủ**. Kích vào Chân 2 (Cathode) Opto PC817 $\rightarrow$ **Active-LOW** (`0`: Bật, `1`: Tắt). |
| **Relay Kênh 2 (RL2)** | **GPIO 5** | GPIO Output | **Quạt phòng ngủ**. Kích vào Chân 2 (Cathode) Opto PC817 $\rightarrow$ **Active-LOW** (`0`: Bật, `1`: Tắt). |
| **LED RGB Thông Minh** | **GPIO 48** | RMT Driver | WS2812B NeoPixel tích hợp trên board hiển thị trạng thái hệ thống. |

---

### 2.2. ESP32 WROOM Energy Slave Node
* **Vi điều khiển:** ESP32-WROOM-32.
* **Cảm biến:** PZEM-004T v3.0 (giao tiếp qua UART phần cứng).
* **Thông số thu thập:**
  - Điện áp ($U$): 80 ~ 260 VAC.
  - Dòng điện ($I$): 0 ~ 100 A.
  - Công suất tức thời ($P$): 0 ~ 23 kW.
  - Điện năng tích lũy ($E$): 0 ~ 9999 kWh.
  - Tần số ($f$): 45 ~ 65 Hz.
  - Hệ số công suất ($\cos\varphi$ / PF): 0.00 ~ 1.00.
* **Giao thức đẩy dữ liệu:** Gói tin nhị phân chuẩn `esp_now_packet_t` gửi về Master định kỳ mỗi chu kỳ polling hoặc gửi ngay khi có biến động tải.

---

### 2.3. Raspberry Pi 4 Gateway
* **Phần cứng:** Raspberry Pi 4 Model B (4GB / 8GB RAM), CPU Broadcom BCM2711 Quad-core Cortex-A72 @ 1.5/1.8GHz.
* **Hệ điều hành:** Raspberry Pi OS 64-bit (Debian GNU/Linux).
* **Địa chỉ IP cố định:** `192.168.11.29`.
* **Dịch vụ mạng:**
  - Cổng `1883`: MQTT Broker (EMQX).
  - Cổng `8080`: llama-server (`llama.cpp` OpenAI API).
  - Cổng `8765`: Audio Streaming WebSocket Server.
  - Cổng `8000`: Web Monitor Dashboard (FastAPI + SSE Stream).
  - Cổng `8086`: InfluxDB v2 Time-series Database.

---

## 3. Kiến Trúc Phân Tích Dữ Liệu & Trí Tuệ Nhân Tạo (AI & Data Pipeline)

### 3.1. Nhận dạng Tiếng nói (Speech-to-Text — ASR)
* **Thư viện:** `sherpa-onnx` (ONNX Runtime biên dịch cho ARM64).
* **Mô hình:** **Zipformer Transducer tiếng Việt**.
* **Đặc tả tệp mô hình (`/home/pi4/smarthome/models`):**
  - `encoder.onnx`: Trích xuất đặc trưng âm học đa tầng.
  - `decoder.onnx`: Giải mã ngôn ngữ dựa trên ngữ cảnh chuỗi ký tự trước.
  - `joiner.onnx`: Hợp nhất xác suất âm học và ngôn ngữ.
  - `tokens.txt`: Bảng mã từ vựng âm tiết tiếng Việt có dấu.
* **Hiệu năng:** Độ trễ giải mã < 350ms trên CPU Pi 4 (2 threads), hỗ trợ phát hiện tiếng nói VAD tự động ngắt sau 1.5s im lặng.

---

### 3.2. Hiểu Ngôn Ngữ Tự Nhiên & Trích Xuất Lệnh (Hybrid NLU — Cloud & Edge AI)

Hệ thống triển khai **Kiến trúc Hybrid 2 tầng song song (Parallel Hybrid Architecture)** với khả năng chuyển đổi mượt mà (Seamless Automatic Switching) giữa Trí tuệ Nhân tạo Đám mây và Mô hình Biên Cục bộ:

```
                      ┌───────────────────────────┐
                      │    Khẩu lệnh Tiếng Việt   │
                      │  "bật đèn phòng ngủ master" │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │    IntentEngine Router    │
                      └──────┬─────────────┬──────┘
                             │             │
        (Có mạng & có key)   │             │ (Mất mạng / Timeout >3.5s / Offline)
        ┌────────────────────┘             └────────────────────┐
        ▼                                                       ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│     TẦNG 1: CLOUD AI          │               │     TẦNG 2: EDGE LOCAL AI     │
│   Google Gemini 1.5 Flash     │  Fallback     │      Qwen2.5-3B-Instruct      │
│  - Phản hồi siêu tốc: ~0.35s  │ ────────────> │  - llama-server (llama.cpp)   │
│  - Ngữ cảnh: 1M tokens        │ (Tự động &    │  - Context: 1024 tokens       │
│  - Schema: JSON Strict        │  không lỗi)   │  - GBNF Grammar ép schema     │
│  - Hoàn toàn miễn phí         │               │  - Không cần mạng (100% riêng)│
└───────────────┬───────────────┘               └───────────────┬───────────────┘
                │                                               │
                └───────────────────────┬───────────────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ JSON Trích Xuất Ý Định Hợp Lệ │
                        │  {"action": "turn_on", ...}   │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │     LỚP 2: REGISTRY NLU       │
                        │ Phân giải node_id & channel   │
                        │      Chống ảo giác 100%       │
                        └───────────────────────────────┘
```

#### Tầng 1 — Cloud Primary Tier (Google Gemini 1.5 Flash):
* **Mô hình:** `gemini-1.5-flash` qua REST API trực tiếp (`httpx`), không phụ thuộc SDK nặng.
* **Tốc độ phản hồi:** **0.3s — 0.5s** (Cực kỳ nhạy, tức thì cho trải nghiệm giọng nói).
* **Đặc tả:** Tích hợp `responseMimeType: "application/json"`, nhiệt độ `0.0`.
* **Cấu hình:** Đặt `GEMINI_API_KEY=AIzaSy...` trong file `.env` (ở `Gateway/.env` hoặc `/home/pi4/.env`). Nếu chưa có key hoặc mạng chập chờn, hệ thống tự động nhảy sang Tầng 2 mà không ném lỗi ra người dùng.

#### Tầng 2 — Local Edge Fallback Tier (Qwen2.5-3B trên Raspberry Pi 4):
* **Runtime:** `llama-server` (`llama.cpp` ARM64 build) chạy service nền `llama-server.service`.
* **Mô hình:** **Qwen2.5-3B-Instruct (Q4_K_M)** (`/home/pi4/models/qwen2.5-3b-instruct-q4_k_m.gguf`, 2.04 GB, 3.09 tỷ tham số).
* **Tham số tối ưu hóa phần cứng Pi 4 (4GB RAM):**
  - Context size: `-c 1024` tokens (Mở rộng cửa sổ ngữ cảnh theo yêu cầu).
  - Slot processing: `-np 1` (Ép 1 slot đơn để loại bỏ hiện tượng tràn bộ nhớ swap, giữ dung lượng RAM vật lý 0B swap).
  - Luồng CPU: `-t 4` (Tận dụng 4 nhân Cortex-A72 @ 1.5GHz).
* **Bộ đệm ngữ cảnh (Prompt KV Cache):**
  - Kích hoạt `cache_prompt: True` trong `llama.cpp`. Lần gọi đầu tiên (cold start) đánh giá prompt mất ~70s, nhưng các lần gọi tiếp theo được tái sử dụng KV cache $\rightarrow$ thời gian phản hồi rút ngắn xuống chỉ còn **~34 giây**!
* **Ngữ pháp GBNF (Chống ảo giác tuyệt đối):**
  - Sử dụng GBNF Grammar ép LLM chỉ được phép sinh các token thiết bị (`"den"`, `"quat"`, ...) và phòng (`"phong_ngu"`, `"phong_khach"`, ...) đang thực tế tồn tại trong `device_registry.json`.

#### Tầng 3 — Registry Resolver & Ánh Xạ Phần Cứng:
* Khi nhận JSON từ LLM, hàm `find_node_by_device(device, location)` trong `registry_manager.py` sẽ đối chiếu với cơ sở dữ liệu `device_registry.json`.
* Tự động xử lý các trường hợp:
  - Khẩu lệnh chuẩn: *"bật đèn phòng ngủ"* $\rightarrow$ Node `esp32s3_master`, Channel `ch1` (GPIO 4).
  - Khẩu lệnh tắt: *"tắt quạt phòng ngủ"* $\rightarrow$ Node `esp32s3_master`, Channel `ch2` (GPIO 5).
  - Khẩu lệnh thiếu phòng: Tự động hỏi lại phòng hoặc chọn thiết bị phù hợp nhất.
  - Khẩu lệnh không tồn tại: Báo lỗi thân thiện thay vì gửi lệnh rác xuống relay.

---

### 3.3. Tổng Hợp Tiếng Nói (Text-to-Speech — TTS)
* **Động cơ:** `Microsoft EdgeTTS` (`vi-VN-HoaiMyNeural` giọng nữ chuẩn Hà Nội, fallback `vi-VN-NamMinhNeural`).
* **Xử lý âm thanh:** Chuyển đổi định dạng MP3 $\rightarrow$ Raw PCM (16kHz, 16-bit, Little-Endian Mono) bằng thư viện `pydub` và `ffmpeg`.
* **Kiểm soát luồng (Throttling):** Truyền qua WebSocket với từng chunk 2048 bytes (64ms âm thanh), nghỉ 35ms giữa các chunk (~1.8x tốc độ thời gian thực) giúp bộ đệm ESP32 hấp thụ liên tục mà không bị nghẽn mạng TCP hay sập WebSocket.

---

### 3.4. Xác Thực Vòng Lặp Kín (Closed-Loop Verification Engine)
Khác biệt hoàn toàn với các giải pháp IoT truyền thống (chỉ gửi lệnh một chiều), hệ thống triển khai thuật toán **Closed-loop Verification**:
1. Ghi nhận công suất trước lệnh: $P_{before}$.
2. Bắn lệnh bật/tắt relay qua MQTT.
3. Chờ phản hồi cảm biến và đo lại: $P_{after}$.
4. Tính độ lệch công suất: $\Delta P = P_{after} - P_{before}$.
5. Đánh giá:
   - Nếu $\Delta P > \max(0.3 \times P_{rated}, 3.0W) \rightarrow$ `SUCCESS` (Xác nhận tải thực tế đã khởi động).
   - Nếu $\Delta P \le 0 \rightarrow$ `FAILED` (Relay đóng nhưng không có dòng điện tiêu thụ $\rightarrow$ bóng đèn bị cháy hoặc thiết bị chưa cắm điện).
6. **Cơ chế dự phòng:** Đối với các node chỉ có relay đơn thuần chưa tích hợp cảm biến đo dòng PZEM (như `esp32s3_master`), hệ thống tự động nhận diện `before = 0` & `after = 0` để xác nhận thành công qua gói tin trạng thái relay, phản hồi tích cực ngay lập tức.

---

### 3.5. Bộ Nhớ 3 Tầng & Tự Học Thói Quen (3-Tier Memory Engine)
* **Tầng 1 — STM (Short-Term Memory):** Lưu trữ trên RAM các câu lệnh gần nhất để duy trì chuỗi ngữ cảnh đối thoại.
* **Tầng 2 — MTM (Medium-Term Memory):** SQLite Database (`/home/pi4/smarthome/memory.db`):
  - `command_log`: Lịch sử thời gian thực (Timestamp, Giờ trong ngày, Thứ trong tuần, Khẩu lệnh, Thiết bị, Khu vực, Công suất trước/sau, Kết quả verify).
  - `user_corrections`: Dữ liệu những lần người dùng sửa lại lệnh khi AI phân tích nhầm.
  - `power_baselines`: Bản ghi công suất tiêu thụ định mức thực tế (Avg, Min, Max).
* **Tầng 3 — LTM (Long-Term Memory / Machine Learning Patterns):**
  - Bảng `learned_patterns`: Thuật toán tự động gom cụm thói quen sinh hoạt (ví dụ: Người dùng thường xuyên bật quạt phòng ngủ vào lúc 22h tối các ngày trong tuần $\rightarrow$ nâng độ tin cậy `confidence` $\rightarrow$ tự động gợi ý hành động tự động hóa).

---

### 3.6. Mô Hình TinyML Trên ESP32-S3 (On-Device Inference)
Mô hình TinyML chạy song song trên Core 0 của ESP32-S3 phân tích đặc tính dạng sóng công suất:
* **Đỉnh vọt dòng khởi động:** $P > 800W$ và $\Delta P > 250W \rightarrow$ Phát hiện tải khởi động máy nén/động cơ điều hòa, máy bơm nước.
* **Hệ số $\cos\varphi$ thấp:** $PF < 0.80$ và $I > 0.4A \rightarrow$ Phát hiện tải cảm kháng (quạt, biến áp), đưa ra khuyến nghị gắn tụ bù tiết kiệm điện.
* **Tải ngầm (Standby Vampire Load):** $0 < P < 35W \rightarrow$ Phát hiện thiết bị ở chế độ chờ tiêu hao vô ích, khuyến nghị ngắt công tắc.

---

## 4. Hệ Thống Âm Báo Phản Hồi Loa (Audio Feedback Cues)

Hệ thống tích hợp bộ tổng hợp sóng sin thuần túy ([audio_feedback.c](file:///d:/Home-Assistant-IoT-/Firmware/firmware_esp/Esp32S3_Master/src/audio_feedback.c)) với các đường bao Envelope Ramp Attack/Decay để triệt tiêu hoàn toàn tiếng nổ "pop/click" của loa:

| Sự kiện hệ thống | Kiểu âm thanh | Tần số & Thời lượng | Mục đích trải nghiệm người dùng |
| :--- | :--- | :--- | :--- |
| **Server Connected** | Arpeggio 3 nốt thăng hoa | C5 (523Hz) $\rightarrow$ E5 (659Hz) $\rightarrow$ G5 (784Hz) | Báo hiệu ESP32 đã kết nối mạng Wi-Fi và WebSocket tới Pi 4 thành công. |
| **Wake Word ("Hi ESP")**| Ding! thanh thoát | A5 (880Hz) $\rightarrow$ C6 (1046Hz), 120ms | Xác nhận ESP32 đã nghe thấy từ khóa, sẵn sàng nhận lệnh. |
| **Listening Completed** | Tick nhẹ nhàng | E5 (659Hz), 60ms | Xác nhận đã thu âm xong câu lệnh của người dùng, bắt đầu xử lý. |
| **Error / Disconnected**| Âm trầm giáng cảnh báo | 330Hz $\rightarrow$ 220Hz, 250ms | Báo lỗi mất kết nối máy chủ hoặc sự cố hệ thống. |

> [!IMPORTANT]
> **Cơ chế Khóa Phần Cứng (Hardware Mutex):** Sử dụng `spk_hw_mutex` ngăn chặn hoàn toàn hiện tượng xung đột tài nguyên giữa tác vụ phát âm báo hệ thống và tác vụ phát giọng nói TTS, bảo vệ chân `SP_SD` không bị tắt nhầm giữa chừng.

---

## 5. Cấu Hình MQTT & Thiết Bị (Device Registry)

### 5.1. Định dạng Topics MQTT
* **Đăng ký:** `smarthome/register` (QoS 1)
* **Điều khiển:** `smarthome/command/{node_id}`
* **Trạng thái:** `smarthome/status/{node_id}`
* **Dữ liệu điện:** `smarthome/telemetry/{node_id}`
* **Cảnh báo:** `smarthome/alert`

### 5.2. Hồ Sơ Đăng Ký Node Phòng Ngủ (`esp32s3_master`)
```json
{
  "node_id": "esp32s3_master",
  "mac": "30:ED:A0:BD:69:D4",
  "area": "phong_ngu",
  "description": "ESP32-S3 Master Voice + 2-CH Relay Phòng Ngủ",
  "channels": {
    "ch1": {
      "device_type": "den",
      "description": "Đèn phòng ngủ",
      "gpio": 4,
      "rated_watts": 40.0,
      "aliases": ["den", "den_ngu", "den_phong_ngu", "den_chinh"]
    },
    "ch2": {
      "device_type": "quat",
      "description": "Quạt phòng ngủ",
      "gpio": 5,
      "rated_watts": 55.0,
      "aliases": ["quat", "quat_ngu", "quat_phong_ngu", "quat_tran"]
    }
  }
}
```

---

## 6. Danh Mục Các Tệp Mã Nguồn Quan Trọng (File Tree)

```text
d:\Home-Assistant-IoT-\
├── Firmware\
│   └── firmware_esp\
│       └── Esp32S3_Master\
│           ├── platformio.ini               # Cấu hình PlatformIO (ESP-IDF 5.3.1, N16R8)
│           ├── partitions.csv               # Bảng phân vùng (OTA, Model 8MB, Storage)
│           ├── include\
│           │   ├── audio_feedback.h         # Header bộ âm báo phản hồi loa & Mutex
│           │   ├── mqtt_relay.h             # Cấu hình Relay (Active-LOW) & MQTT Client
│           │   └── ws_audio_client.h        # Client truyền nhận âm thanh WebSocket
│           └── src\
│               ├── main.c                   # Entry point: AFE, WakeNet, ESP-NOW, TinyML
│               ├── audio_feedback.c         # Bộ tổng hợp âm thanh Sine Wave + Envelope
│               ├── mqtt_relay.c             # Điều khiển Relay và gửi nhận MQTT
│               └── ws_audio_client.c        # Xử lý luồng âm thanh WebSocket 192KB PSRAM
├── Gateway\
│   ├── device_registry.json                 # Cơ sở dữ liệu danh mục thiết bị & Alias
│   ├── requirements.txt                     # Các gói thư viện Python yêu cầu
│   ├── systemd\
│   │   ├── llama-server.service             # Dịch vụ systemd chạy Qwen2.5 trên Pi 4
│   │   └── smarthome-gateway.service        # Dịch vụ systemd chạy Gateway chính
│   └── gateway\
│       ├── config.py                        # Tệp cấu hình tập trung toàn bộ hệ thống
│       ├── main.py                          # Bộ điều phối trung tâm (Central Orchestrator)
│       ├── asr_engine.py                    # Nhận dạng giọng nói Sherpa-ONNX
│       ├── intent_engine.py                 # Phân tích cú pháp khẩu lệnh qua LLM
│       ├── tts_engine.py                    # Chuyển văn bản thành giọng nói EdgeTTS
│       ├── audio_server.py                  # Server WebSocket stream âm thanh 2 chiều
│       ├── verify_engine.py                 # Động cơ đối soát vòng lặp kín năng lượng
│       ├── memory_engine.py                 # Bộ nhớ 3 tầng & khai phá mẫu thói quen
│       ├── mqtt_handler.py                  # Trình quản lý kết nối & điều phối MQTT
│       ├── registry_manager.py              # Tìm kiếm thiết bị mờ (Fuzzy/Alias matcher)
│       ├── telemetry_writer.py              # Ghi dữ liệu chuỗi thời gian vào InfluxDB
│       └── web_server.py                    # Web Monitor Dashboard thời gian thực (SSE)
├── Hardware\
│   └── PCB\
│       └── IoT_Board\
│           ├── IoT_Board.kicad_sch          # Sơ đồ nguyên lý mạch phần cứng
│           └── netlist.net                  # Danh sách liên kết mạch (Netlist)
└── systemif.md                              # Tài liệu hiện trạng hệ thống tổng thể (Tệp này)
```

---

## 7. Trạng Thái Vận Hành & Khắc Phục Lỗi Gần Nhất

1. **Khắc phục lỗi treo WebSocket Disconnect/Reconnect:**
   - Đã nâng cấp bộ đệm âm thanh loa lên **192 KB trong Octal PSRAM** của ESP32-S3.
   - Chuyển việc ghi dữ liệu sang chế độ Non-blocking (`timeout = 0`) để không làm nghẽn task mạng của ESP-IDF.
   - Điều chỉnh thời gian nghỉ truyền gói tin trên Pi 4 thành `35ms` (~1.8x tốc độ phát thực) triệt tiêu tình trạng dồn ứ TCP.
2. **Khắc phục lỗi xung đột Loa I2S:**
   - Tích hợp `spk_hw_mutex` đảm bảo an toàn tuyệt đối khi phát âm báo và giọng nói phản hồi.
   - Đưa âm báo hoàn tất thu âm (`AUDIO_FB_RECORDING_DONE`) lên phát trước khi gửi gói kết thúc lên Gateway.
3. **Sửa cực điều khiển Relay phần cứng:**
   - Đã cấu hình chính xác `RELAY_ACTIVE_LOW true` phù hợp với tầng kích cực âm Opto PC817 trên PCB, relay không bị nhảy sai khi khởi động.
4. **Xác thực lệnh thông minh trên Gateway:**
   - Gateway tự động phân biệt các node có cảm biến đo dòng và node không có cảm biến đo dòng để phản hồi thành công ngay lập tức, không gây báo lỗi giả.
