# OTA nội bộ — HomeCompetition

Phạm vi hiện tại: Pi4 điều phối OTA có chữ ký cho SubBox 0B54 và ActionBox DDF8.
Firebase vẫn ở Spark; chưa triển khai API OTA qua Internet. DDE8 dùng bảng phân
vùng Arduino cũ nên không thuộc nhóm tương thích. Kết quả thực tế và các ca chưa
đạt được ghi trong `2026-10-27-commercial-ota-progress.md` cùng thư mục.

## Thành phần đang triển khai

- Pi: `pi4@192.168.11.29`, user service `homecompetition-ota-local.service`.
- Mã/venv OTA độc lập: `/home/pi4/.local/lib/homecompetition-ota/`.
- Cấu hình, khóa xác thực từng bo và DB pilot: thư mục riêng quyền 0700
  `/home/pi4/.local/state/commercial-ota/pilot/`; cấu hình JSON quyền 0600.
- `loginctl enable-linger pi4` giữ dịch vụ hoạt động sau khi đóng SSH.
- `smarthome-gateway.service` vẫn chạy chương trình điều khiển hiện tại.
- Broker chỉ cho tài khoản Gateway và SubBox đã chọn truy cập các topic `hc/v1`
  cần thiết, sau đó deny toàn bộ `hc/v1/#`. Các rule topic cũ được giữ nguyên.

Xem trạng thái trên Pi, không làm gián đoạn cập nhật:

```bash
cd /home/pi4/.local/lib/homecompetition-ota
venv/bin/python -m gateway.fleet_ota.local \
  --config /home/pi4/.local/state/commercial-ota/pilot/pi-pilot-config.json \
  --data /home/pi4/.local/state/commercial-ota/pilot/data status
```

## Quy trình phát hành

1. Build app firmware với `HC_FACTORY_BOOTSTRAP_FILE` rỗng, phiên bản mới và cùng
   chip/layout/model. Không phát hành firmware factory chứa khóa thiết bị.
2. Trên máy bên bán, dùng `python -m gateway.fleet_ota.sign_target --help` với
   `PYTHONPATH=Gateway`. Cung cấp khóa P-256 riêng quyền 0600, file app `.bin`,
   compatibility ID đã xác minh, role 1/2, counter tăng và file `.target` đầu ra.
   Tool lấy version/hash/size từ image, xác minh lại chữ ký và từ chối ghi đè.
3. Chỉ chuyển app `.bin` và `.target` đã ký lên Pi. Khóa ký riêng ở lại máy bên
   bán; Pi và bo chỉ giữ khóa công khai để kiểm tra bản phát hành.
4. Dùng lệnh `queue` thay cho `status`, thêm factory ID, đường dẫn `.target` và
   `.bin`. Ví dụ factory ID của DDF8 là `HC-28848533DDF8`.
5. Cập nhật ActionBox trước SubBox cùng nhánh. Bộ điều phối chỉ truyền một target
   trên mỗi nhánh; mọi chunk vẫn qua xác thực HC và kiểm tra offset.
6. Chỉ tính thành công khi bo báo version/hash thực tế, boot mới và sức khỏe
   đã xác nhận. Hết truyền hoặc nhận ACK không phải là cài thành công.

Pilot là lệnh do người vận hành chủ động chạy trong LAN. Chưa nối lịch cài của
khách, grant cloud, màn hình OTA của app hoặc quyền vận hành nhiều hộ vào đây.
Không mở service/DB/config pilot ra Internet.

## Khôi phục và giới hạn

- Hai app slot có nền OTA V2 trước khi thử radio OTA; không ghi bootloader,
  partition table, model hay eFuse. Sao lưu USB nằm riêng trên máy phát triển.
- Cập nhật bị ngắt có thể bắt đầu lại với cùng gói đã ký và nhận offset mà bo
  đã ghi. Tác vụ cũ được ghi FAILED khi coordinator restart; tạo tác vụ mới để
  thử lại. `status` không khởi chạy cơ chế phục hồi hoặc đánh dấu tác vụ lỗi.
- Firmware thử rollback cố ý restart sau ba giây, không xác nhận boot và không
  truy cập GPIO. Chỉ sử dụng ở pilot chưa nối tải; không phát hành cho khách.
- Phép thử restart phần mềm không thay thế kiểm thử mất nguồn vật lý.
- CA broker cũ thiếu KeyUsage. Riêng cấu hình pilot dùng `legacy_ca=true`, giữ
  CERT_REQUIRED và kiểm tra hostname, bỏ strict X509 của Python 3.13. Thay CA và
  xóa tùy chọn này trước sản xuất. [Tài liệu Python](https://docs.python.org/3.13/library/ssl.html).
- Updater Gateway đã có kiểm thử và gói stage/import trên Pi. Cấu hình
  `updater-stage-only.json` chưa có inventory đầy đủ các file cấu hình/bí mật,
  không được dùng để activate. Chuyển dịch vụ chính sang release bất biến và
  boot recovery cần bước bootstrap bằng quản trị hệ thống; SSH hiện chưa có
  sudo không tương tác. Xem `2026-10-27-gateway-ota-updater.md`.
