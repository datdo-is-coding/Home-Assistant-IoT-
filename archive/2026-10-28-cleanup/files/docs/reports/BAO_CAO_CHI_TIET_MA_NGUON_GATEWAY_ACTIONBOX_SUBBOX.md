# BÁO CÁO TOÀN DIỆN VỀ KIẾN TRÚC VÀ CÔNG DỤNG TỪNG FILE CODE TRONG GATEWAY, ACTIONBOX V2 VÀ SUBBOX

> **Dự án:** Hệ Thống Nhà Thông Minh Điều Khiển Giọng Nói Tiếng Việt & Giám Sát Năng Lượng Vòng Lặp Kín (Closed-Loop IoT Smart Home)  
> **Phiên bản:** Aetheria OS / Home Competition Core Architecture  
> **Thời gian lập báo cáo:** Tháng 10/2026  
> **Tài liệu tham chiếu:** [systemif.md](file:///home/tuan/Home-Assistant-IoT-/systemif.md), [report_project.md](file:///home/tuan/Home-Assistant-IoT-/report_project.md), [device-lifecycle-v1.md](file:///home/tuan/Home-Assistant-IoT-/docs/contracts/device-lifecycle-v1.md)

---

## MỤC LỤC
1. [TỔNG QUAN KIẾN TRÚC HỆ THỐNG 3 TẦNG (3-TIER ARCHITECTURE)](#1-tổng-quan-kiến-trúc-hệ-thống-3-tầng)
2. [CHI TIẾT MÃ NGUỒN SUBBOX (`Firmware/firmware_esp/SubBox/src`)](#2-chi-tiết-mã-nguồn-subbox)
   - 2.1. File Khởi Động & Cấu Hình Build
   - 2.2. Module Cấu Hình Phần Cứng & Hệ Thống (`config/`)
   - 2.3. Module Điều Phối Tác Vụ & Quản Trị Hệ Thống (`system/`)
   - 2.4. Module Lưu Trữ Bền Vững & Bảo Mật (`storage/`)
   - 2.5. Module Mạng & Giao Tiếp Truyền Thông (`network/`, `mqtt/`)
   - 2.6. Module Quản Lý Không Gian & Luật Tự Động Hóa (`room/`, `rules/`)
   - 2.7. Module Quản Lý ActionBox & Định Tuyến Lệnh (`actionbox/`)
   - 2.8. Module Xử Lý Âm Thanh Toàn Diện (`audio/`)
   - 2.9. Module Xử Lý Ngôn Ngữ Tự Nhiên Cục Bộ (`nlu/`)
   - 2.10. Module Tổng Hợp Giọng Nói (`tts/`)
3. [CHI TIẾT MÃ NGUỒN ACTIONBOX V2 (`Firmware/firmware_esp/ActionBox_V2/src`)](#3-chi-tiết-mã-nguồn-actionbox-v2)
   - 3.1. File Khởi Động & Cấu Hình Build
   - 3.2. Cấu Hình Phần Cứng & Tham Số Vận Hành (`config/`, `common/`)
   - 3.3. Module Trình Điều Khiển Thiết Bị Ngoại Vi (`drivers/`)
   - 3.4. Module Thu Âm & Nhận Diện Từ Khóa KWS (`audio/`)
   - 3.5. Module Giao Thức Mạng & Truyền Thông ESP-NOW (`protocol/`, `network/`)
   - 3.6. Module Lưu Trữ NVS & Giám Sát An Toàn Phần Cứng (`storage/`, `safety/`)
   - 3.7. Module Điều Phối Thiết Bị & Đăng Ký Hệ Thống (`system/`, `device/`)
4. [CHI TIẾT MÃ NGUỒN GATEWAY (`Gateway/gateway`)](#4-chi-tiết-mã-nguồn-gateway)
   - 4.1. Khởi Động, Cấu Hình & Quản Trị Hệ Thống
   - 4.2. Quản Lý Thiết Bị, Vòng Đời & Ghép Nối
   - 4.3. Động Cơ Xử Lý Giọng Nói & Tương Tác Hội Thoại (ASR, Intent, Dialog, TTS, Sound)
   - 4.4. Truyền Thông Mạng, Server Âm Thanh & Web Dashboard
   - 4.5. Động Cơ Xác Thực Vòng Lặp Kín & Cơ Sở Dữ Liệu Lịch Sử (Verify Engine, InfluxDB)
   - 4.6. Trí Tuệ Nhân Tạo Tự Chủ & Đồng Hành (Memory, Persona, Proactive Agent)
   - 4.7. Phân Hệ Core V1 Doanh Nghiệp (`core_v1/`)
5. [SƠ ĐỒ PHỐI HỢP LIÊN TẦNG & LUỒNG HOẠT ĐỘNG THỰC TẾ (WORKFLOWS)](#5-sơ-đồ-phối-hợp-liên-tầng--luồng-hoạt-động-thực-tế)
6. [TỔNG KẾT VÀ BẢNG TRA CỨU NHANH DANH MỤC FILE](#6-tổng-kết-và-bảng-tra-cứu-nhanh)

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG 3 TẦNG

Hệ thống được xây dựng theo mô hình **Điện toán phân tán từ biên đến cổng điều khiển (Edge-to-Gateway Distributed Architecture)** gồm 3 phân tầng vật lý độc lập nhưng liên kết chặt chẽ:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GATEWAY (Raspberry Pi 4 / Linux)                      │
│ - Web Server & SSE Realtime (Port 8000)                                     │
│ - Audio WebSocket Server (Port 8765): ASR (Sherpa-ONNX Zipformer)           │
│ - NLU Intent Engine v3 (Fast-path rules + Qwen 2.5 / Gemini)                │
│ - TTS Engine (VieNeu On-device / EdgeTTS Cloud)                             │
│ - Closed-Loop Verifier (Đối soát trạng thái Relay & độ biến thiên dòng P)   │
│ - Multi-Turn Dialog & Context Manager, Device Lifecycle, Core V1            │
│ - Time-Series DB InfluxDB v2, SQLite WAL (gateway.db, auth.db)              │
└───────────────────────────────────────▲─────────────────────────────────────┘
                                        │ Wi-Fi STA / MQTT TLS (Port 8883) &
                                        │ WebSocket Streaming (Port 8765)
┌───────────────────────────────────────┴─────────────────────────────────────┐
│                        SUBBOX (ESP32-S3 Room Coordinator)                   │
│ - "Local Brain" của từng phòng, xử lý điều phối phòng không phụ thuộc Cloud │
│ - Ingest & Buffer âm thanh (PSRAM Ring Buffer, Energy VAD)                  │
│ - Local NLU: Vietnamese Normalizer, Entity Extractor, Intent Parser         │
│ - Local Context Manager, Rule Engine tự động hóa nội bộ phòng               │
│ - Audio Router & Sound Synthesizer (Chime, Prompt qua I2S MAX98357A)        │
│ - Cầu nối truyền thông: ESP-NOW Unicast (với ActionBox) <--> Wi-Fi (Gateway)│
└───────────────────────────────────────▲─────────────────────────────────────┘
                                        │ ESP-NOW Không dây mã hóa (~1-2ms)
                                        │ Tần số 2.4GHz, Frame 250 bytes
┌───────────────────────────────────────┴─────────────────────────────────────┐
│                    ACTIONBOX V2 (ESP32-S3 Actuator & Sensor Node)           │
│ - 3 kênh Relay Latching (Xung đóng/ngắt độc lập, chống dính tiếp điểm)      │
│ - Đo lường điện năng chuyên dụng 3 kênh qua IC BL0942 (V, I, P, E, PF, Hz)  │
│ - Mic INMP441 I2S DMA + Wake-word KWS (TinyML offline "Hi ESP")             │
│ - Safety Supervisor ngắt cứng siêu tốc (<20ms) khi quá dòng, chập tải       │
│ - Nút bấm cơ bản xúc giác (Debounce) + LED chỉ thị trực quan                │
│ - Lưu trữ NVS chống mất dữ liệu khi cúp điện (Power-cut Recovery)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. CHI TIẾT MÃ NGUỒN SUBBOX (`Firmware/firmware_esp/SubBox/src`)

Thư mục `Firmware/firmware_esp/SubBox/src` chứa toàn bộ mã nguồn C/C++ điều khiển vi điều khiển ESP32-S3 đóng vai trò **Bộ Điều Phối Phòng (Room Coordinator / Local Brain)**.

### 2.1. File Khởi Động & Cấu Hình Build

* [`src/main.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/main.cpp):
  - **Công dụng:** Điểm khởi nhập chính (`app_main`) của hệ điều hành trên SubBox.
  - **Chức năng:**
    - Khởi tạo hệ thống logging, heap caps, NVS flash.
    - Đọc cấu hình mạng và thông tin phòng từ NVS thông qua `NVSManager`.
    - Kiểm tra trạng thái xuất xưởng (First Boot / Blank NVS); nếu chưa có cấu hình sẽ mở cửa sổ cấp phát mạng an toàn (`hc_provisioning_start`).
    - Khởi tạo ngăn xếp kết nối Wi-Fi Station với cơ chế tự động thử lại (reconnect backoff) và đồng bộ thời gian thực qua NTP (`pool.ntp.org`).
    - Khởi tạo bộ tổng hợp âm thanh `SoundPlayer` và phát âm báo khởi động (`SoundType::BOOTUP`).
    - Tạo các đối tượng quản lý cốt lõi: `RoomManager`, `EnergyVAD`, `WsASR`, `AudioManager`, `EspNowAudioTransport`, `AudioOutputRouter`, `TTSManager`, `ActionBoxRegistry`, `ContextManager`, `CommandRouter`, `RuleEngine`, `MqttClient`.
    - Thiết lập luồng callback: Audio Transport -> Audio Manager -> VAD -> ASR -> Command Router.
    - Khởi động `TaskManager` để phân bổ tác vụ FreeRTOS và mở cổng dòng lệnh nhà phát triển `DevConsole`.
* [`src/CMakeLists.txt`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/CMakeLists.txt):
  - **Công dụng:** File kịch bản cấu hình build hệ thống ESP-IDF cho SubBox.
  - **Chức năng:** Định nghĩa các thư mục mã nguồn (`SRCS`), thư mục header (`INCLUDE_DIRS`), và liên kết các component phụ thuộc của ESP-IDF (`esp_wifi`, `nvs_flash`, `esp_netif`, `esp_timer`, `driver`, `esp_psram`, `app_update`, `mqtt`).
* [`src/idf_component.yml`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/idf_component.yml):
  - **Công dụng:** Khai báo các gói phụ thuộc mở rộng qua ESP Component Manager.
  - **Chức năng:** Tải tự động các thư viện tối ưu hóa thuật toán âm thanh của Espressif (như `espressif/esp-sr`, `espressif/esp_websocket_client`).

### 2.2. Module Cấu Hình Phần Cứng & Hệ Thống (`config/`)

* [`src/config/board_pins.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/config/board_pins.h):
  - **Công dụng:** Định nghĩa bản đồ chân GPIO vật lý của bo mạch ESP32-S3 SubBox.
  - **Chức năng:**
    - Giao tiếp I2S Microphone INMP441: `BCLK`, `WS`, `DIN`.
    - Giao tiếp I2S Speaker MAX98357A: `BCLK`, `LRC`, `DOUT`, và chân điều khiển nguồn amply `SP_SD`.
    - Chân LED trạng thái: `LED1` (Hệ thống / Wi-Fi), `LED2` (Hoạt động thu âm/nhận diện).
    - Chân nút bấm vật lý (nút Boot/Cấu hình nhanh) và chân UART phục vụ Dev Console.
* [`src/config/subbox_config.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/config/subbox_config.h):
  - **Công dụng:** Lưu trữ toàn bộ hằng số cấu hình hệ thống, tham số âm thanh và phân bổ tài nguyên FreeRTOS.
  - **Chức năng:**
    - Cấu hình âm thanh: Tần số lấy mẫu 16,000 Hz, 16-bit PCM, Mono; kích thước khung 10ms (160 samples = 320 bytes).
    - Kích thước vùng đệm Ring Buffer trong PSRAM: 256 KB.
    - Ngưỡng thuật toán VAD: Ngưỡng năng lượng khởi tạo (`SUBBOX_VAD_INITIAL_ENERGY_THRESH`), khung bắt đầu tiếng nói (`SPEECH_ONSET_FRAMES = 3`), thời gian im lặng kết thúc câu (`SILENCE_TIMEOUT = 1500ms`), độ dài khẩu lệnh tối đa 10s.
    - Cấu hình mạng: Cổng UDP RX/TX (5005/5006), độ dài tối đa payload gói âm thanh.
    - Bảng định mức ưu tiên (`TASK_PRIO_*`) và dung lượng stack (`TASK_STACK_*`) cho 11 tác vụ FreeRTOS chạy đồng thời trên 2 nhân CPU.

### 2.3. Module Điều Phối Tác Vụ & Quản Trị Hệ Thống (`system/`)

* [`src/system/task_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/task_manager.h) & [`src/system/task_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/task_manager.cpp):
  - **Công dụng:** Quản lý vòng đời, phân phối hàng đợi và giám sát hoạt động của các tiến trình FreeRTOS.
  - **Chức năng:**
    - Tạo các Queue FreeRTOS liên tác vụ (hàng đợi gói âm thanh thô, hàng đợi lệnh điều khiển, hàng đợi bản tin MQTT).
    - Tạo và ghim các tác vụ vào Core 0 và Core 1:
      - `AudioRxTask`: Tiếp nhận liên tục luồng gói âm thanh từ ActionBox qua ESP-NOW.
      - `AudioManagerTask`: Bơm mẫu âm thanh vào VAD và chuyển tiếp sang ASR.
      - `CommandProcessTask`: Lấy lệnh từ ASR hoặc Gateway để định tuyến.
      - `RuleEngineTask`: Định kỳ chạy vòng quét luật tự động hóa phòng.
      - `MqttWorkerTask`: Đẩy dữ liệu đo đạc và sự kiện lên Gateway qua MQTT.
    - Theo dõi tình trạng bộ nhớ và thực hiện Watchdog nuôi task tránh nghẽn luồng.
* [`src/system/subbox_led.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/subbox_led.h) & [`src/system/subbox_led.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/subbox_led.cpp):
  - **Công dụng:** Điều khiển đèn LED hiển thị trạng thái vận hành của SubBox.
  - **Chức năng:**
    - Hiển thị trực quan trạng thái kết nối Wi-Fi (nhấp nháy khi đang kết nối, sáng liên tục khi đã có IP).
    - Hiển thị trạng thái MQTT Broker (sáng xanh/tắt).
    - Bật nhấp nháy báo lỗi (`subbox_led_set_error`) khi có sự cố mạng hoặc lỗi phần cứng.
    - Bật LED trạng thái giọng nói khi người dùng đang nói và hệ thống đang lắng nghe.
* [`src/system/wifi_provisioning.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/wifi_provisioning.h) & [`src/system/wifi_provisioning.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/wifi_provisioning.cpp):
  - **Công dụng:** Cơ chế cấp phát cấu hình Wi-Fi ban đầu (Provisioning) khi thiết bị mới xuất xưởng hoặc cần đổi mạng.
  - **Chức năng:** Hỗ trợ mở cổng cấu hình qua Wi-Fi SoftAP / Bluetooth BLE để nhận SSID, mật khẩu Wi-Fi và địa chỉ Gateway từ ứng dụng di động, sau đó lưu an toàn vào NVS.
* [`src/system/dev_console.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/dev_console.h) & [`src/system/dev_console.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/system/dev_console.cpp):
  - **Công dụng:** Giao diện dòng lệnh tương tác trực tiếp (Interactive CLI) qua cổng UART/Serial dành cho kỹ sư.
  - **Chức năng:**
    - Cung cấp các lệnh chẩn đoán: `status` (bộ nhớ, CPU, IP), `nodes` (danh sách ActionBox kết nối), `room` (thông tin phòng), `play_chime` (test loa), `inject_cmd` (giả lập khẩu lệnh giọng nói để kiểm tra luồng NLU).

### 2.4. Module Lưu Trữ Bền Vững & Bảo Mật (`storage/`)

* [`src/storage/nvs_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/storage/nvs_manager.h) & [`src/storage/nvs_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/storage/nvs_manager.cpp):
  - **Công dụng:** Lớp trừu tượng quản lý bộ nhớ flash bất biến NVS (Non-Volatile Storage).
  - **Chức năng:**
    - Đọc/ghi cấu hình `SubBoxPersistentConfig`: ID SubBox, tên phòng tiếng Việt, mã phân loại phòng, SSID/Mật khẩu Wi-Fi, URI Broker MQTT, URI Audio WebSocket.
    - Bảo đảm an toàn giao dịch: Ghi dữ liệu nguyên tử (atomic commit), tự khôi phục về cấu hình mặc định an toàn khi dữ liệu bị lỗi.
* [`src/storage/security_config.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/storage/security_config.h) & [`src/storage/security_config.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/storage/security_config.cpp):
  - **Công dụng:** Quản lý khóa mật mã và chứng chỉ an ninh mạng.
  - **Chức năng:**
    - Lưu trữ khóa mã hóa cục bộ LMK (Local Master Key) cho giao thức ESP-NOW.
    - Lưu trữ khóa bí mật HMAC dùng để xác thực tính toàn vẹn của các gói tin điều khiển và chống tấn công phát lại (Replay Attacks).

### 2.5. Module Mạng & Giao Tiếp Truyền Thông (`network/`, `mqtt/`)

* [`src/network/espnow_receiver.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/network/espnow_receiver.h) & [`src/network/espnow_receiver.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/network/espnow_receiver.cpp):
  - **Công dụng:** Trình tiếp nhận các khung truyền không dây ESP-NOW tốc độ cao từ các ActionBox trong phòng.
  - **Chức năng:**
    - Khởi tạo ngăn xếp ESP-NOW trên kênh tần số Wi-Fi tương ứng.
    - Phân tách và giải mã loại gói tin đến: phân biệt giữa luồng gói âm thanh giọng nói (`AUDIO_PACKET`) và gói tin dữ liệu telemetry/trạng thái (`DATA_PACKET`).
    - Chuyển giao gói tin cho bộ đệm tương ứng mà không làm nghẽn luồng xử lý thời gian thực.
* [`src/mqtt/subbox_mqtt_client.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/mqtt/subbox_mqtt_client.h) & [`src/mqtt/subbox_mqtt_client.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/mqtt/subbox_mqtt_client.cpp):
  - **Công dụng:** Trình khách MQTT không đồng bộ kết nối SubBox với Gateway (qua EMQX Broker).
  - **Chức năng:**
    - Hỗ trợ mã hóa TLS/MQTTS (Port 8883) hoặc tiêu chuẩn TCP (Port 1883).
    - Đăng ký lắng nghe các topic cấu hình, lệnh điều khiển từ Gateway gửi xuống phòng: `smarthome/cmd/{subbox_id}`, `smarthome/cfg/{subbox_id}`.
    - Đẩy dữ liệu định kỳ: telemetry dòng/áp/công suất tổng hợp của phòng, trạng thái trực tuyến (LWT - Last Will and Testament), và báo cáo sự kiện/cảnh báo quá tải lên Gateway.

### 2.6. Module Quản Lý Không Gian & Luật Tự Động Hóa (`room/`, `rules/`)

* [`src/room/room_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/room/room_manager.h) & [`src/room/room_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/room/room_manager.cpp):
  - **Công dụng:** Quản trị ngữ cảnh không gian vật lý của căn phòng mà SubBox đang phụ trách.
  - **Chức năng:**
    - Lưu trữ tên phòng hiển thị (`m_room_name` e.g., "Phòng Ngủ Master"), mã phòng chuẩn hóa (`m_room_id`).
    - Lưu trữ danh sách các loại thiết bị mặc định có trong phòng để phục vụ việc giải quyết câu lệnh tỉnh lược (ví dụ: khi người dùng nói "Bật đèn" trong phòng ngủ, SubBox tự hiểu là đèn của phòng ngủ này).
* [`src/rules/rule_engine.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/rules/rule_engine.h) & [`src/rules/rule_engine.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/rules/rule_engine.cpp):
  - **Công dụng:** Động cơ thực thi kịch bản tự động hóa nội bộ phòng chạy độc lập (Offline Edge Automation).
  - **Chức năng:**
    - Đánh giá các ngưỡng cảm biến: Nếu dòng điện đo được từ ActionBox vượt ngưỡng cảnh báo quá tải (`current_overload_ma`), lập tức phát lệnh ngắt relay và kích hoạt còi báo.
    - Luật môi trường: Tự động kích hoạt quạt khi nhiệt độ phòng vượt ngưỡng cài đặt (`temp_fan_auto_on_c`).
    - Hoạt động liên tục kể cả khi Gateway bị tắt hoặc mạng Wi-Fi bị đứt.

### 2.7. Module Quản Lý ActionBox & Định Tuyến Lệnh (`actionbox/`)

* [`src/actionbox/protocol/actionbox_network_protocol.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/actionbox/protocol/actionbox_network_protocol.h):
  - **Công dụng:** Định nghĩa cấu trúc khung truyền thông nhị phân giữa SubBox và ActionBox qua ESP-NOW.
  - **Chức năng:**
    - Định nghĩa cấu trúc Header: Magic byte, Message Type (`CMD_RELAY_CONTROL`, `TELEMETRY_REPORT`, `PAIR_REQUEST`, `ACK`), độ dài payload, số thứ tự gói (Sequence number).
    - Cấu trúc Payload: Trạng thái relay, dòng điện RMS (mA), điện áp RMS (V), công suất tức thời (W), cờ báo lỗi phần cứng.
* [`src/actionbox/registry/actionbox_registry.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/actionbox/registry/actionbox_registry.h) & [`src/actionbox/registry/actionbox_registry.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/actionbox/registry/actionbox_registry.cpp):
  - **Công dụng:** Bảng đăng ký lưu trữ danh sách các nút ActionBox đang hoạt động trong phòng.
  - **Chức năng:**
    - Ánh xạ địa chỉ MAC ESP-NOW của từng ActionBox với Node ID logic và các kênh relay tương ứng (Channel 1: Đèn, Channel 2: Quạt, Channel 3: Thiết bị phụ).
    - Theo dõi nhịp tim sống (Heartbeat / Keepalive), tự động đánh dấu thiết bị là `OFFLINE` nếu quá 15 giây không nhận được gói tin nào.
* [`src/actionbox/router/command_router.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/actionbox/router/command_router.h) & [`src/actionbox/router/command_router.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/actionbox/router/command_router.cpp):
  - **Công dụng:** Bộ định tuyến lệnh thông minh phân biệt lệnh nội bộ phòng và lệnh liên phòng.
  - **Chức năng:**
    - Nhận lệnh đã phân tích từ NLU/ASR.
    - Kiểm tra đích đến:
      - Nếu thiết bị thuộc cùng phòng: Gửi gói tin điều khiển nhị phân trực tiếp đến ActionBox tương ứng qua ESP-NOW (`executeLocalCommand`) với độ trễ cực thấp (<5ms).
      - Nếu thiết bị thuộc phòng khác (Cross-Room) hoặc cần xử lý nâng cao: Đóng gói và chuyển tiếp lệnh lên Gateway qua MQTT (`forwardCrossRoom` / `forwardToPi4`).

### 2.8. Module Xử Lý Âm Thanh Toàn Diện (`audio/`)

* [`src/audio/audio_transport/audio_packet.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/audio_packet.h):
  - **Công dụng:** Định nghĩa cấu trúc dữ liệu gói tin truyền tải luồng âm thanh PCM.
  - **Chức năng:** Chứa thông tin định danh nguồn (`source_id`), số thứ tự gói (`sequence_number`), dấu thời gian (`timestamp`), cờ kết thúc câu nói (`is_last_chunk`) và mảng dữ liệu mẫu âm thanh 16-bit PCM.
* [`src/audio/audio_transport/audio_transport.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/audio_transport.h):
  - **Công dụng:** Lớp giao diện trừu tượng (Interface) cho các cơ chế vận chuyển âm thanh.
* [`src/audio/audio_transport/espnow_audio_transport.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/espnow_audio_transport.h) & [`src/audio/audio_transport/espnow_audio_transport.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/espnow_audio_transport.cpp):
  - **Công dụng:** Hiện thực hóa truyền nhận âm thanh thời gian thực qua giao thức ESP-NOW.
  - **Chức năng:** Nhận các gói âm thanh giọng nói truyền từ micro của ActionBox về SubBox với cơ chế kiểm soát thất thoát gói tin (Packet Loss Detection).
* [`src/audio/audio_transport/udp_audio_transport.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/udp_audio_transport.h) & [`src/audio/audio_transport/udp_audio_transport.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_transport/udp_audio_transport.cpp):
  - **Công dụng:** Phương thức vận chuyển âm thanh dự phòng qua UDP Socket trên nền mạng Wi-Fi tiêu chuẩn.
* [`src/audio/audio_buffer/audio_ring_buffer.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_buffer/audio_ring_buffer.h) & [`src/audio/audio_buffer/audio_ring_buffer.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_buffer/audio_ring_buffer.cpp):
  - **Công dụng:** Cấu trúc bộ đệm vòng (Circular Ring Buffer) an toàn tuyến trình (thread-safe) đặt trong bộ nhớ ngoài PSRAM.
  - **Chức năng:** Lưu trữ trơn tru luồng âm thanh PCM giữa tiến trình nhận mạng và tiến trình phân tích VAD/ASR, loại bỏ hiện tượng giật cục âm thanh hoặc tràn RAM nội vi.
* [`src/audio/vad/vad_interface.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/vad/vad_interface.h):
  - **Công dụng:** Giao diện chuẩn cho thuật toán phát hiện hoạt động giọng nói (Voice Activity Detection).
* [`src/audio/vad/energy_vad.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/vad/energy_vad.h) & [`src/audio/vad/energy_vad.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/vad/energy_vad.cpp):
  - **Công dụng:** Thuật toán VAD dựa trên mức năng lượng trung bình bình phương (Short-time Energy VAD).
  - **Chức năng:** Tự động ước lượng ngưỡng ồn nền môi trường, phát hiện chính xác thời điểm người dùng bắt đầu nói (Onset) và tự động ngắt thu âm khi người dùng im lặng quá 1.5 giây (Endpoint Detection), giúp tối ưu băng thông mạng.
* [`src/audio/asr/asr_engine.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/asr_engine.h):
  - **Công dụng:** Interface định nghĩa các phương thức nhận dạng giọng nói thành văn bản.
* [`src/audio/asr/ws_asr.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/ws_asr.h) & [`src/audio/asr/ws_asr.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/ws_asr.cpp):
  - **Công dụng:** Trình khách WebSocket truyền luồng âm thanh trực tiếp từ SubBox lên Audio Server của Gateway (`ws://<gateway_ip>:8765/ws/audio`).
  - **Chức năng:** Mở kết nối nhị phân, truyền liên tục các khối PCM 16kHz, nhận lại kết quả văn bản tiếng Việt đã nhận diện (Transcript) và cờ yêu cầu mở mic tiếp tục (Follow-up Dialog).
* [`src/audio/asr/fallback_asr.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/fallback_asr.h) & [`src/audio/asr/fallback_asr.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/fallback_asr.cpp):
  - **Công dụng:** Bộ nhận dạng giọng nói dự phòng chạy offline trên vi điều khiển khi mất kết nối Gateway.
  - **Chức năng:** Sử dụng mô hình nhận diện từ khóa cơ bản của ESP-SR để xử lý các câu lệnh khẩn cấp tại chỗ như "Bật đèn", "Tắt đèn".
* [`src/audio/asr/dummy_asr.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/dummy_asr.h) & [`src/audio/asr/dummy_asr.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/asr/dummy_asr.cpp):
  - **Công dụng:** Triển khai ASR giả lập phục vụ unit test tự động và kiểm thử hồi quy trên môi trường CI/CD.
* [`src/audio/audio_manager/audio_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_manager/audio_manager.h) & [`src/audio/audio_manager/audio_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_manager/audio_manager.cpp):
  - **Công dụng:** Bộ điều phối trung tâm của toàn bộ đường ống xử lý âm thanh đầu vào.
  - **Chức năng:** Quản lý máy trạng thái âm thanh (`IDLE`, `RECORDING`, `PROCESSING`, `STREAMING`), tiếp nhận gói âm thanh từ transport, đẩy vào ring buffer, kiểm tra trạng thái VAD và chuyển giao tới ASR.
* [`src/audio/audio_output/audio_output_router.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_output/audio_output_router.h) & [`src/audio/audio_output/audio_output_router.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_output/audio_output_router.cpp):
  - **Công dụng:** Định tuyến âm thanh đầu ra.
  - **Chức năng:** Quyết định phát âm phản hồi (câu trả lời giọng nói TTS hoặc âm báo chuông) qua loa tích hợp tại chỗ của SubBox hoặc gửi ngược gói âm thanh về loa của thiết bị yêu cầu.
* [`src/audio/audio_output/sound_player.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_output/sound_player.h) & [`src/audio/audio_output/sound_player.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/audio/audio_output/sound_player.cpp):
  - **Công dụng:** Trình phát âm thanh hiệu ứng bằng thuật toán tổng hợp sóng hình sin trực tiếp (Sine Wave Synthesizer) xuất qua DAC I2S MAX98357A.
  - **Chức năng:** Phát các âm hiệu ứng hệ thống: Chuông khởi động (`BOOTUP`), nhận lệnh thành công (`ACK`), chuông cảnh báo lỗi (`ERROR`).

### 2.9. Module Xử Lý Ngôn Ngữ Tự Nhiên Cục Bộ (`nlu/`)

* [`src/nlu/normalizer/vietnamese_normalizer.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/normalizer/vietnamese_normalizer.h) & [`src/nlu/normalizer/vietnamese_normalizer.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/normalizer/vietnamese_normalizer.cpp):
  - **Công dụng:** Tiền xử lý và chuẩn hóa chuỗi tiếng Việt.
  - **Chức năng:** Chuyển đổi chữ hoa thành chữ thường, loại bỏ các ký tự đặc biệt, chuẩn hóa các biến thể đặt dấu thanh tiếng Việt (ví dụ: `hoà` vs `hòa`), chuẩn hóa các từ đồng nghĩa thường dùng trong khẩu lệnh nhà thông minh.
* [`src/nlu/entity/entity_types.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/entity/entity_types.h):
  - **Công dụng:** Định nghĩa các kiểu thực thể (Entity) trong hệ thống nhà thông minh: Thiết bị (`DEVICE_LIGHT`, `DEVICE_FAN`, `DEVICE_AC`), Vị trí phòng (`LOCATION_ROOM`), Chỉ số kênh (`CHANNEL_INDEX`), Giá trị tham số (`VALUE_NUMBER`).
* [`src/nlu/entity/entity_extractor.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/entity/entity_extractor.h) & [`src/nlu/entity/entity_extractor.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/entity/entity_extractor.cpp):
  - **Công dụng:** Trích xuất các thực thể từ chuỗi văn bản đã chuẩn hóa.
  - **Chức năng:** Tìm kiếm từ khóa định danh thiết bị ("đèn chùm", "quạt trần", "bình nóng lạnh"), tên phòng ("phòng khách", "phòng ngủ", "bếp"), số kênh ("kênh 1", "kênh 2") và giá trị số (nhiệt độ điều hòa: "24 độ").
* [`src/nlu/intent/intent_types.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/intent/intent_types.h):
  - **Công dụng:** Định nghĩa các cấu trúc và Enum ý định điều khiển: `INTENT_TURN_ON`, `INTENT_TURN_OFF`, `INTENT_QUERY_STATUS`, `INTENT_SET_VALUE`, `INTENT_SCENE_CONTROL`, `INTENT_UNKNOWN`.
* [`src/nlu/intent/intent_parser.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/intent/intent_parser.h) & [`src/nlu/intent/intent_parser.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/intent/intent_parser.cpp):
  - **Công dụng:** Phân tích cú pháp khẩu lệnh để rút ra ý định hành động tương ứng.
  - **Chức năng:** Phân tích ngữ pháp động từ hành động ("bật", "mở", "kích hoạt" -> `TURN_ON`; "tắt", "đóng", "ngắt" -> `TURN_OFF`) kết hợp với thực thể trích xuất được để tạo thành đối tượng `ParsedIntent`.
* [`src/nlu/context/context_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/context/context_manager.h) & [`src/nlu/context/context_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/nlu/context/context_manager.cpp):
  - **Công dụng:** Quản lý ngữ cảnh hội thoại đa lượt tại phòng (Multi-turn Conversation Context).
  - **Chức năng:**
    - Ghi nhớ thiết bị và kênh vừa được tương tác gần nhất trong vòng TTL (mặc định 30 giây).
    - Giải quyết các đại từ thay thế tiếng Việt: Ví dụ người dùng nói "Bật đèn phòng khách", sau đó nói tiếp "Tắt nó đi" hoặc "Bật số hai", Context Manager sẽ tự động ánh xạ "nó" chính là đèn phòng khách.

### 2.10. Module Tổng Hợp Giọng Nói (`tts/`)

* [`src/tts/tts_engine.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/tts/tts_engine.h):
  - **Công dụng:** Định nghĩa giao diện chung cho bộ phận phát sinh giọng nói nhân tạo.
* [`src/tts/tts_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/tts/tts_manager.h) & [`src/tts/tts_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/SubBox/src/tts/tts_manager.cpp):
  - **Công dụng:** Quản lý hàng đợi phát các câu thông báo giọng nói phản hồi.
  - **Chức năng:** Tiếp nhận luồng PCM phản hồi từ TTS Server của Gateway, thực hiện điều tiết tốc độ khung (flow control) và đẩy ra bộ định tuyến âm thanh đầu ra `AudioOutputRouter`.

---

## 3. CHI TIẾT MÃ NGUỒN ACTIONBOX V2 (`Firmware/firmware_esp/ActionBox_V2/src`)

Thư mục `Firmware/firmware_esp/ActionBox_V2/src` chứa toàn bộ firmware của **Hộp Công Tắc & Đo Năng Lượng Thông Minh (Smart Actuator & Energy Metering Node)** phiên bản V2 chạy trên vi điều khiển ESP32-S3.

### 3.1. File Khởi Động & Cấu Hình Build

* [`src/main.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/main.cpp):
  - **Công dụng:** Điểm khởi động chính (`app_main`) của ActionBox V2.
  - **Chức năng:**
    - Cưỡng bức vô hiệu hóa phần cứng Amply loa (`hardware_disable_speaker` kéo chân `SP_SD` xuống mức LOW theo chính sách an toàn, ngắt điện mạch amply để triệt tiêu tiếng ù xì và tiết kiệm điện năng, vì ActionBox đóng vai trò là cơ cấu chấp hành có micro thu âm).
    - Khởi tạo bộ lưu trữ NVS (`nvs_storage_init`), nạp cấu hình hệ thống và hệ số hiệu chuẩn.
    - Khởi tạo trình điều khiển Relay (`relay_driver_init`) và phục hồi trạng thái đóng ngắt trước khi mất điện (`resume_interrupted_reset`).
    - Khởi tạo giao thức truyền thông nhị phân `actionbox_protocol`.
    - Khởi tạo trình điều khiển cảm biến đo điện chuyên dụng `bl0942_driver_init` cho 3 kênh độc lập.
    - Khởi tạo trình điều khiển nút bấm vật lý `button_driver_init` và LED chỉ thị `led_driver_init`.
    - Kích hoạt giám sát an toàn `safety_supervisor_init` và thiết lập trạng thái khởi động an toàn (`safety_apply_startup_state`).
    - Khởi tạo truyền thông không dây ESP-NOW tốc độ cao `espnow_transport_init` kết nối với SubBox.
    - Khởi tạo vi tác vụ thu âm micro I2S DMA `voice_capture_init`.
    - Đăng ký các hàm thực thi lệnh Core V1: `hc_apply` (đóng ngắt relay) và `hc_sample` (thu thập mẫu dòng điện tức thời).
    - Khởi động `device_manager` và `task_manager` bắt đầu chu trình vận hành.
* [`src/CMakeLists.txt`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/CMakeLists.txt):
  - **Công dụng:** Cấu hình build mã nguồn thành phần ActionBox_V2 trong hệ sinh thái ESP-IDF.
* [`src/Kconfig.projbuild`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/Kconfig.projbuild):
  - **Công dụng:** Menu cấu hình linh hoạt cho dự án qua công cụ `idf.py menuconfig`.
  - **Chức năng:** Cho phép tùy chỉnh loại relay (Relay thường Active-LOW hay Relay chốt Latching), số lượng kênh (2 kênh hoặc 3 kênh), chu kỳ phát telemetry và các ngưỡng bảo vệ dòng điện.
* [`src/idf_component.yml`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/idf_component.yml):
  - **Công dụng:** Quản lý gói thư viện phụ thuộc của ESP-IDF Component Registry cho ActionBox V2.

### 3.2. Cấu Hình Phần Cứng & Tham Số Vận Hành (`config/`, `common/`)

* [`src/config/app_config.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/config/app_config.h):
  - **Công dụng:** Chứa các định nghĩa thông số ứng dụng cốt lõi.
  - **Chức năng:**
    - Tên và phiên bản firmware (`APP_FW_NAME`, `APP_FW_VERSION_STR`).
    - Số kênh điều khiển vật lý: Hỗ trợ 3 kênh relay độc lập (`BOARD_RELAY_CHANNEL_COUNT = 3`).
    - Cấu hình loại điều khiển relay chốt (`BOARD_RELAY_TYPE_LATCHING_DUAL` với độ rộng xung kích mở/đóng 30ms).
    - Cấu hình chu kỳ lấy mẫu dòng điện (100ms) và chu kỳ đẩy telemetry (1000ms).
    - Dung lượng bộ nhớ ngăn xếp cấp phát cho các tiến trình FreeRTOS.
* [`src/config/board_pins.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/config/board_pins.h):
  - **Công dụng:** Bản đồ chân GPIO cụ thể trên PCB ActionBox V2 (ESP32-S3).
  - **Chức năng:**
    - Chân điều khiển Relay: Relay 1 (`GPIO 4`), Relay 2 (`GPIO 5`), Relay 3 (`GPIO 6`) hoặc các cặp chân xung SET/RESET của relay chốt.
    - Chân nút bấm cơ học: Nút 1 (`GPIO 1`), Nút 2 (`GPIO 3`), Nút 3.
    - Chân giao tiếp cảm biến BL0942 qua UART phần cứng (`TX/RX`).
    - Chân Micro I2S INMP441: `BCLK`, `WS`, `DIN`.
    - Chân LED chỉ thị: `LED_SYS` (GPIO 48) và `LED_VOICE` (GPIO 47).
    - Chân ngắt cứng nguồn amply: `BOARD_PIN_SPEAKER_SD` (GPIO 2).
* [`src/common/connection_status.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/common/connection_status.h):
  - **Công dụng:** Định nghĩa các cấu trúc dữ liệu và enum biểu diễn trạng thái kết nối và vũ trang của thiết bị (`ConnectivityState`, `LifecycleState`, `ArmedKind`).

### 3.3. Module Trình Điều Khiển Thiết Bị Ngoại Vi (`drivers/`)

* [`src/drivers/relay/relay_driver.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/relay/relay_driver.h) & [`src/drivers/relay/relay_driver.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/relay/relay_driver.cpp):
  - **Công dụng:** Trình điều khiển relay cấp công nghiệp hỗ trợ relay xung chốt (Dual-Coil Latching Relays).
  - **Chức năng:**
    - Cơ chế kích xung chính xác: Khi đóng hoặc mở relay chốt, driver chỉ phát một xung mức HIGH chính xác 30ms rồi tự động ngắt về mức LOW, giúp cuộn hút không bị nóng, không tiêu hao năng lượng tĩnh và loại bỏ hoàn toàn nguy cơ cháy cuộn coil.
    - Cơ chế khóa liên động phần mềm (Interlock) ngăn chặn xung đóng và xung ngắt kích hoạt đồng thời.
    - Quản lý trạng thái logic (`RELAY_STATE_ON`, `RELAY_STATE_OFF`) và phát hiện lỗi kẹt tiếp điểm relay.
* [`src/drivers/button/button_driver.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/button/button_driver.h) & [`src/drivers/button/button_driver.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/button/button_driver.cpp):
  - **Công dụng:** Trình điều khiển nút bấm vật lý gắn trên mặt công tắc.
  - **Chức năng:**
    - Khử rung phím bằng phần mềm (Software Debounce 50ms) loại bỏ xung nhiễu cơ học.
    - Nhận diện các sự kiện nhấn:
      - Nhấn nhanh (Short Press): Đảo trạng thái đóng/ngắt trực tiếp của kênh relay tương ứng tại chỗ với độ trễ tức thời (<5ms).
      - Nhấn giữ lâu (Long Press > 5s): Kích hoạt chế độ ghép nối mạng an toàn (Pairing Mode) hoặc khôi phục cài đặt gốc (Factory Reset).
* [`src/drivers/led/led_driver.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/led/led_driver.h) & [`src/drivers/led/led_driver.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/led/led_driver.cpp):
  - **Công dụng:** Trình điều khiển hệ thống đèn LED trạng thái.
  - **Chức năng:**
    - Điều khiển LED trạng thái hệ thống: Sáng liên tục khi hoạt động bình thường, nhấp nháy nhanh khi đang ghép nối mạng, nhấp nháy chu kỳ báo lỗi.
    - Điều khiển LED giọng nói: Bật sáng khi micro đang thu âm giọng nói và tắt khi kết thúc câu lệnh.
* [`src/drivers/current_sensor/current_sensor.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/current_sensor/current_sensor.h):
  - **Công dụng:** Khai báo cấu trúc đo lường điện năng chuẩn (`CurrentMeasurement`) và cấu trúc hiệu chuẩn cảm biến (`SensorCalibration`).
* [`src/drivers/current_sensor/bl0942.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/current_sensor/bl0942.h) & [`src/drivers/current_sensor/bl0942.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/drivers/current_sensor/bl0942.cpp):
  - **Công dụng:** Trình điều khiển giao tiếp UART với IC đo năng lượng chuyên dụng BL0942.
  - **Chức năng:**
    - Giao tiếp qua UART ở tốc độ 4800 baud, đọc định kỳ khung dữ liệu 23 bytes từ BL0942.
    - Kiểm tra mã tổng kiểm tra Checksum đảm bảo dữ liệu không bị sai lệch do nhiễu điện trường.
    - Tính toán chính xác các thông số điện học:
      - Điện áp hiệu dụng ($U_{RMS}$ tính bằng Vôn).
      - Dòng điện hiệu dụng ($I_{RMS}$ tính bằng mili-Ampe).
      - Công suất tác dụng tức thời ($P$ tính bằng Watt).
      - Điện năng tiêu thụ tích lũy ($E$ tính bằng kWh).
      - Tần số lưới điện ($f$ tính bằng Hz) và Hệ số công suất ($\cosarphi$).
    - Áp dụng các hệ số hiệu chuẩn (`calibrations`) riêng biệt cho từng kênh đo để triệt tiêu sai số linh kiện.

### 3.4. Module Thu Âm & Nhận Diện Từ Khóa KWS (`audio/`)

* [`src/audio/voice_capture.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/voice_capture.h) & [`src/audio/voice_capture.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/voice_capture.cpp):
  - **Công dụng:** Thu nhận dữ liệu âm thanh trực tiếp từ Microphone kỹ thuật số INMP441 qua bus I2S bằng kỹ thuật DMA (Direct Memory Access).
  - **Chức năng:**
    - Thu âm chuẩn 16,000 Hz, 16-bit mono.
    - Tích hợp động cơ KWS để lắng nghe từ khóa đánh thức ("Hi ESP").
    - Khi phát hiện từ khóa hoặc khi nhận lệnh mở mic từ hệ thống: Bật LED báo giọng nói và tự động truyền luồng gói âm thanh thô qua ESP-NOW về SubBox để phân tích ASR.
* [`src/audio/kws/kws_config.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_config.h):
  - **Công dụng:** Định nghĩa các tham số trích xuất đặc trưng âm thanh cho mô hình TinyML Keyword Spotting (kích thước khung FFT, bước nhảy hop size, số lượng bộ lọc Mel).
* [`src/audio/kws/kws_mfcc.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_mfcc.h) & [`src/audio/kws/kws_mfcc.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_mfcc.cpp):
  - **Công dụng:** Động cơ tính toán hệ số phổ Mel (MFCC - Mel-Frequency Cepstral Coefficients) thời gian thực trên ESP32-S3.
  - **Chức năng:** Biến đổi tín hiệu dạng sóng âm thanh theo miền thời gian sang ma trận biểu diễn tần số - năng lượng đóng vai trò là vector đặc trưng đầu vào cho mạng nơ-ron nhận dạng từ khóa.
* [`src/audio/kws/kws_engine.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_engine.h) & [`src/audio/kws/kws_engine.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_engine.cpp):
  - **Công dụng:** Bộ máy suy luận nơ-ron thu nhỏ (TinyML Neural Inference Engine) nhận diện từ khóa đánh thức Wake-word.
  - **Chức năng:** Chạy mô hình học sâu rút gọn tại biên, đưa ra xác suất kích hoạt từ khóa với mức tiêu thụ tài nguyên CPU tối thiểu.
* [`src/audio/kws/kws_model_quantized.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_model_quantized.h):
  - **Công dụng:** Mảng hằng số chứa trọng số mô hình mạng nơ-ron đã được lượng tử hóa số nguyên 8-bit (INT8 Quantized Model Weights) đặt trong bộ nhớ Flash ROM.

### 3.5. Module Giao Thức Mạng & Truyền Thông ESP-NOW (`protocol/`, `network/`)

* [`src/protocol/actionbox_protocol.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/protocol/actionbox_protocol.h) & [`src/protocol/actionbox_protocol.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/protocol/actionbox_protocol.cpp):
  - **Công dụng:** Hiện thực hóa giao thức đóng gói dữ liệu nhị phân chuẩn cho ActionBox.
  - **Chức năng:**
    - Đóng gói lệnh điều khiển (`ActionBoxCommand`) và gói phản hồi kết quả (`ActionBoxResponse`).
    - Đóng gói bản tin dữ liệu đo năng lượng (`ActionBoxTelemetry`) gồm đầy đủ thông số 3 kênh.
    - Tính toán và thẩm tra mã kiểm tra toàn vẹn CRC16/CRC32 cùng mã xác thực khóa HMAC.
* [`src/network/espnow_transport.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/network/espnow_transport.h) & [`src/network/espnow_transport.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/network/espnow_transport.cpp):
  - **Công dụng:** Lớp giao tiếp truyền dẫn không dây ESP-NOW tốc độ cao kết nối trực tiếp với SubBox.
  - **Chức năng:**
    - Khởi tạo ngăn xếp mạng vô tuyến ESP-NOW đơn hướng/song hướng với cơ chế bắt tay Unicast.
    - Quản lý hàng đợi gửi tin không chặn (Non-blocking TX Queue) và cơ chế thử lại tự động khi mất khung.
    - Lắng nghe lệnh từ SubBox và chuyển tiếp vào hàng đợi xử lý của `DeviceManager`.

### 3.6. Module Lưu Trữ NVS & Giám Sát An Toàn Phần Cứng (`storage/`, `safety/`)

* [`src/storage/nvs_storage.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/storage/nvs_storage.h) & [`src/storage/nvs_storage.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/storage/nvs_storage.cpp):
  - **Công dụng:** Quản lý lưu trữ trạng thái bất biến và cấu hình trên bộ nhớ Flash NVS của ActionBox.
  - **Chức năng:**
    - Lưu trữ trạng thái đóng/ngắt tức thời của 3 relay: Khi xảy ra cúp điện đột ngột và có điện trở lại, thiết bị lập tức khôi phục chính xác trạng thái tiếp điểm trước đó mà không làm xáo trộn sinh hoạt gia đình.
    - Lưu hệ số hiệu chuẩn đo lường BL0942, thông tin Node ID, Boot ID, số thế hệ sở hữu (`owner_epoch`) và thông tin vòng đời thiết bị.
    - Kiểm tra tính toàn vẹn dữ liệu bằng mã kiểm tra CRC cho từng vùng cấu hình, phát hiện và sửa chữa phân vùng hỏng.
* [`src/safety/safety_supervisor.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/safety/safety_supervisor.h) & [`src/safety/safety_supervisor.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/safety/safety_supervisor.cpp):
  - **Công dụng:** Bộ giám sát an toàn phần cứng thời gian thực cấp độ nghiêm ngặt (Hard Real-Time Safety Supervisor).
  - **Chức năng:**
    - Tiếp nhận dữ liệu đo dòng điện tức thời từ BL0942 mỗi 100ms.
    - Cắt relay khẩn cấp (Emergency Overcurrent Trip): Nếu dòng điện trên bất kỳ kênh nào vượt quá ngưỡng an toàn định mức (ví dụ quá tải 16A hoặc chập mạch), bộ giám sát kích hoạt ngắt relay tức thì trong thời gian dưới 20 mili-giây, ngăn ngừa nguy cơ chập cháy điện lưới.
    - Giám sát tình trạng sống của cảm biến (Sensor Timeout Watchdog): Nếu IC BL0942 ngừng phản hồi quá thời gian quy định, đánh dấu kênh lỗi và đưa ra chế độ bảo vệ.
    - Ngăn chặn lệnh điều khiển không an toàn và đăng ký nuôi Task Watchdog định kỳ.

### 3.7. Module Điều Phối Thiết Bị & Đăng Ký Hệ Thống (`system/`, `device/`)

* [`src/system/registration.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/system/registration.h) & [`src/system/registration.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/system/registration.cpp):
  - **Công dụng:** Quản lý quy trình đăng ký, ghép nối và bàn giao khóa bảo mật giữa ActionBox và SubBox/Gateway theo giao thức Core V1.
  - **Chức năng:** Thực hiện cơ chế bắt tay thách thức - phản hồi (Challenge-Response Handshake), chứng minh sự hiện diện vật lý qua thao tác nhấn nút trên thiết bị, và lưu trữ trạng thái đăng ký (`CLAIMED`).
* [`src/system/task_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/system/task_manager.h) & [`src/system/task_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/system/task_manager.cpp):
  - **Công dụng:** Quản trị các tác vụ nền FreeRTOS chuyên biệt trên ActionBox V2.
  - **Chức năng:**
    - Khởi tạo và giám sát: `MeteringTask` (quét dữ liệu BL0942), `SafetyTask` (đánh giá giới hạn an toàn), `ButtonTask` (đọc nút bấm), `VoiceTask` (thu âm micro), `TelemetryTask` (phát gói tin định kỳ).
* [`src/device/device_manager.h`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/device/device_manager.h) & [`src/device/device_manager.cpp`](file:///home/tuan/Home-Assistant-IoT-/Firmware/firmware_esp/ActionBox_V2/src/device/device_manager.cpp):
  - **Công dụng:** Bộ não điều phối trung tâm của ActionBox.
  - **Chức năng:**
    - Trọng tài điều khiển: Hợp nhất và giải quyết xung đột giữa các nguồn điều khiển khác nhau (lệnh nhấn nút cơ học tại chỗ, lệnh từ xa qua ESP-NOW, và lệnh ngắt từ bộ giám sát an toàn).
    - Cập nhật trạng thái relay, ghi nhận cảnh báo sự cố (`on_fault_alert`), cập nhật màu sắc LED trạng thái tương ứng và tạo báo cáo phản hồi kết quả điều khiển.

---

## 4. CHI TIẾT MÃ NGUỒN GATEWAY (`Gateway/gateway`)

Thư mục `Gateway/gateway` chứa toàn bộ mã nguồn trung tâm điều khiển của hệ thống chạy trên máy tính nhúng Linux (Raspberry Pi 4). Đây là nơi hội tụ các mô hình Trí tuệ Nhân tạo xử lý ngôn ngữ tự nhiên, máy chủ truyền thông thời gian thực, quản lý thiết bị toàn diện và cơ sở dữ liệu chuỗi thời gian.

### 4.1. Khởi Động, Cấu Hình & Quản Trị Hệ Thống

* [`gateway/__init__.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/__init__.py):
  - **Công dụng:** Đánh dấu thư mục `gateway` là một Python Package chính quy của hệ thống.
* [`gateway/config.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/config.py):
  - **Công dụng:** Tệp cấu hình tập trung toàn bộ hệ sinh thái Gateway.
  - **Chức năng:**
    - Tự động tìm kiếm và nạp các biến môi trường từ file cấu hình bí mật `.env`.
    - Định nghĩa địa chỉ IP, cổng kết nối và chứng chỉ bảo mật TLS của MQTT Broker (EMQX: 1883/8883).
    - Định nghĩa bảng danh mục các MQTT Topic chuẩn: Đăng ký (`smarthome/register`), nhịp tim (`smarthome/hello`), cấu hình (`smarthome/cfg/...`), đo lường (`smarthome/telemetry/...`), điều khiển (`smarthome/command/...`), cảnh báo (`smarthome/alert`).
    - Cấu hình các cổng dịch vụ mạng: Web Dashboard (8000), Audio WebSocket (8765), Llama LLM Server (8080), InfluxDB (8086).
    - Cấu hình các cờ tính năng AI: Kích hoạt AI (`AI_ENABLED`), chế độ trợ lý ảo nhân cách hóa (`PERSONA_ENABLED`), đặc vụ chủ động (`PROACTIVE_ENABLED`), nhà cung cấp giọng nói TTS (`TTS_PROVIDER`).
* [`gateway/main.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/main.py):
  - **Công dụng:** Điểm khởi nhập chính (Main Entry Point) của dịch vụ Smart Home Gateway v2.
  - **Chức năng:**
    - Khởi tạo toàn bộ các hệ thống con: `RegistryManager`, `MQTTHandler`, `IntentEngine`, `DialogManager`, `TTSEngine`, `ASREngine`, `AudioServer`, `CommandVerifier`, `DiscoveryManager`, `OTAManager`, `AuthManager`, `SoundManager`, `WebServer`, `DeviceLifecycleManager`, `MemoryEngine`, `PersonaEngine`, `ProactiveAgent`, `TelemetryWriter`.
    - Nạp từ khóa danh mục thiết bị động vào mô hình nhận diện giọng nói ASR (`asr.initialize(registry)`).
    - Khởi chạy bất đồng bộ các máy chủ mạng (Audio Server, Web Server) và thiết lập kết nối MQTT.
    - Điều phối toàn bộ đường ống xử lý giọng nói: Tiếp nhận văn bản ASR -> Xác định ý định Intent -> Điền slot đa lượt Dialog -> Điều phối lệnh qua WebSocket/MQTT -> Chờ đối soát vòng lặp kín Verify -> Sinh câu nói phản hồi tự nhiên và phát TTS.
    - Quản lý tín hiệu ngắt OS (`SIGINT`, `SIGTERM`) để đóng kết nối và giải phóng tài nguyên hệ thống an toàn.

### 4.2. Quản Lý Thiết Bị, Vòng Đời & Ghép Nối

* [`gateway/registry_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/registry_manager.py):
  - **Công dụng:** Bộ quản lý danh mục thiết bị thế hệ 2 (Device Registry Manager v2).
  - **Chức năng:**
    - Quản lý cấu trúc định danh phân tầng theo chuẩn: Tên nút `{room}-{short}` (ví dụ `livingroom-node01`), Tên kênh tải `{node_id}-{device}` (ví dụ `livingroom-node01-light`).
    - Hỗ trợ bảng từ đồng nghĩa tiếng Việt cho phòng (`ROOM_ALIASES`) và thiết bị (`DEVICE_CANON`), tự động chuyển đổi chuỗi tiếng Việt có dấu sang slug chuẩn không dấu.
    - Lưu trữ bền vững hai lớp: Cơ sở dữ liệu SQLite chuẩn chế độ WAL (`gateway.db`) và sao lưu dự phòng định dạng JSON (`device_registry.json`).
    - Quản lý hàng đợi thiết bị chờ cấp phát (Pending Nodes Queue) cho phép người dùng ghép nối nhanh 1-Click trên Web UI và tự động đẩy cấu hình xuống NVS của ESP32.
    - Giải quyết ánh xạ thông minh từ thực thể câu nói ("đèn trần phòng khách") sang địa chỉ vật lý chính xác `(node_id, channel)`.
* [`gateway/device_lifecycle.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/device_lifecycle.py):
  - **Công dụng:** Tầng quản lý hợp đồng vòng đời thiết bị (Device Lifecycle & Wire v2 Contract Layer).
  - **Chức năng:**
    - Hiện thực hóa máy trạng thái vòng đời thiết bị: Chưa cấp phát (`UNCLAIMED`) $ightarrow$ Đang ghép nối (`CLAIMING`) $ightarrow$ Đã sở hữu (`CLAIMED`) $ightarrow$ Đang đặt lại (`RESETTING`) $ightarrow$ Thu hồi hủy bỏ (`DECOMMISSIONED`).
    - Hiện thực hóa giao thức phân mảnh và tái lắp ghép gói tin Wire v2 (hỗ trợ khung dữ liệu tối đa 250 bytes, phân mảnh chunk 160 bytes) đảm bảo truyền cấu hình dung lượng lớn qua sóng vô tuyến an toàn.
    - Quản lý số thế hệ sở hữu bất biến (`owner_epoch`) và số thứ tự bản tin tăng đơn điệu (`monotonic sequence`), ngăn ngừa thiết bị cũ bị điều khiển trái phép.
    - Giám sát các lỗi phần cứng nghiêm trọng: Quá dòng (`OVER_CURRENT`), quá nhiệt (`OVER_TEMPERATURE`), kẹt dính tiếp điểm relay (`RELAY_WELDED`), lỗi cảm biến đo đạc (`METER_FAULT`).
* [`gateway/discovery_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/discovery_manager.py):
  - **Công dụng:** Quản lý tự động khám phá thiết bị theo chuẩn Home Assistant MQTT Discovery và chuẩn native.
  - **Chức năng:**
    - Lắng nghe các bản tin thông báo thiết bị mới từ mạng: `homeassistant/switch/+/config`, `smarthome/discovery/+`, `smarthome/hello`.
    - Tự động xuất bản (Publish) cấu hình khám phá sang Home Assistant để phần mềm Home Assistant bên ngoài tự nhận diện toàn bộ công tắc, cảm biến năng lượng của hệ sinh thái mà không cần cấu hình thủ công.
* [`gateway/ota_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/ota_manager.py):
  - **Công dụng:** Quản lý nâng cấp phần mềm qua mạng không dây (Over-The-Air Firmware Manager).
  - **Chức năng:**
    - Quản lý kho firmware nhị phân trong thư mục `firmware/`.
    - Phân tích cú pháp tiêu đề nhị phân ESP-IDF (Header Parser): Kiểm tra mã Magic Byte (`0xE9`), nhận diện dòng chip (`ESP32-S3`, `ESP32-C3`), kích thước bộ nhớ flash, tính toán mã băm toàn vẹn SHA-256.
    - Cấp vé tải firmware có chữ ký bảo mật và thời hạn sử dụng (Signed Download Tickets).
    - Kích hoạt tiến trình OTA qua MQTT (`.../ota/trigger`), theo dõi tiến độ nạp (`.../ota/progress`) và kiểm tra sức khỏe thiết bị sau khởi động trước khi hoàn tất chuyển đổi phân vùng flash.
* [`gateway/auth_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/auth_manager.py):
  - **Công dụng:** Quản lý xác thực người dùng, phiên làm việc và phạm vi truy cập thiết bị (Multi-tenant Auth Manager).
  - **Chức năng:**
    - Cơ sở dữ liệu SQLite riêng biệt (`auth.db`) hoạt động ở chế độ WAL.
    - Băm mật khẩu an toàn chuẩn công nghiệp bằng thuật toán PBKDF2-HMAC-SHA256 kết hợp muối ngẫu nhiên (Salt).
    - Quản lý phiên đăng nhập (Session Tokens) có thời hạn sống TTL, tích hợp cơ chế chống tấn công dò mật khẩu vét cạn (Brute-force Rate Limiting).
    - Phân quyền người dùng và gán quyền sở hữu thiết bị theo từng phòng hoặc căn hộ.

### 4.3. Động Cơ Xử Lý Giọng Nói & Tương Tác Hội Thoại

* [`gateway/asr_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/asr_engine.py):
  - **Công dụng:** Động cơ nhận dạng giọng nói tiếng Việt tự động ASR chạy offline tại biên.
  - **Chức năng:**
    - Sử dụng mô hình mạng nơ-ron Zipformer Transducer tiếng Việt chạy thông qua thư viện tối ưu hóa CPU `sherpa-onnx` (thời gian nhận dạng thời gian thực RTF < 0.2 trên Raspberry Pi 4).
    - Tăng cường nhận diện từ khóa nhà thông minh (Hotwords Beam-search Boosting): Tự động nạp danh sách tên phòng, tên thiết bị, hành động để ưu tiên giải mã chính xác trong môi trường có tiếng ồn.
    - Bộ hậu xử lý âm học tiếng Việt (Vietnamese Phonetic Post-correction): Tự động sửa lỗi đồng âm thường gặp trong khẩu lệnh nhà thông minh (ví dụ: sửa "bất quá" thành "bật quạt", "bật đen" thành "bật đèn").
* [`gateway/intent_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/intent_engine.py):
  - **Công dụng:** Hệ thống phân tích ý định khẩu lệnh tiếng Việt thế hệ 3 (Intent Engine v3).
  - **Chức năng:**
    - Nguyên tắc kiến trúc tách biệt: Ý định (Intent) $
eq$ Thiết bị (Device) $
eq$ Thực thi (Execution).
    - Đường ống phân tích đa lớp:
      - *Bộ phát hiện phủ định (Negation Detector):* Chặn câu phủ định ("đừng bật đèn", "không được tắt quạt"), không bao giờ bị nhận diện nhầm thành lệnh bật/tắt.
      - *Đường dẫn siêu tốc (Fast Path Rule Engine):* Đối soát mẫu quy tắc trực tiếp, nếu độ tin cậy $\ge 0.95$ sẽ lập tức trả về kết quả trong vòng ~5ms mà không cần gọi mô hình ngôn ngữ lớn LLM.
      - *Mô hình ngôn ngữ NLU biên/đám mây (LLM NLU Engine):* Sử dụng Qwen 2.5 chạy cục bộ trên Pi 4 (qua llama-server cổng 8080) hoặc Gemini Flash Cloud khi gặp câu lệnh phức tạp, ngữ cảnh dài.
      - *Bộ kiểm tra nghiêm ngặt (Strict Validator):* Đối soát kết quả với `RegistryManager`, loại bỏ hoàn toàn hiện tượng ảo giác (Hallucination) thiết bị không tồn tại.
* [`gateway/dialog_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/dialog_manager.py):
  - **Công dụng:** Bộ quản lý hội thoại đa lượt và điền tham số khuyết thiếu (Slot-Filling Manager).
  - **Chức năng:**
    - Tự động phát hiện các câu lệnh thiếu thông tin: Ví dụ khi người dùng chỉ nói "Bật đèn" (thiếu vị trí phòng) hoặc "Cài nhiệt độ" (thiếu số độ).
    - Tạo câu hỏi làm rõ tự nhiên (Clarification Question): "Dạ, anh muốn bật đèn ở phòng nào ạ?".
    - Duy trì phiên hội thoại dở dang (`DialogSession`) gắn với Client ID trong vòng 15 giây.
    - Đặt cờ yêu cầu mở mic tiếp nối (`follow-up`), ra lệnh cho ESP32 tự động bật micro thu âm câu trả lời của người dùng mà không cần người dùng phải gọi lại từ khóa "Hi ESP".
* [`gateway/tts_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/tts_engine.py):
  - **Công dụng:** Động cơ chuyển đổi văn bản phản hồi thành giọng nói tiếng Việt tự nhiên (Text-to-Speech).
  - **Chức năng:**
    - Hỗ trợ song song hai nền tảng:
      - *VieNeu-TTS (On-device):* Mô hình giọng đọc nơ-ron tiếng Việt chạy hoàn toàn offline trên CPU của Pi 4 thông qua ONNX Runtime, không phụ thuộc kết nối Internet.
      - *Microsoft EdgeTTS (Cloud):* Giọng đọc truyền cảm chất lượng cao (Hoài My Neural, Nam Minh Neural).
    - Bộ nhớ đệm âm thanh hai tầng (Disk & RAM LRU Cache): Tự động băm mã MD5 nội dung văn bản để lưu trữ các câu phản hồi cố định ("Dạ em đã bật đèn", "Dạ em đã tắt quạt"), giúp trả về luồng âm thanh tức thì trong 0ms mà không tốn công tính toán lại.
    - Chuyển đổi định dạng âm thanh chuẩn: Giải mã âm thanh sang định dạng PCM thô 16kHz, 16-bit Mono sẵn sàng truyền trực tiếp cho ESP32 phát ra loa.
* [`gateway/sound_manager.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/sound_manager.py):
  - **Công dụng:** Quản lý không gian âm thanh và hiệu ứng âm học của hệ thống (Acoustic System).
  - **Chức năng:**
    - Nạp sẵn và giải mã vào RAM các mẫu âm thanh chuẩn: Âm khởi động hệ thống (`bootup_sound`), âm nhận diện giọng nói thành công (`listen_success`), giai điệu buổi sáng (`morning_sound`), âm chuông thông báo/cảnh báo (`new_noti`), âm báo lệnh sai (`wrong_sound`).
    - Hỗ trợ truyền dòng PCM tức thời về loa ESP32 hoặc phát file MP3 trên giao diện Web Dashboard.
* [`gateway/display_names.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/display_names.py):
  - **Công dụng:** Mô đun chuẩn hóa phát âm và hiển thị tiếng Việt tự nhiên.
  - **Chức năng:**
    - Ánh xạ mã định danh kỹ thuật (`phong_khach`, `den_chum`, `binh_nong_lanh`) thành chuỗi tiếng Việt có dấu chuẩn ngữ pháp ("phòng khách", "đèn chùm", "bình nóng lạnh").
    - Hàm `clean_voice_text()` loại bỏ ký tự markdown, biểu tượng cảm xúc emoji, dấu gạch ngang, đảm bảo loa AI phát âm tự nhiên, lịch sự như người thật.

### 4.4. Truyền Thông Mạng, Server Âm Thanh & Web Dashboard

* [`gateway/mqtt_handler.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/mqtt_handler.py):
  - **Công dụng:** Trình điều phối truyền thông MQTT không đồng bộ kết nối Gateway với các node phần cứng.
  - **Chức năng:**
    - Sử dụng thư viện `aiomqtt` với cơ chế tự động kết nối lại khi đứt mạng (Auto-reconnect & Exponential Backoff).
    - Hỗ trợ xác thực danh tính và mã hóa đường truyền qua chứng chỉ TLS/SSL.
    - Quản lý bộ đệm trạng thái đo lường mới nhất của tất cả các node (`latest_telemetry`, `channel_powers`).
    - Phát lệnh điều khiển kèm số ID phiên làm việc (`session_id`) và số thứ tự bản tin để theo dõi việc nhận xác nhận (Command ACK Tracking).
* [`gateway/audio_server.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/audio_server.py):
  - **Công dụng:** Máy chủ WebSocket âm thanh tốc độ cao phục vụ luồng tiếng nói thời gian thực (Port 8765).
  - **Chức năng:**
    - Thiết lập kết nối song công (Full-duplex) với SubBox và ActionBox.
    - Tiếp nhận luồng khung âm thanh nhị phân (Binary PCM 640 bytes/khung) truyền từ micro của thiết bị.
    - Đẩy âm thanh vào ASR để nhận dạng, đồng thời xen kẽ các bản tin điều khiển dạng văn bản (JSON TEXT Frame) như trạng thái đang nghe, kết quả dịch transcript.
    - Truyền ngược luồng nhị phân các khối âm thanh giọng nói TTS từ Gateway về cho loa của thiết bị phát ra âm thanh.
* [`gateway/web_server.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/web_server.py):
  - **Công dụng:** Máy chủ Web bất đồng bộ và cung cấp giao diện quản trị Aetheria OS / SIC Home (Port 8000).
  - **Chức năng:**
    - Phục vụ ứng dụng web đơn trang SPA (`templates/index.html`) tích hợp mô hình 3D Digital Twin căn hộ, biểu đồ năng lượng thời gian thực, bảng điều khiển công tắc.
    - Cung cấp cổng truyền dữ liệu trực tiếp Server-Sent Events (SSE) giúp cập nhật trạng thái thiết bị và dữ liệu đo điện tức thời lên trình duyệt mà không cần tải lại trang.
    - Cung cấp hệ thống REST API hoàn chỉnh: Đăng nhập/xác thực, điều khiển bật/tắt thiết bị, cấp phát thiết bị mới, quản lý cập nhật OTA, cấu hình giọng nói và thông số hệ thống.

### 4.5. Động Cơ Xác Thực Vòng Lặp Kín & Cơ Sở Dữ Liệu Lịch Sử

* [`gateway/verify_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/verify_engine.py):
  - **Công dụng:** Động cơ xác thực lệnh điều khiển thông qua phản hồi kép khép kín (Closed-Loop Command Verifier).
  - **Chức năng:**
    - **Trọng tâm của hệ thống vòng lặp kín:** Giải quyết triệt để vấn đề "Lệnh đã gửi nhưng thiết bị thực tế có hoạt động hay không?".
    - Đối soát 2 bước nghiêm ngặt:
      - *Bước 1 (Xác nhận logic):* Chờ bản tin ACK phản hồi từ relay của ESP32 xác nhận tiếp điểm đã đóng/ngắt vật lý.
      - *Bước 2 (Xác nhận tải thực tế qua năng lượng):* Đo lường độ biến thiên công suất tiêu thụ ($\Delta P = P_{after} - P_{before}$) thông qua cảm biến BL0942/PZEM-004T.
    - Phân loại trạng thái thực thi chính xác:
      - `CONFIRMED_LOAD`: Relay đã đóng VÀ dòng điện tăng lên tương ứng với tải tiêu thụ (ví dụ: đèn thực sự sáng).
      - `ACK_ONLY`: Relay đã đóng nhưng công suất không đổi (nghi vấn bóng đèn bị cháy đứt tóc, thiết bị chưa cắm phích hoặc hỏng tải).
      - `MISMATCH` / `FAULT`: Tiếp điểm relay bị kẹt hoặc mạch bảo vệ bị ngắt do sự cố.
      - `TIMEOUT`: Thiết bị không phản hồi trong thời gian quy định.
    - Sinh câu thông báo giọng nói thông minh dựa trên kết quả đối soát: "Dạ em đã bật đèn, nhưng dường như bóng đèn chưa sáng hoặc đã bị cháy, anh kiểm tra lại giúp em nhé!".
* [`gateway/telemetry_writer.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/telemetry_writer.py):
  - **Công dụng:** Trình ghi dữ liệu chuỗi thời gian (Time-series Telemetry Writer) vào InfluxDB v2.
  - **Chức năng:**
    - Khởi tạo kết nối đến InfluxDB qua API đồng bộ/bất đồng bộ.
    - Ghi nhận liên tục các trường dữ liệu: Điện áp ($V$), Dòng điện ($I$), Công suất ($P$), Điện năng ($E$), Tần số ($Hz$), Hệ số công suất ($PF$) phân loại theo từng Node ID, từng phòng và từng kênh tải.
    - Cung cấp nguồn dữ liệu sạch để vẽ đồ thị phụ tải thời gian thực và phân tích thống kê tiết kiệm điện trên Grafana / Web Dashboard.

### 4.6. Trí Tuệ Nhân Tạo Tự Chủ & Đồng Hành

* [`gateway/memory_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/memory_engine.py):
  - **Công dụng:** Hệ thống bộ nhớ 3 tầng (3-Tier Memory Architecture) phục vụ học tập thói quen người dùng.
  - **Chức năng:**
    - Tầng 1 - Trí nhớ ngắn hạn (STM - Short-Term Memory): Lưu trên RAM, ghi nhớ ngữ cảnh tức thời trong phiên trò chuyện.
    - Tầng 2 - Trí nhớ trung hạn (MTM - Medium-Term Memory): Cơ sở dữ liệu SQLite (`smart_journal`), lưu vết toàn bộ nhật ký khẩu lệnh, thời điểm thực hiện trong ngày, thứ trong tuần, và kết quả xác thực tải.
    - Tầng 3 - Trí nhớ dài hạn (LTM - Long-Term Memory): Dữ liệu tổng hợp từ InfluxDB và SQLite để rút ra thói quen sinh hoạt định kỳ (ví dụ: người dùng luôn tắt đèn ngủ lúc 23:00 và bật quạt lúc 12:30).
* [`gateway/persona_engine.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/persona_engine.py):
  - **Công dụng:** Động cơ nhân cách hóa trợ lý ảo thành người bạn đồng hành sống động ("Lumi").
  - **Chức năng:**
    - Kho tri thức cục bộ (Offline Persona): Chứa sẵn thư viện các bài hát thiếu nhi vui tươi, truyện cười dân gian, lời thăm hỏi ân cần khi người dùng đi làm về mệt mỏi.
    - Tích hợp Gemini Flash Cloud: Khi có Internet, gửi các câu hỏi trò chuyện, tâm sự của người dùng lên mô hình ngôn ngữ thông minh để nhận về câu trả lời sâu sắc, dí dỏm chỉ trong 0.4 giây.
* [`gateway/proactive_agent.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/proactive_agent.py):
  - **Công dụng:** Đặc vụ canh gác an toàn và tương tác chủ động (Autonomous House Sentry Daemon).
  - **Chức năng:**
    - Canh gác an toàn tải điện (Safety Sentry): Chạy ngầm liên tục theo dõi các thiết bị sinh nhiệt hoặc công suất lớn (bình nóng lạnh, bàn là, bếp điện). Nếu phát hiện thiết bị bật liên tục quá 30 phút mà không có người tương tác, Lumi sẽ chủ động phát âm thanh thông báo và nhắc nhở gia chủ qua giọng nói: "Anh ơi, bình nóng lạnh phòng tắm đã bật hơn 30 phút rồi, anh kiểm tra xem đã sử dụng xong chưa nhé!".
    - Tương tác chủ động theo nhịp sinh học: Lời chào buổi sáng vui vẻ (07:00 - 08:30), lời nhắc ngủ ngon (22:00 - 22:30).
    - Tuân thủ giờ giới nghiêm ban đêm (Quiet Hours 22:30 - 07:00): Tuyệt đối giữ im lặng, không tự ý phát âm thanh làm phiền giấc ngủ của gia đình.

### 4.7. Phân Hệ Core V1 Doanh Nghiệp (`gateway/core_v1/`)

Thư mục `Gateway/gateway/core_v1` triển khai tầng giao thức doanh nghiệp Home Competition (HC Core V1) với độ tin cậy và an ninh bảo mật cấp công nghiệp:

* [`gateway/core_v1/__init__.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/__init__.py) & [`gateway/core_v1/__main__.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/__main__.py):
  - **Công dụng:** Khởi tạo package và cung cấp giao diện dòng lệnh độc lập để khởi động riêng phân hệ Core V1 khi cần kiểm thử.
* [`gateway/core_v1/protocol.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/protocol.py):
  - **Công dụng:** Đặc tả và hiện thực hóa định dạng gói tin nhị phân HC v1 có xác thực mật mã.
  - **Chức năng:**
    - Tiêu đề khung (Header) chuẩn 38 bytes định dạng Little-Endian không dùng struct-cast nguy hiểm: Chứa Magic `HC`, Version, Message Type (`HELLO`, `IDENTITY_CHALLENGE`, `COMMAND`, `STATE_REPORT`, `OTA_CHUNK`), Message ID 64-bit ngẫu nhiên, Source/Destination ID 32-bit, Boot ID 64-bit, Sequence Number và Config Revision.
    - Payload tối đa 196 bytes, đuôi khung gắn mã băm xác thực HMAC-SHA256 cắt ngắn 16 bytes (tổng khung tối đa đúng 250 bytes phù hợp với giới hạn vật lý của gói tin ESP-NOW).
* [`gateway/core_v1/registry.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/registry.py):
  - **Công dụng:** Sổ đăng ký trạng thái và quyền sở hữu thiết bị bất biến của Core V1.
  - **Chức năng:** Quản lý cơ sở dữ liệu SQLite lưu trữ danh tính xuất xưởng (`factory_id`), khóa bí mật riêng của từng nút (`device_key`), số thế hệ sở hữu, số chuỗi thứ tự bản tin để ngăn chặn hoàn toàn tấn công phát lại.
* [`gateway/core_v1/database.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/database.py):
  - **Công dụng:** Quản trị kết nối cơ sở dữ liệu SQLite hiệu năng cao của Core V1 với chế độ ghi nhật ký trước WAL (Write-Ahead Logging) và tự động thực thi các file kịch bản nâng cấp phiên bản dữ liệu (Migrations).
* [`gateway/core_v1/bridge.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/bridge.py):
  - **Công dụng:** Cầu nối liên lạc chuyển đổi giữa các khung nhị phân HC v1 và hệ thống bản tin MQTT/WebSocket của Gateway.
* [`gateway/core_v1/api.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/api.py):
  - **Công dụng:** Cung cấp hệ thống REST API và WebSocket có xác thực mã hóa phục vụ ứng dụng điều khiển di động Flutter (DTV Energy App).
* [`gateway/core_v1/ha.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/ha.py):
  - **Công dụng:** Mô đun đồng bộ thực thể trạng thái giữa Core V1 và máy chủ Home Assistant qua MQTT.
* [`gateway/core_v1/provisioning.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/provisioning.py):
  - **Công dụng:** Tiến trình cấp phát và ghép nối thiết bị mới bằng mật mã học (Cryptographic Provisioning).
  - **Chức năng:** Sử dụng cơ chế mã thiết lập bí mật (Setup Code), phát sinh số ngẫu nhiên Nonce thách thức, xác minh sự hiện diện vật lý của con người và trao đổi khóa phiên an toàn tuyệt đối.
* [`gateway/core_v1/ota.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/ota.py):
  - **Công dụng:** Giao thức nạp phần mềm OTA phân mảnh theo từng khối nhỏ độc lập (Chunked OTA Transport).
  - **Chức năng:** Chia nhỏ file firmware thành các gói nhị phân nhỏ truyền qua ESP-NOW, yêu cầu bên nhận gửi ACK xác nhận cho từng khối, hỗ trợ truyền lại từng khối bị lỗi mà không phải nạp lại từ đầu.
* [`gateway/core_v1/release.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/release.py):
  - **Công dụng:** Quản lý và kiểm tra tính toàn vẹn của các bản phát hành firmware thông qua file manifest có chữ ký bảo mật.
* [`gateway/core_v1/simulator.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/simulator.py):
  - **Công dụng:** Môi trường giả lập thiết bị phần cứng SubBox và ActionBox trong bộ nhớ RAM, phục vụ việc chạy tự động hàng trăm test case mà không cần cắm mạch thật.
* [`gateway/core_v1/voice.py`](file:///home/tuan/Home-Assistant-IoT-/Gateway/gateway/core_v1/voice.py):
  - **Công dụng:** Ánh xạ các ý định giọng nói tiếng Việt vào các thiết bị và kênh tải được quản lý dưới mô hình Core V1.

---

## 5. SƠ ĐỒ PHỐI HỢP LIÊN TẦNG & LUỒNG HOẠT ĐỘNG THỰC TẾ

### 5.1. Luồng 1: Điều Khiển Giọng Nói Tiếng Việt Vòng Lặp Kín (Closed-Loop Voice Control)

```
[Người dùng] 
     │ Nói "Hi ESP, bật đèn phòng ngủ"
     ▼
[ActionBox V2 - Mic INMP441]
     │ Nhận diện từ khóa KWS "Hi ESP" -> Sáng LED Voice
     │ Truyền luồng PCM 16kHz qua ESP-NOW
     ▼
[SubBox - ESP32-S3]
     │ Nhận gói âm thanh -> PSRAM Ring Buffer -> Energy VAD
     │ Truyền trực tiếp qua WebSocket tới Gateway (ws://...:8765)
     ▼
[Gateway - AudioServer & ASREngine]
     │ Sherpa-ONNX giải mã PCM -> Text: "bật đèn phòng ngủ"
     ▼
[Gateway - IntentEngine v3]
     │ Phát hiện không phủ định -> Fast-path khớp mẫu "bật" + "đèn" + "phòng ngủ"
     │ RegistryManager đối soát: Thiết bị hợp lệ -> livingroom-node01-light (RL1)
     ▼
[Gateway - Command Dispatch]
     │ Gửi bản tin lệnh qua MQTT Topic: smarthome/command/livingroom-node01
     ▼
[SubBox / ActionBox V2]
     │ Nhận lệnh -> DeviceManager -> Kích xung 30ms đóng Relay 1
     │ BL0942 ghi nhận dòng điện tăng từ 0.00A lên 0.45A (P = 99W)
     │ Gửi bản tin ACK và Telemetry cập nhật về Gateway
     ▼
[Gateway - VerifyEngine]
     │ Kiểm tra chéo: Có ACK + ΔP = +99W > 5W -> Đạt chuẩn CONFIRMED_LOAD!
     ▼
[Gateway - TTSEngine & AudioServer]
     │ Sinh câu trả lời: "Dạ, em đã bật đèn phòng ngủ rồi ạ!"
     │ Mã hóa PCM và stream ngược lại loa của SubBox phát cho người dùng nghe
```

### 5.2. Luồng 2: Canh Gác An Toàn Năng Lượng & Bảo Vệ Ngắt Cứng

```
[Tải điện phòng tắm / Bình nóng lạnh]
     │ Tiêu thụ quá dòng đột biến (> 16A) do chạm chập
     ▼
[ActionBox V2 - IC BL0942]
     │ Đọc mẫu dòng điện chu kỳ 100ms: I_RMS = 18.5A
     ▼
[ActionBox V2 - SafetySupervisor]
     │ Phát hiện vượt ngưỡng an toàn định mức tức thời
     │ < 20ms: Lập tức kích xung ngắt ngay Relay cấp nguồn!
     │ Đánh dấu cờ lỗi phần cứng: FAULT_OVER_CURRENT
     │ Nhấp nháy LED đỏ cảnh báo
     ▼
[ActionBox V2 -> SubBox -> Gateway]
     │ Phát gói tin khẩn cấp qua ESP-NOW và MQTT Topic: smarthome/alert
     ▼
[Gateway - ProactiveAgent & SoundManager]
     │ Phát âm thanh cảnh báo NEW_NOTI qua loa
     │ Đọc loa cảnh báo: "Cảnh báo khẩn cấp! Bình nóng lạnh bị quá dòng, hệ thống đã tự động ngắt điện an toàn!"
```

---

## 6. TỔNG KẾT VÀ BẢNG TRA CỨU NHANH DANH MỤC FILE

| Phân Hệ | Đường dẫn thư mục | Số lượng file | Vai trò chính |
|---|---|:---:|---|
| **SubBox** | `Firmware/firmware_esp/SubBox/src` | **40 file** | Bộ điều phối phòng cục bộ ("Local Brain"), cầu nối âm thanh I2S, đệm PSRAM, VAD, ASR streaming, NLU tiếng Việt nội bộ, tự động hóa phòng độc lập khi mất mạng. |
| **ActionBox V2** | `Firmware/firmware_esp/ActionBox_V2/src` | **27 file** | Thiết bị chấp hành thông minh điều khiển 3 relay chốt (latching), đo điện năng 3 kênh bằng IC BL0942, mic thu âm I2S DMA, nhận diện từ khóa KWS TinyML, bảo vệ ngắt cứng <20ms. |
| **Gateway** | `Gateway/gateway` (bao gồm `core_v1`) | **35 file** | Trung tâm xử lý thông minh: ASR Zipformer offline, NLU Intent v3, TTS nơ-ron, đối soát tải vòng lặp kín VerifyEngine, Web Dashboard SSE, InfluxDB chuỗi thời gian, an ninh Core V1. |
| **TỔNG CỘNG** | **Toàn bộ hệ thống** | **102 file** | **Hệ sinh thái Nhà thông minh hoàn chỉnh, tin cậy cao, bảo mật doanh nghiệp và tối ưu cho ngôn ngữ tiếng Việt.** |
