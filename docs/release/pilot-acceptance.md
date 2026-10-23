# Commercial Hardware, HIL & Pilot User Acceptance Protocol (Milestone M4 - Task T16)

*Date: 2026-10-20*  
*Target Environment: ActionBox V2 Commercial Board, SubBox Gateway Master, SIC Home Android App*

---

## 1. Executive Summary & Quality Bar

Task T16 defines the empirical Hardware-in-the-Loop (HIL) acceptance criteria, commercial PCB review verification, and 10-user pilot acceptance protocol. **No commercial release is permitted based purely on simulated unit tests; physical verification on commercial hardware is an uncompromised requirement.**

---

## 2. Commercial Hardware Review & Pinout Verification

### ActionBox V2 Commercial Board
- **Microcontroller:** ESP32-S3 (Dual-core 240MHz, 8MB Flash)
- **Power Sensor:** 3 IC BL0942 đo năng lượng độc lập cho 3 kênh qua UART (TX chung GPIO 9, RX CH1: GPIO 10, RX CH2: GPIO 11, RX CH3: GPIO 12), dữ liệu hiệu chuẩn lưu trong phân vùng NVS `nvs_calib` tại nhà máy
- **Audio Mic (Voice):** INMP441 I2S (GPIO 8 DIN, GPIO 17 WS, GPIO 18 SCK)
- **Relay Configuration:**
  - Cả 3 kênh đều là **Dual-coil Magnetic Latching Relay** (Xung điều khiển 50ms):
    - Kênh 1 (CH1): GPIO 16 Set / GPIO 15 Reset
    - Kênh 2 (CH2): GPIO 7 Set / GPIO 6 Reset
    - Kênh 3 (CH3): GPIO 5 Set / GPIO 4 Reset
- **Buttons & Physical Controls:**
  - **BUT1 (GPIO 13):** Vừa là nút điều khiển tải kênh 1 vừa là nút bảo trì/reset hệ thống.
  - **BUT2 (GPIO 14):** Nút điều khiển tải kênh 2.
  - *Lưu ý an toàn:* Tuyệt đối không dùng GPIO 9 làm nút bấm (GPIO 9 là chân UART TX của chip đo năng lượng BL0942). Nút BOOT chỉ dùng cho nạp firmware qua USB.
- **LED Indicators:**
  - **LED1 (GPIO 3 - System & Network):** Solid Blue = Connected; Slow Blinking Blue (1 Hz) = Ready to claim; Fast Blinking (Nháy nhanh) = Vũ trang Network Reset; Double Blinking (Nháy kép) = Vũ trang Safe Factory Reset.
  - **LED2 (GPIO 2 - Voice Assistant / System):** Đèn phản hồi thoại / trợ lý ảo offline (Cyan pulsing = Listening; Green pulse = Acknowledged).

### SubBox Master Gateway
- **Microcontroller:** ESP32-S3 (Dual-core 240MHz, 8MB Flash)
- **Network Interfaces:** Wi-Fi 802.11 b/g/n (SoftAP & Station) + ESP-NOW Master
- **Buttons:**
  - **Nút CONFIG:** GPIO 1 (chính xác).
  - **Nút Action:** GPIO 2.
- **Audio I2S Interface:** Micro INMP441 + Bộ khuếch đại âm thanh MAX98357A.
- **Capacity:** Strict hardware limit of **4 child ActionBoxes** (Audit B07 / T03)

---

## 3. Physical Button Rhythm & Safety Timing Runbook

Nhịp nút bấm vật lý trên ActionBox V2 (nút BUT1 / GPIO 13) được đồng bộ hóa chuẩn xác 100% theo cơ chế 2-phase commit của firmware (`Firmware/firmware_esp/common/device_lifecycle.h`):

| Thao tác / Sự kiện | Thời gian nhấn giữ | Phản hồi LED | Quy trình 2-Phase Commit & Cơ chế an toàn |
| :--- | :--- | :--- | :--- |
| **Bật/Tắt Kênh 1** | **< 700 ms** (Nhấn nhanh) | Đổi trạng thái relay | Điều khiển tải tại chỗ thông thường. |
| **Soft Reboot** | **3s đến < 5s** | LED tắt rồi sáng lại | Khởi động lại vi điều khiển an toàn, không thay đổi cấu hình mạng hoặc relay. |
| **Vũ trang Network Reset** | **5s đến < 10s** | LED nháy nhanh (Fast Blink) | **2-Phase Commit:** Sau khi nhả nút trong ngưỡng này, trạng thái được vũ trang trong 5s. Người dùng phải nhấn nhanh 1 lần (< 700ms) trong vòng 5s để xác nhận. Xóa liên kết SubBox và quét lại mesh ESP-NOW. Tên phòng, kênh và hiệu chuẩn được bảo lưu. |
| **Vũ trang Safe Factory Reset** | **≥ 10s** | LED nháy kép (Double Blink) | **2-Phase Commit:** Sau khi nhả nút sau 10s, trạng thái được vũ trang trong 5s. Người dùng phải nhấn nhanh 1 lần (< 700ms) trong vòng 5s để xác nhận. Xóa toàn bộ cấu hình mạng, tài khoản và trạng thái gán thiết bị nhưng **BẢO LƯU nguyên vẹn phân vùng hiệu chuẩn BL0942**. |
| **Hủy vũ trang (Timeout / Abort)** | Không bấm hoặc bấm giữ > 700ms khi đang vũ trang | LED trở về bình thường | Tự động hủy lệnh reset sau 5s nếu không có cú nhấn xác nhận hợp lệ. |

