# DDF8: cập nhật lệnh quản trị qua OTA

## Chẩn đoán và kế hoạch

DDF8 (`HC-28848533DDF8`, node 3399160) đang REGISTERED/ONLINE nhưng chạy
`2.0.0-b1`, chưa gửi capability quản trị. Gateway trả đúng
`maintenance_firmware_required`; app lại ghi tiêu đề lỗi kết nối cho cả lỗi
nghiệp vụ này.

1. Giữ nguyên nhánh `main` và thay đổi có sẵn trong `discovery_manager.py`.
2. Dùng image `2.3.0-control1` đã kiểm tra trên DDF4, SHA-256
   `04e662594c0d64a2d5a0095c6b57e183b80cf937d4bd76f186945b814c6e33d4`.
   Image không có factory bootstrap và nhỏ hơn cả hai app slot DDF8.
3. Bảng phân vùng từ sao lưu DDF8 có `ota_0` 0x20000/0x2f0000,
   `ota_1` 0x310000/0x300000 và `model` 0x610000/0x800000, khớp layout ứng dụng.
   Ký target riêng compatibility DDF8, counter 3, đúng khóa công khai đã cấp.
4. Sao lưu SQLite hiện tại trên Pi; giữ bản sao lưu flash riêng 16 MiB tại
   `/home/tuan/.codex/device-backups/20261029-control1/DDF8-before.bin`, hash
   `129063eb5007213ccaa5595b796426a47a667789981846e2b0e0065ea962f9b2`.
5. Chuyển image và target công khai tới Pi, cập nhật qua ESP-NOW OTA có chữ ký.
   Không ghi bootloader/bảng phân vùng/model/khóa thiết bị bằng USB.
6. Chỉ kết luận cài thành công sau boot mới, đúng version/hash, health xác thực,
   đăng ký/cấu hình còn nguyên và capability quản trị xuất hiện trên Firebase.
   Nếu health thất bại, bootloader giữ đường rollback sang app trước.
7. Sửa app phân biệt phản hồi từ chối với lỗi kết nối. Kiểm tra hồi quy gỡ
   thiết bị không được báo thành công khi chưa có ACK. Không chạy reset/gỡ thật
   chỉ để thử bản sửa.

## Kết quả thực tế

- Lượt đầu `OTA-357b35c27201698c9fc902d3` dừng ở 290496 byte do
  `transfer_timeout`; không được tính thành công.
- Mở cổng serial để chẩn đoán sau lỗi gây `USB_UART_CHIP_RESET` trên hai bo;
  cả hai kết nối lại và giữ đăng ký. Không ghi firmware bằng USB trong lượt này.
- Lượt hai `OTA-48412eaa037ae5a568e1c8e1` SUCCEEDED: đủ 1354576 byte,
  đúng SHA-256/version, health và boot mới đã được xác thực.
- DDF8 lên `2.3.0-control1`, REGISTERED/ONLINE. Đối chiếu bản sao SQLite:
  assignment, credential, nhãn kênh, tên/loại thiết bị và binding giữ nguyên.
- Firebase có đủ `reboot`, `factory_reset`, `remove_from_home` cùng boot mới.
- Thử reboot thật qua Firebase RPC `HCM-ffea275913c04df1e1f8c3e4`:
  accepted → running → succeeded; Core và Firebase cùng xác nhận boot mới
  `10047243855772218375`, đăng ký còn nguyên.
- Không chạy factory reset hoặc gỡ thật để giữ cấu hình đang sử dụng.
- App sửa tiêu đề từ chối nghiệp vụ, giữ mô tả firmware và không báo thành công
  nếu chưa có kết quả từ bo. Bản sửa nằm trong app 1.7.0 có thêm tự cập nhật.

Bằng chứng: [evidence.json](evidence.json).
