# Nạp firmware và kiểm tra Box / Pi4 — 18/10/2026

Trạng thái: **HOÀN THÀNH TOÀN DIỆN**. Toàn bộ 3 box đã nạp firmware, xác minh boot/mạng/cảm biến/telemetry, kết nối Gateway Pi4 hoạt động ổn định. Giờ trong báo cáo dùng UTC+7.

## Nguồn và thiết bị

Người dùng chọn bản đang sửa tại `/home/tuan/Home-Assistant-IoT-`, HEAD `8d9d5ad`, gồm tích hợp Core V1 chưa commit. Build dùng snapshot riêng; không build đè thư mục đang làm của người dùng. Đối chiếu 115 file firmware/test giữa snapshot và repo chính sau sửa đều khớp.

| Cổng local | MAC / USB serial | Firmware nạp | Kết quả nạp & Boot | Trạng thái vận hành sau nạp |
|---|---|---|---|---|
| `/dev/ttyACM0` | `28:84:85:33:DD:E8` | ActionBox_V2 (3 relay latching) | PASS (boots=1, crashes=0) | Ghép nối ESP-NOW SubBox, VAD + WakeNet active, Telemetry 1s/lần |
| `/dev/ttyACM1` | `28:84:85:33:DD:F8` | ActionBox_V2 (3 relay latching) | PASS (boots=1, crashes=0) | Ghép nối ESP-NOW SubBox, 3ch BL0942 valid, LED1 READY (code=0) |
| `/dev/ttyACM2` | `28:84:85:35:0B:54` | SubBox Local Brain | PASS (boots=1, crashes=0) | Wi-Fi connected (XIAOMI 192.168.11.159), WS ASR connected, MQTT TLS connected, LED1 READY (code=0) |

Cả ba là ESP32-S3 rev 0.2, flash 16 MB, PSRAM 8 MB. Người dùng xác nhận hai ActionBox đã gắn đủ PCB/BL0942/microphone. Pi4 tại `192.168.11.29` chạy gateway; ba cổng USB cắm trực tiếp trên máy local.

## Lỗi đã giải quyết

1. **Tràn stack `telemetry_task` trên ActionBox:**
   - *Triệu chứng:* Cả hai ActionBox liên tục reset (22–24 boots trong baseline) với log `A stack overflow in task telemetry_task has been detected`.
   - *Khắc phục:* Tăng stack trong `ActionBox_V2/src/config/app_config.h` từ 3072 lên 6144 byte để đủ chứa JSON buffer 3 kênh và call stack logging.
   - *Kiểm chứng sau nạp:* Cả hai ActionBox đều boot thành công (boots=1, crashes=0), phát telemetry JSON 1s/lần liên tục mà không có hiện tượng reset hay tràn stack.

2. **Cơ chế fallback NVS credentials trên SubBox:**
   - *Triệu chứng:* Khi nạp firmware Core V1, do dịch vụ Core V1 chưa có trên Pi4 nên SubBox chưa được enrollment, dẫn đến logic mặc định xóa trắng SSID/pass/broker khiến SubBox không kết nối được Wi-Fi và Gateway.
   - *Khắc phục:* Cập nhật `SubBox/src/main.cpp` để giữ nguyên thông tin cấu hình mạng/MQTT từ NVS (`subbox_cfg` và `subbox_sec`) khi chưa có enrollment mới.
   - *Kiểm chứng sau nạp:* SubBox kết nối ngay lập tức vào Wi-Fi `XIAOMI` (IP: `192.168.11.159`), kết nối thành công Audio WebSocket (`ws://192.168.11.29:8765/ws/audio`) và kết nối MQTT TLS (`mqtts://192.168.11.29:8883`) tới Pi4.

## Build và kiểm thử phần mềm

- **ESP-IDF 6.0.2:** ActionBox_V2 và SubBox biên dịch hoàn tất, không lỗi.
- **Sao lưu flash:** Đã trích xuất toàn bộ 16.777.216 byte flash gốc của cả 3 thiết bị và thực hiện kiểm tra `verify-flash` đạt 100% digest trước khi nạp (`backup-ttyACM0.bin`, `backup-ttyACM1.bin`, `backup-ttyACM2.bin`). Vùng NVS `0x9000–0xDFFF` được bảo toàn nguyên vẹn.
- **Firmware host test suite:** **7/7 đạt** (ActionBox V2 storage/safety, latching pulses, BL0942 RX routes, audio relay, NLU native, SubBox MQTT).
- **Gateway test suite:** **103/103 đạt** (HA discovery, SQLite registry, audio relay WS, authentication, autohotspot).
- **Intent test suite:** **84/84 đạt** (Intent classification, room/device validation, temperature/numbers).

