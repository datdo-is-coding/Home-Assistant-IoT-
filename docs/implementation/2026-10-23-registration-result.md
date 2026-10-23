# Đăng ký ActionBox V2 qua SubBox — kết quả ngày 23/10/2026

## Trạng thái triển khai

Đã sửa tại `/home/tuan/Home-Assistant-IoT-`, build và nạp hai ActionBox V2
(MAC 28848533DDF8, 28848533DDE8) cùng SubBox (288485350B54).
Chỉ ghi app tại 0x20000; giữ NVS, model, bootloader và dữ liệu hiệu chuẩn.
Gateway tại Pi 192.168.11.29 đã cập nhật hai file và khởi động lại thành công.
APK release đã tạo nhưng chưa cài: ADB không có điện thoại.

Đã xác nhận đăng ký thật cho cả hai ActionBox: ledger trên Pi ghi claim succeeded,
revision khớp và thiết bị online/SYNCED. Người dùng xác nhận đăng ký hoạt động.
Lượt quan sát 90 giây ban đầu chưa có thao tác; lần kiểm tra tiếp theo đã có kết quả.
Không gửi lệnh relay hoặc tự giả lập tín hiệu nút trên bo.

## Cách thử trên hệ thống thật

1. Pi và SubBox phải cùng mạng; app báo SubBox trực tuyến.
2. Nhấn rồi thả CONFIG trên SubBox. Giữ BUT1 trên ActionBox chưa đăng ký khoảng
   6 giây rồi thả. Cửa sổ đăng ký có thời hạn 180 giây. Không giữ 10 giây.
3. Trong app, thêm ActionBox, làm mới danh sách, chọn UID `AB` + MAC của bo.
   Đặt tên/phòng/kênh rồi xác nhận. App chỉ báo thành công khi SubBox xác nhận
   đã nhận ACK ghi cấu hình của ActionBox và lưu liên kết vào bộ nhớ của nó.
4. Khởi động lại ActionBox và SubBox, kiểm tra thiết bị trở lại trực tuyến mà
   không cần đăng ký lại. Đây là bước kiểm chứng phần cứng còn chờ thực hiện.
5. Hết thời gian phát hiện: mở lại CONFIG và BUT1, làm mới danh sách. Nội dung
   biểu mẫu vẫn được giữ. Bo đã nhận đăng ký có cơ chế nút khác: giữ BUT1 5–10
   giây sẽ chuẩn bị reset mạng, cần bấm xác nhận; không được coi đó là mở setup.

## Đã thay đổi

- Heartbeat chỉ thiết lập liên lạc tạm, không kết thúc cửa sổ đăng ký.
  ActionBox chỉ chọn heartbeat của SubBox đang mở CONFIG.
- UID phát hiện dựa trên MAC, có mã phiên và thời gian còn lại. Thiết bị chưa
  đăng ký nháy theo trạng thái UNCLAIMED; khi mở cửa sổ dùng CLAIMING.
- Gói đăng ký nhị phân 146 byte, kiểm tra định danh, phiên, độ dài và khóa reset.
  Không thực hiện lệnh relay trong đăng ký. Điều khiển mạng chỉ được nhận sau
  khi đã đăng ký và từ đúng SubBox.
- ActionBox lưu liên kết trong cấu hình người dùng trước ACK. SubBox lưu peer
  trước thông báo CLAIM_APPLIED. Nạp lại danh sách khi khởi động. Peer protocol-3
  tách riêng khỏi peer mã hóa; không hạ cấp peer mã hóa sẵn có.
- Yêu cầu trùng được trả lại kết quả mà không lặp ghi cấu hình ActionBox. Gateway
  gửi lại cùng operation khi mất ACK và tiếp tục operation còn hạn sau khi Pi
  khởi động lại, khi SubBox phát heartbeat.
- Gateway kiểm tra đúng SubBox, UID, operation và revision trước khi hoàn tất;
  ACK trực tiếp của ActionBox không bỏ qua bước lưu của SubBox. Chỗ đang đăng ký
  cũng được tính vào giới hạn bốn ActionBox. Có thể đăng ký lại bản ghi cũ sau
  mở setup vật lý, không tự khôi phục quyền sở hữu chỉ vì thấy thiết bị.
