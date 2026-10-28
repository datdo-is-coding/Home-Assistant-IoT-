# Trạng thái hệ thống — 2026-10-28

## Nguồn và dịch vụ đang duy trì

App duy nhất là `App/HomeCompetition`, đọc dữ liệu và gửi yêu cầu ghép qua
Firebase. Main Gateway là `Gateway/gateway/main.py`, đang chạy trên Pi từ
`/home/pi4/Home-Assistant-IoT-/Gateway/gateway`. Dịch vụ radio/OTA nội bộ chạy
riêng từ `/home/pi4/.local/lib/homecompetition-ota`; cầu nối Firebase chia sẻ
registry Core với nó và không mở radio bridge thứ hai.

Hai project firmware hiện hành là `ActionBox_V2` và `SubBox`; cả hai liên kết
`common/hc_core`. ActionBox V2 có 3 relay và 3 BL0942, giữ quyền GPIO và bảo vệ
tải. Model từ khóa hiện có được dùng ở SubBox; các nhãn đèn/quạt và khách/ngủ/bếp
không quy định cố định relay số mấy.

## Đã kiểm chứng trên thiết bị

- DDF4 đã được app đăng ký thật, có xác nhận độc lập từ bo và SubBox, đủ 3 kênh.
- DDF4 và SubBox 0B54 đã OTA đã ký lên 2.0.1-b1; trạng thái `SUCCEEDED` và
  heartbeat/configuration revision được kiểm tra sau reboot.
- Trong lượt ghép/OTA trước, Firebase chiếu cả hai online; calibration, định danh
  và enrollment được giữ. Đây là kết quả tại thời điểm kiểm tra, không phải
  khẳng định cả hai luôn đang online.
- Trong lượt tích hợp tiếp theo, DDE8 đã được sao lưu, nạp ActionBox_V2
  2.0.3-b1 và đăng ký thật. SubBox đã OTA lên 2.0.3-b1, counter 6. Model không
  được huấn luyện thêm.

Chi tiết tại [báo cáo commissioning](../implementation/2026-10-27-firebase-commissioning-repair.md).

Phần phát lời đáp Pi → SubBox đã được sửa và nạp OTA 2.0.2-b2 cho 0B54
(counter 5). Người dùng đã nghe rõ câu thử; lượt cuối xác nhận đủ 81600 byte
PCM và API báo phát thành công. Đã kiểm tra tự kết nối lại sau Gateway restart.
Đường loa dùng WSS, CA đã ghim và xác thực theo enrollment của bo. Chưa kiểm
thử trọn chuỗi nhận lệnh/điều khiển tải trong lượt này; xem
[bằng chứng phát giọng nói](../testing/voice-response-2026-10-28/README.md).

## Cấu hình kênh, khẩu lệnh và phản hồi hiện tại

Repo có hai lớp điều khiển đang cùng được giữ vì còn caller và test:

1. Lớp tương thích trong `registry_manager.py`, `kws_service.py` và giao thức
   JSON/SubBox có bảng `(room, LIGHT/FAN) → ActionBox/kênh`.
2. Core có `devices`, `device_bindings`, `channels`, quyền theo nhà và command
   queue. Thiết bị Core đã enroll có quyền nhận lệnh riêng, không tự chấp nhận
   lệnh tương thích cũ.

Cầu nối Firebase đã nối gán thiết bị logic, lệnh và báo cáo từng kênh vào Core.
Phòng thuộc SubBox, ActionBox chỉ gán thiết bị cho ba kênh. App đợi ACK APPLIED;
ghi boolean cloud không được coi là xác nhận điều khiển. Relay chốt dùng SET
30 ms để bật, RESET 30 ms để tắt rồi nhả chân.

SubBox nhận snapshot KWS có phiên bản và xác nhận áp dụng. KWS chọn đích trong
các ánh xạ đèn/quạt; Pi xác thực, đưa vào command queue và phát lời đáp sau ACK.
Đường Core này cần Pi hoạt động. Đã thử ba kênh từ app và sáu ý định tiêm kèm
phản hồi loa; hai lượt nói thật vẫn nhận thiếu câu và không đóng relay. Xem
[báo cáo tích hợp](../testing/core-kws-three-relay-2026-10-28/README.md).

## Phạm vi dọn nguồn

[Archive ngày 2026-10-28](../../archive/2026-10-28-cleanup/README.md) giữ nguyên
code cũ, pipeline huấn luyện đã dừng, build/cache và tài liệu lịch sử. Các file
đang được import/build, dữ liệu triển khai, model hiện tại, tài nguyên âm thanh,
thiết kế PCB và dependency đã khóa của hai Box được giữ. Active test vẫn kiểm
tra driver V1 qua bản nguồn gốc trong archive như một baseline tương thích.

Đợt dọn chỉ thay đổi repo trên máy phát triển. Không triển khai lại dịch vụ Pi,
không reset/nạp firmware, không đóng relay. OTA qua Internet, phân quyền tenant
sản xuất và thử tải điện thật chưa được xác nhận.