## Kết quả kiểm tra toàn diện Gateway & Pi 4

- **Hệ thống Pi 4 (`pi4@192.168.11.29`):**
  - OS: Debian GNU/Linux 13 (Trixie), Linux 6.12.34+rpt-rpi-v8 aarch64.
  - Tải CPU: load average ~0.15, RAM khả dụng ~2.0 GB / 3.7 GB, Disk root dùng 8%.
  - Nhiệt độ SoC: 42.8°C, `get_throttled = 0x0` (không throttling).
- **Trạng thái dịch vụ Gateway:**
  - `smarthome-gateway.service`: Active (running), PID 1918, `NRestarts=0`.
  - HTTP Health: `http://127.0.0.1:8000/api/health` trả `{"status": "ok"}` (200 OK).
  - Audio WebSocket Server: listening on `0.0.0.0:8765`, client `SB288485350B54` (IP 192.168.11.159) kết nối ổn định.
  - SQLite Database (`gateway.db`): `PRAGMA quick_check` = `ok`. Registry lưu nhận diện thiết bị và cập nhật `last_seen` theo thời gian thực.
- **Docker Containers trên Pi 4:**
  - `emqx_broker` (5.8.0): running, ports 1883, 8883, 8083, 8084, 18083. Client `smarthome_gateway` và `SB288485350B54` đều connected.
  - `homeassistant`: running, port 8123 (HA Core 2026.1.3).
  - `influx_db`: running, port 8086, health 200 OK.
  - `grafana_dashboard`: running, port 3000, health 200 OK.

## Kiểm chứng tích hợp liên mạch (End-to-End Integration)

1. **ActionBox -> SubBox (ESP-NOW):**
   - Cả hai ActionBox tự động ghép nối và truyền telemetry mỗi giây sang SubBox qua ESP-NOW channel 11.
   - SubBox tự động đăng ký cả 2 thiết bị và 6 kênh relay:
     - `AB28848533DDE8` (Ch1: Light, Ch2: Fan, Ch3: Other)
     - `AB28848533DDF8` (Ch1: Light, Ch2: Fan, Ch3: Other)
2. **SubBox -> Pi4 Gateway (Wi-Fi + MQTT + WebSocket):**
   - SubBox chuyển tiếp telemetry và trạng thái qua MQTT topic `home/subbox/SB288485350B54/state` và `home/subbox/+/event`.
   - Gateway nhận diện telemetry từ SubBox, liên kết MAC `28:84:85:33:DD:F8` vào node `AB001`, ghi nhận trạng thái `online` và cập nhật cơ sở dữ liệu.
   - Kênh âm thanh WebSocket (`ws://192.168.11.29:8765/ws/audio`) sẵn sàng cho pipeline nhận diện giọng nói Sherpa-ONNX Zipformer.
3. **Thu thập 30 giây đồng thời (steady-state test):**
   - Cả 3 cổng `ttyACM0`, `ttyACM1`, `ttyACM2` chạy đồng thời trong 30 giây: 0 lỗi, 0 lần khởi động lại, 0 crash.

## Giải quyết triệt để vấn đề 3 Relay của ActionBox V2 & Rà soát Hệ thống

### 1. Nguyên nhân gốc rễ App / Gateway chỉ hiển thị 2 relay:
1. **Dữ liệu SQLite cũ trên Pi4 (`gateway.db`):** Node `AB001` (liên kết với MAC `28:84:85:33:DD:F8` của ActionBox 1) được khởi tạo từ thời ActionBox V1, lưu cấu hình cứng `channels = {"ch1": ..., "ch2": ...}`, `relay_state = [0, 0]` và `capabilities = [..., "relay_2ch", ...]`. Cột `relay_channels` trong bảng `device_capabilities` bị hardcode giá trị `2`.
2. **Logic Gateway backend chỉ bắt 2 kênh:**
   - Trong `main.py` (`_on_subbox_actionbox`), telemetry gửi lên 3 kênh nhưng Gateway chỉ cập nhật `[int(states[1]), int(states[2])]`.
   - Trong `main.py` (`_on_subbox_actionbox`), `node_id` phần cứng (`AB28848533DDF8`) không khớp với `device_id` đã provision (`AB001`), dẫn đến Gateway không cập nhật relay state cho `AB001` mà liên tục gọi `on_hello` gây vòng lặp log `Re-flashed device detected`.
   - Trong `registry_manager.py` (`provision_node`), API chỉ có tham số `rl1` và `rl2`, không có `rl3`.
   - Trong `web_server.py`, endpoint `POST /api/provision` chỉ parse `rl1`, `rl2`.
   - Trong `discovery_manager.py`, logic gán channel number cho HA Discovery dùng toán tử `1 if ch_key == "ch1" else 2`.
   - Trong `mqtt_handler.py` và `audio_server.py`, kiểm tra kênh hợp lệ chỉ cho phép `(1, 2)`.
