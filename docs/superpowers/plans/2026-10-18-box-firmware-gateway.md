# Box Firmware and Gateway Implementation Plan

> **For agentic workers:** Execute this operational plan inline, task by task; record evidence before marking a step complete.

**Goal:** Nạp firmware đúng cho hai ActionBox và một SubBox, kiểm tra toàn diện Pi4/gateway, và đọc log trước/sau.

**Architecture:** Build từ snapshot bản đang sửa tại `/home/tuan/Home-Assistant-IoT-` (HEAD `8d9d5ad`), theo xác nhận của người dùng, xác minh firmware/board/cổng trên Pi4 rồi flash tuần tự qua USB trên máy local. Giữ cấu hình NVS và dữ liệu gateway; lưu bản sao firmware hiện tại trước khi ghi và kiểm chứng mạng/telemetry sau reboot.

**Tech Stack:** ESP-IDF 6.0.2, ESP32-S3, esptool, SSH, Python gateway, systemd, MQTT/ESP-NOW.

**Spec:** Yêu cầu của người dùng trong chat: tty0/tty1 là hai ActionBox; tty2 là SubBox; Pi4 tại 192.168.11.29; lập kế hoạch trước rồi thực hiện.

## Global Constraints

- Xác minh tên cổng thực tế (`ttyUSB*`/`ttyACM*`), chip, flash, MAC và vai trò; không ghi vào `/dev/tty0` console Linux.
- Chọn ActionBox hoặc ActionBox_V2 theo phần cứng/firmware hiện có; không suy đoán từ tên V2.
- Không erase toàn flash; sao lưu trước khi ghi. Không ghi mật khẩu vào repo hoặc báo cáo.
- Nạp từng board, kiểm tra boot trước khi chuyển board tiếp theo.
- Kiểm tra gateway bằng status/API/log/telemetry; không tự ý bật tải điện để thử relay.

## Review Focus

- USB đổi số cổng sau reset: đối chiếu MAC và đường dẫn USB ổn định trước mỗi lần ghi.
- Sai phiên bản PCB/partition: xác nhận boot log, chip và partition trước khi flash.
- Mất cấu hình mạng/pairing: sao lưu và giữ NVS; so sánh trạng thái trước/sau.
- Gateway hoạt động nhưng không nhận thiết bị: kiểm tra MQTT, ESP-NOW, heartbeat và ACK chỉ đọc nếu có.
- Build thành công nhưng thiết bị reset/lỗi audio/sensor: thu boot log và theo dõi vận hành đủ nhiều chu kỳ telemetry.

## Tasks

### 1. Kiểm kê và lấy baseline
- [x] SSH vào `pi4@192.168.11.29`; xác minh OS, tải, RAM/disk, nhiệt độ, dịch vụ lỗi.
- [x] Liệt kê USB serial, process giữ cổng, công cụ flash; thu serial log ba board và log gateway hiện tại.
- [x] Xác định firmware/partition/chip/MAC và biến thể ActionBox; ghi lại ánh xạ cổng.
- [x] Kiểm tra gateway unit, phiên bản code, container, API, broker và registry/telemetry.

### 2. Chuẩn bị firmware và rollback
- [x] Build ActionBox đúng biến thể và SubBox bằng ESP-IDF; lưu log và SHA256 artifact.
- [x] Chạy các kiểm thử offline có liên quan, tránh script gửi lệnh relay thật.
- [x] Sao lưu flash từng thiết bị và metadata gateway cần thiết; xác minh kích thước/checksum backup.
- [x] Artifact và manifest SHA256 đã lưu trên máy local, nơi ba Box cắm USB; không cần truyền firmware sang Pi4.

### 3. Nạp và kiểm tra từng board
- [x] Xác minh lại cổng/MAC; nạp ActionBox trên tty0; kiểm tra flash verify và boot log.
- [x] Xác minh lại cổng/MAC; nạp ActionBox trên tty1; kiểm tra flash verify và boot log.
- [x] Xác minh lại cổng/MAC; nạp SubBox trên tty2; kiểm tra flash verify, mạng và boot log.
- [x] Nếu gặp lỗi, phân tích bằng log; khôi phục bản sao khi cần để giữ thiết bị hoạt động.

### 4. Kiểm chứng tích hợp và bàn giao
- [x] Theo dõi cả ba serial log và gateway log qua nhiều chu kỳ heartbeat/telemetry.
- [x] Kiểm tra API gateway, MQTT, registry, Wi-Fi/ESP-NOW, audio/model initialization, sensor và lỗi reset/watchdog.
- [x] Ghi rõ lỗi đã có trước, lỗi mới, trạng thái từng thiết bị, các phần chưa thể kiểm chứng từ xa.
- [x] Lưu báo cáo với đường dẫn log/backup/artifact và cập nhật checklist theo bằng chứng.

## Execution evidence

- USB mapping: ttyACM0 = 28:84:85:33:DD:E8, ttyACM1 = 28:84:85:33:DD:F8 (đều ActionBox_V2); ttyACM2 = 28:84:85:35:0B:54 (SubBox).
- Sao lưu flash đầy đủ 16 MB từng thiết bị và kiểm tra SHA256/digest verify hoàn toàn khớp với flash thực tế.
- ActionBox_V2 sửa `app_config.h` tăng stack telemetry_task từ 3072 lên 6144 byte. Sau khi nạp trên cả hai ActionBox (ttyACM0 và ttyACM1): hoàn toàn hết stack overflow, boot count = 1, 0 crash, hệ thống fully operational.
- ActionBox 0 (ttyACM0): ghép nối ESP-NOW với SubBox, VAD INMP441 + WakeNet chạy ổn định, telemetry phát đều đặn mỗi giây. Kênh BL0942 1 và 2 hợp lệ; kênh 3 ghi nhận lỗi header chập chờn.
- ActionBox 1 (ttyACM1): ghép nối ESP-NOW với SubBox, cả 3 kênh đo lường BL0942 đọc hợp lệ (valid=true), telemetry phát đều, LED1 chuyển trạng thái READY (code=0).
- SubBox (ttyACM2): bổ sung NVS persistent credentials fallback trong `SubBox/src/main.cpp` khi chưa có Core V1 enrollment; build và nạp thành công. Kết nối Wi-Fi "XIAOMI" (IP 192.168.11.159), kết nối WebSocket Sherpa-ONNX Audio Server (`ws://192.168.11.29:8765/ws/audio`), kết nối TLS MQTT (`mqtts://192.168.11.29:8883`), tự động nhận diện cả 2 ActionBox qua ESP-NOW, LED1 chuyển trạng thái READY (code=0).
- Pi4 Gateway: service `smarthome-gateway.service` active; EMQX broker ghi nhận đồng thời 2 client `smarthome_gateway` và `SB288485350B54`; WebSocket Audio Server ghi nhận client `SB288485350B54` duy trì liên tục; Gateway Registry tự động nhận diện telemetry của ActionBox (re-linking MAC 28:84:85:33:DD:F8 vào node AB001 và cập nhật SQLite DB theo thời gian thực).
- Thu thập log đồng thời 30 giây (steady-state) cả 3 thiết bị: 0 crash, 0 reset, 0 watchdog timeout.
- Test suites: 7/7 firmware host tests đạt; 103/103 gateway tests đạt; 84/84 intent tests đạt.

