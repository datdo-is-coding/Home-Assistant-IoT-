# ActionBox V2

Project đang dùng cho bo 3 relay chốt hai cuộn và 3 kênh đo BL0942. Mỗi cặp
relay/đo dòng giữ cùng số kênh 1–3. Tên thiết bị và phòng là cấu hình, không phải
đặc tính cố định của relay.

- Điểm vào: `src/main.cpp`.
- GPIO/loại relay: `src/config/board_pins.h`.
- Driver relay/đo: `src/drivers/relay/`, `src/drivers/current_sensor/`.
- Bảo vệ: `src/safety/`; dữ liệu calibration/định danh: `src/storage/`.
- Đăng ký an toàn và OTA: `../common/hc_core/`.
- Các lối tương thích cũ trong `src/network/` vẫn được build; Core quyết định
  quyền nhận lệnh khi thiết bị đã được enroll.

Build từ gốc repo trong ESP-IDF 6.0.2:

```sh
idf.py -C Firmware/firmware_esp/ActionBox_V2 build
```

Giữ nguyên phân vùng, model WakeNet, NVS và calibration khi cập nhật ứng dụng.
ActionBox giữ quyền thực thi GPIO và bảo vệ tải. Nhận ACK hoặc online chưa xác
nhận dòng điện/tải thật.

Bản README cũ đã chuyển vào archive. Xem
[trạng thái hiện tại](../../../docs/architecture/current_state.md) và
[manifest dọn repo](../../../archive/2026-10-28-cleanup/README.md).