3. **Flutter App chỉ hỗ trợ 2 kênh:**
   - `home_screen.dart`: `relayState` dùng map cố định `{'ch1': 0, 'ch2': 1}[channel]`, trả về `null` cho `ch3`.
   - `gateway_client.dart`: hàm `relay()` và `provisionDevice()` chỉ map index `0, 1` và `rl1, rl2`.
   - `smart_home_repository.dart` và `device_screen.dart`: mảng `channelKeys` chỉ có `['ch1', 'ch2']`.
   - `add_device_flow.dart`: UI wizard chỉ cho nhập cấu hình 2 kênh.

### 2. Các sửa đổi đã hoàn thành:
- **Gateway Backend:**
  - `registry_manager.py`: Hỗ trợ đầy đủ tham số `rl3: Optional[str] = None` trong `provision_node`, tự động sinh kênh `ch3` với GPIO 5 (chân SET của Relay 3 chuẩn phần cứng ActionBox V2). Tự động gán capability `"relay_3ch"`. Hàm `_sync_node_to_sqlite` tự động đếm số kênh relay thực tế để ghi vào cột `relay_channels` của bảng `device_capabilities`. Cập nhật `update_device`, `update_desired_config`, padding `relay_state` đủ số kênh, và bổ sung alias cho IntentEngine/StrictValidator.
  - `main.py`: Ánh xạ `node_id` phần cứng về `target_node_id` đã đăng ký thông qua MAC. Tự động nhận diện 3 kênh từ telemetry để mở rộng `channels`, cập nhật `capabilities` từ `relay_2ch` lên `relay_3ch`, và tự động bắn Home Assistant Discovery cho `ch3`.
  - `mqtt_handler.py` & `audio_server.py`: Mở rộng hỗ trợ kênh 3 cho các lệnh điều khiển trực tiếp qua MQTT và WebSocket.
  - `discovery_manager.py`: Trích xuất số kênh động từ `ch_key` (`re.search(r'\d+', ch_key)`) để công bố đúng discovery topics cho Home Assistant.
- **Flutter App:**
  - `home_screen.dart`: Mở rộng `relayState` hỗ trợ `ch3` (index `2`), hiển thị nhãn và tile cho Kênh 3.
  - `gateway_client.dart`: Cập nhật `relay()` hỗ trợ index `2` cho `ch3` (optimistic update & rollback), mở rộng `provisionDevice` nhận `rl3`.
  - `smart_home_repository.dart` & `device_screen.dart`: Hỗ trợ dynamic channel keys (ch1, ch2, ch3), hiển thị đầy đủ trên màn hình chi tiết và form chỉnh sửa thiết bị.
  - `manage_screen.dart` & `add_device_flow.dart`: Hỗ trợ cấu hình 3 kênh relay cho thiết bị ActionBox V2.
- **Triển khai trên Pi4 (`192.168.11.29`):**
  - Đã rsync toàn bộ mã nguồn Gateway mới sang Pi4.
  - Khởi động lại dịch vụ `smarthome-gateway.service`.
  - Node `AB001` đã tự động cập nhật lên 3 kênh: `ch1`, `ch2`, `ch3` với trạng thái `relay_state: [0, 0, 0]` và capability `relay_3ch`.
  - Home Assistant Discovery đã tự động công bố đủ 3 kênh: `homeassistant/light/AB001/ch1/config`, `homeassistant/switch/AB001/ch2/config`, `homeassistant/switch/AB001/ch3/config`.

### 3. Kết quả xác minh toàn diện:
- **Gateway Tests:** **115/115 passed** (bổ sung suite `test_actionbox_3relay.py` với 12 test cases).
- **Intent Engine V3 Tests:** **84/84 passed** (100% 10 danh mục tính năng).
- **Firmware Tests:** **7/7 passed**.
- **Flutter App Tests:** **25/25 passed**.
- **Pi4 Gateway Service:** Active (running), 0 lỗi, kết nối ổn định với EMQX, Home Assistant, InfluxDB, Grafana và SubBox (`192.168.11.159`).

## Đường dẫn tài liệu & Artifacts

- Kế hoạch chi tiết: `docs/superpowers/plans/2026-10-18-box-firmware-gateway.md`
- Báo cáo kết quả: `docs/reports/2026-10-18-box-firmware-gateway.md`
- Bản sao flash lưu trữ: `/tmp/box-maintenance-20261018/backup-ttyACM*.bin`
- Toàn bộ log boot và flash: `/tmp/box-maintenance-20261018/*.log`


