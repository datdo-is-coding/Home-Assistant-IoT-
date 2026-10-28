# KWS, ba relay và lời đáp — 2026-10-28

Đã triển khai Gateway, app HomeCompetition 1.3.0+19 và firmware 2.0.3-b1 cho
SubBox 0B54 / ActionBox DDE8. Phòng được gán tại SubBox; ActionBox kế thừa
phòng và gán tên/loại thiết bị riêng cho CH1–CH3. App hỗ trợ nhiều loại tải;
khẩu lệnh chỉ dùng LIGHT/FAN và ba phòng hiện có, không huấn luyện thêm.

## Bằng chứng trên thiết bị

- Sáu thao tác ON/OFF, đủ ba kênh, được bấm bằng app trên điện thoại qua
  Firebase. Cả sáu lệnh có ACK APPLIED và báo cáo relay tương ứng.
  Xem `app-relay-hil.json` và `device-status.json`.
- Sáu ý định được tiêm tại Gateway, bỏ qua nhận tiếng nói và bước tiếp nhận
  frame radio, đã điều khiển đủ ba relay thật. Mỗi lượt có ACK APPLIED,
  báo cáo relay mới và biên nhận SubBox phát đủ lời đáp. Thời gian toàn lượt
  2,578–7,113 giây. Xem `injected-intent-hil.json`.
- Để thử CH3, ánh xạ LIGHT được tạm chuyển từ CH1 sang CH3, chờ SubBox xác
  nhận rồi mới thử. Sau đó đã khôi phục LIGHT→CH1, FAN→CH2, phòng ngủ;
  cấu hình cuối revision 4 đã được SubBox xác nhận.
- Hai lượt nói thật đánh thức được DDE8 nhưng trả về `no_command` và
  `incomplete_command`; không sinh lệnh đóng relay. Người dùng nghe được
  “Chưa xác nhận được lệnh điều khiển”. Loa xác nhận đủ 94.080 byte mỗi lượt.
  Lượt đầu có log hủy phiên âm thanh; không coi các lượt tiêm ý định là bằng
  chứng model nhận giọng nói thành công.
- Trạng thái cuối: cả hai bo ONLINE, ba relay OFF, ct_valid=1, fault_flags=0.
  Không nối tải; relay_reported không phải xác nhận tải điện hoạt động.

## Nguồn, build và sao lưu

- Gateway: 471 test qua; Flutter: 167 test qua; firmware host: 36 test qua.
  Các lượt này đã chạy trước yêu cầu push, không chạy thêm để push.
- Hai project ESP-IDF 6.0.2 build thành công. Driver được kiểm tra timer
  30.000 µs cho cả SET/RESET, nhả chân và chống xung lặp; chưa đo xung bằng
  máy hiện sóng trên bo.
- SubBox OTA `OTA-069525b002f171f12c343615` SUCCEEDED, counter 6.
  DDE8 chuyển từ layout Arduino bằng USB, giữ nguyên UID/calibration và
  đăng ký Core bằng xác nhận thật từ bo và SubBox; chưa thử OTA riêng DDE8.
- Bản sao lưu DDE8 đầy đủ 16 MiB đã đối chiếu ROM digest trước nạp:
  SHA-256 `2332ac2669855e4e68d7b3047087f556c6815c8fb502bb38cf864f9d2e0a976f`.
  Khóa, enrollment và ảnh sao lưu giữ ngoài Git trong kho riêng.

Đường lệnh Core này cần Pi hoạt động. Pi xác thực/đưa lệnh vào hàng đợi và
phát lời đáp sau ACK; KWS vẫn chạy tại SubBox. Nhận đủ câu nói thật còn chưa
đạt, không mở rộng từ vựng hay hạ điều kiện thực thi để che lỗi nhận dạng.