- Tên tiếng Việt/biệt danh được lưu tại Gateway; gói xuống bo chỉ mang loại kênh
  và mã phòng ngắn. Tránh vượt bộ đệm khi có tên/biệt danh dài.
- App bỏ lựa chọn đã hết thời gian, giữ mã yêu cầu khi kết nối lỗi để thử lại,
  chờ theo thời hạn 120 giây của Gateway và chỉ hiển thị thành công sau xác nhận.

## Kiểm chứng

- Gateway: 268 bài chạy, 7 bỏ qua, 261 đạt.
- Firmware host: 18 bài đạt, có chạy mã thật của luồng SubBox nhận/phát claim,
  đối chiếu receipt, lỗi lưu, khôi phục sau reboot và giữ riêng peer mã hóa.
- Android: 126 bài đạt khi chạy tuần tự. Một lượt chạy song song có lỗi ở bài
  voice_alias_gateway_test; bài này đạt khi chạy riêng và khi chạy toàn bộ tuần tự.
  Không coi đây là bằng chứng bộ kiểm thử song song đã hết chập chờn.
- Pi: 9 bài đăng ký chạy tại chính môi trường dịch vụ đều đạt.
- Hai firmware build đạt; cả ba lần nạp xác minh hash đạt. APK debug và release
  build đạt. Build release có cảnh báo font CupertinoIcons sẵn có; chưa kiểm tra
  các màn hình dùng font này trên điện thoại thật.

## Giới hạn cần biết

Protocol-3 ESP-NOW đang dùng vẫn chưa có xác thực/mã hóa tương đương nhánh
hc_core. Thao tác nút và phiên setup không thay thế xác thực mật mã. Đây là
hoàn thiện chức năng trên đường truyền hiện tại, chưa phải chứng nhận đủ an toàn
để bán thương mại. Luồng hc_core bảo mật giữ nguyên.

Kiểm thử reboot của peer và khôi phục operation là kiểm thử host/API. Chưa thử
cắt nguồn đúng giữa hai bước commit trên bo thật. Nếu chỉ ActionBox đã lưu mà
SubBox bị mất nguồn trước khi lưu, có thể cần reset mạng vật lý và đăng ký lại.

Không thay pipeline voice hoặc reset toàn bộ dữ liệu hệ thống trong công việc này.

## Bảo trì và bằng chứng

- Hợp đồng radio: `Firmware/firmware_esp/common/registration_wire.h`.
- ActionBox: `src/system/registration.cpp`, `src/system/task_manager.cpp`,
  `src/network/espnow_transport.cpp`.
- SubBox: `src/audio/audio_transport/espnow_audio_transport.cpp`,
  `src/storage/security_config.cpp`, `src/system/task_manager.cpp`.
- Gateway: `gateway/main.py`, `gateway/device_lifecycle.py`.
- App: `lib/features/actionbox/add_device_flow.dart`.
- Kiểm thử mới: `Gateway/tests/test_registration_bridge.py`,
  `Firmware/tests/test_registration_transport.py`,
  `Firmware/tests/registration_transport_host.cpp`,
  `Firmware/tests/actionbox_host/registration.cpp`.
- Log, hash nguồn/binary và manifest: `docs/audit-evidence-2026-10-23-registration/`.
- Bản sao lưu riêng tư: `/home/tuan/.local/state/esp-backups/20261023-registration/`.
  Mỗi file là vùng flash 0..0x180000, chứa boot/NVS và toàn bộ app cũ đang chạy,
  không phải bản sao toàn bộ 16 MB flash.
- Pi giữ `main.py.before-registration-20261023` và
  `device_lifecycle.py.before-registration-20261023` ngay cạnh nguồn.

Bản nguồn chính có nhiều thay đổi chưa commit từ trước. Không chép đè bản worktree
cũ của cuộc chat hoặc tạo commit chứa toàn bộ các thay đổi đó.