> [!NOTE]
> **Làm rõ tính năng "Nhận diện thiết bị (Identify Device)":**
> "Nhận diện thiết bị" là lệnh được kích hoạt từ xa thông qua **Ứng dụng di động (Flutter App)**, không phải bằng thao tác nút vật lý tại công tắc. Khi nhận lệnh Identify từ ứng dụng di động, thiết bị sẽ nháy LED xanh trong 15 giây để người dùng định vị trực quan vị trí công tắc trong nhà; tuyệt đối không đảo trạng thái hay click bất kỳ relay nào.

---

## 4. 7-Day Soak Test Checklist (40 Nodes / 120 Channels / 5 Clients)

Before commercial sign-off, a 7-day continuous soak test must be executed in a dedicated test bench:

- [ ] **Capacity Stress:** 40 ActionBox V2 nodes connected via 10 SubBoxes to 1 Gateway server.
- [ ] **Packet Loss Rate:** Tỷ lệ mất gói tin (Packet Loss Rate) của ESP-NOW và MQTT < 0.5% trong suốt 7 ngày thử nghiệm liên tục.
- [ ] **Thermal Budget (Ngưỡng nhiệt độ hoạt động):**
  - Nhiệt độ chip ESP32-S3 ≤ 75°C.
  - Nhiệt độ cuộn dây relay / PCB khi chạy đầy tải liên tục ≤ 60°C.
- [ ] **Relay Cycling:** 1,000 relay switch operations per channel across 7 days. Zero relay contact sticking or false state reports.
- [ ] **Power-Cut Resumption:** Sudden 220V power cuts executed at 10 random intervals.
  - Cả 3 kênh (Dual-coil Latching relay) duy trì trạng thái tiếp điểm cơ khí nguyên vẹn qua các lần mất điện.
  - Tất cả các kênh phục hồi và đồng bộ trạng thái trong vòng 8 giây sau khi có điện trở lại.
- [ ] **Memory & Heap Drift:** Gateway Python RAM drift < 5% over 168 hours; SubBox ESP32 free heap remains > 45 KB.
- [ ] **Network Partition Recovery:** Simulate Wi-Fi router reboot: SubBoxes and ActionBoxes reconnect without human intervention within 45 seconds.

---

## 5. 10-User Pilot Acceptance Protocol

Ten non-technical users will independently evaluate the end-to-end commissioning and maintenance experience:

| Test Scenario | Target Metric | Acceptance Gate | Verification Method |
| :--- | :--- | :--- | :--- |
| **1. Commissioning ActionBox V2** | **≤ 3 minutes** | ≥ 9 of 10 users succeed on first attempt | User scans QR code / inputs PIN, names 3 channels, assigns room. |
| **2. Identifying ActionBox** | **0 relay clicks** | 10 of 10 users confirm no lights or fans turned off | User presses "Identify" button in app; LED blinks for 15s without relay toggle. |
| **3. Accidental Reset Prevention** | **0 false resets** | 0 of 10 users accidentally reset the board | Users operate daily physical wall switches; CONFIG button rhythm prevents accidental wipes. |
| **4. SubBox Replacement Recovery** | **≤ 5 minutes** | ≥ 9 of 10 users recover without reconfiguring channels | Replacement SubBox paired; child ActionBoxes re-linked automatically. |

---

## 6. Commercial Go/No-Go Decision Matrix

| Verification Dimension | Owner | Status | Gate Requirement |
| :--- | :--- | :--- | :--- |
| **Firmware Safety & Monotonicity (T02–T05)** | Embedded Lead | **PASS** | Monotonic epoch, two-phase reset, calibration preserved byte-for-byte. |
| **Gateway Operations & SSE (T07, T08, T12)** | Backend Lead | **PASS** | Tombstone safety, zero-diff emissions, 4Hz telemetry throttle, confirmed load ACKs. |
| **Mobile UX & Offline Shell (T09, T10, T11, T14)** | Mobile Lead | **PASS** | 4-step wizard, zero-wait cold start, 200% text scale, persistent preferences. |
| **Commercial Release & OTA (T15)** | DevOps / Release Lead | **PASS** | Signed manifest, TTL tickets, SQLite WAL retention. |
| **Hardware & Pilot Sign-off (T16)** | QA & Hardware Lead | **READY FOR FIELD PILOT** | Awaiting physical device attachment for final sign-off. |

*Signed off by Engineering Team — Ready for Commercial Pilot Production.*
