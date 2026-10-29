# Trạng thái hệ thống — 2026-10-29

## Nguồn và dịch vụ đang duy trì

Cập nhật 1.7.0+43 bổ sung kiểm tra catalog Firebase và tải APK GitHub Releases,
kiểm tra hash/chữ ký/package/version code, cài qua Android mà không uninstall.
Rules mới chỉ cho tài khoản đăng nhập đọc catalog, client không được ghi.
Spark được giữ nguyên; chưa coi luồng cài trên điện thoại là đã kiểm chứng.

Cập nhật giao diện 1.6.0+41 dùng Progressive Blur + Light Rays, dock nổi,
bề mặt kính nhẹ, giữ dữ liệu/quyền và các luồng điều khiển. Xem
[ảnh, kiểm tra và giới hạn](../testing/progressive-blur-2026-10-29/README.md).

Bản tích hợp IR/quản trị 1.5.0+26: SubBox 0B54 và ActionBox DDF4 chạy
2.3.0-control1; main/radio Pi đã đồng bộ. Tài khoản Google đang liên kết có
vai trò Owner của nhà. Đã kiểm tra reboot DDF4 qua Firebase, boot mới được
xác thực và enrollment giữ nguyên. DDF8 đã cập nhật OTA 2.3.0-control1 ở lượt
sau, kiểm tra hash/health, giữ cấu hình và reboot qua Firebase thành công.
Xem [kết quả DDF8](../testing/ddf8-maintenance-2026-10-29/README.md).
Xem [bằng chứng 1.5.0](../testing/ir-climate-admin-2026-10-29/README.md).

App duy nhất là `App/HomeCompetition`, đọc dữ liệu và gửi yêu cầu ghép qua
Firebase. Main Gateway là `Gateway/gateway/main.py`, đang chạy trên Pi từ
`/home/pi4/Home-Assistant-IoT-/Gateway/gateway`. Dịch vụ radio/OTA nội bộ chạy
riêng từ `/home/pi4/.local/lib/homecompetition-ota`; cầu nối Firebase chia sẻ
registry Core với nó và không mở radio bridge thứ hai.

Hai project firmware hiện hành là `ActionBox_V2` và `SubBox`; cả hai liên kết
`common/hc_core`. ActionBox V2 có 3 relay và 3 BL0942, giữ quyền GPIO và bảo vệ
tải. Theo yêu cầu rollback ngày 28/10, WakeNet ở ActionBox; SubBox chỉ đệm PCM,
chuyển WSS lên Pi và phát loa. ASR tiếng Việt Sherpa chạy trên Pi, lệnh qua Core.
Model KWS cũ được giữ làm lịch sử và không build/chạy trên SubBox.

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

SubBox tiếp tục nhận snapshot peer/phòng và xác nhận áp dụng. Pi nhận dạng câu
hoàn chỉnh, xác thực nguồn/phòng, chọn thiết bị Core, chờ ACK rồi phát lời đáp.
Nếu nhiều thiết bị cùng loại, dùng binding LIGHT/FAN đã cấu hình; phòng vẫn
thuộc SubBox. Đường này cần Pi hoạt động.

Tên và alias thiết bị Core hiện là nguồn chung cho ASR và phân giải lệnh trong
phạm vi nhà/phòng của nguồn micro. Tên/alias rõ ràng được ưu tiên; binding
LIGHT/FAN chỉ dùng cho cách gọi chung. Tên trùng hoặc không khớp không tự chọn
kênh. App hỗ trợ đủ năm loại, alias mặc định theo tên cho tới khi người dùng
sửa riêng; thay cấu hình làm tăng revision và hủy lệnh chờ của cấu hình cũ.
App 1.3.3+23 phản hồi chạm bằng trạng thái đang chờ, cập nhật theo ACK và báo
lỗi/hoàn tác nếu thất bại. Firebase đẩy thay đổi state ngay, không đợi heartbeat.
APPLIED là xác nhận từ firmware; không phải đo tải điện thật.

App 1.3.4+24 tiếp tục giữ cơ chế trên và tinh giản các tab: trạng thái kết nối
đặt ở màu tên nhà, trạng thái online thiết bị đặt ở chấm nhỏ độc lập với
công tắc. Mô tả và tùy chọn kỹ thuật được thu gọn, số đo vẫn được giữ. Xem
[kiểm tra giao diện](../testing/app-minimal-ui-2026-10-29/README.md).

App 1.4.0+25 khôi phục chiều sâu và ánh sáng trên thẻ, nền ambient tĩnh và
một vùng kính ở thanh điều hướng, giữ cấu trúc hạn chế rebuild khi cuộn.
Thêm màn Remote từ tab Thiết bị, dùng Firebase RPC hiện hữu, không gọi cổng
local từ điện thoại. Pi lưu remote theo nhà và SubBox, gửi sóng qua WSS đã
xác thực; SubBox 0B54 đã nạp USB 2.2.0-ir1 có RMT TX GPIO40. Prototype hiện
chỉ có LED phát, nên RX GPIO39 mặc định bị khóa.
Người dùng đã xác nhận Panasonic A75C4187 phản ứng đúng; remote này đã lưu.
Bộ này hiện có nút nguồn ghi sẵn, chưa có điều khiển nhiệt độ tùy ý. Các bộ
Panasonic 216-bit hợp lệ khác hỗ trợ sinh khung nhiệt độ/mode/quạt nhưng chưa
được xác nhận với điều hòa này. IR chỉ báo đã phát, không xác nhận trạng thái
điều hòa. Đó là trạng thái bản 1.4.0; xem [kiểm tra IR ban đầu](../testing/flagship-ir-2026-10-29/README.md).

Từ 1.5.0, Owner/Installer có thể khai báo đã lắp mắt thu, học riêng Bật/Tắt và
từng nhiệt độ 16–30°C; hiện chưa bật vì phần cứng chưa có mắt thu. Panasonic
216-bit hợp lệ hỗ trợ sinh trạng thái đầy đủ; giao thức khác chỉ dùng các mức
đã học. Bộ A75C4187 có mã nút 128-bit tương đối nên không được coi là khung
Bật/Tắt/nhiệt độ tuyệt đối. IR đã nối phân giải giọng nói theo tên/alias và
phòng, dùng chung deadline/ACK/chống gửi lặp. Chỉ nói đã gửi lệnh, không giả
xác nhận trạng thái điều hòa. Mã nhiệt độ và học IR thật chưa được người dùng
kiểm thử trong lượt này.

Owner có thể reboot, khôi phục gốc và gỡ bo qua Firebase → Core → firmware.
Firmware kiểm tra phiên đã enroll, revision/deadline và chuẩn bị relay an toàn
trước reset. Pi chỉ gỡ enrollment sau receipt reset/xóa thành công; reboot cần
boot mới xác thực. Không reset/xóa SubBox còn ActionBox con, không thực hiện
reset/xóa thật trong lượt này. Network reset riêng chưa hỗ trợ cho bo Core.

Pi phát “Em đã bật/tắt <tên thiết bị>” sau APPLIED. Câu đáp đọc tên Core đã lưu,
không giới hạn ở đèn/quạt. Đã nhận đúng lệnh cà phê trên DDF8 CH2 và SubBox
xác nhận phát 50240 byte câu “Em đã bật Máy pha cà phê”; người dùng xác nhận.
Xem [kiểm tra cấu hình và phản hồi](../testing/device-config-response-2026-10-29/README.md).

Kiểm tra ngày 29/10: registry chỉ có Phòng ngủ và SubBox 0B54 thuộc phòng đó.
Màn Thêm thiết bị Firebase lấy toàn bộ phòng từ snapshot, rồi chọn SubBox trong
phòng làm parent; không sinh phòng theo số bo cắm USB. Luồng Firebase hiện
chưa có thao tác tạo phòng, dù Core API độc lập đã có chức năng này. Vì vậy
thiết lập thêm phòng qua app còn thiếu; cần tạo phòng trước, đăng ký SubBox
cho phòng rồi mới ghép ActionBox vào phòng đó.

Trước bản IR, đã nạp USB 2.1.0-pi4 cho SubBox 0B54 và ActionBox DDE8, kiểm tra app và giữ
nguyên bootloader/NVS/otadata. Nói thật “bật đèn” được nhận đúng, APPLIED và
phát đủ phản hồi; lượt cuối “tắt đèn” cũng success. Người dùng xác nhận điều
khiển/loa và tiếng wake đã ổn. Wake gửi sự kiện riêng trước VAD, chime được
enqueue trên SubBox sau khoảng 8–44 ms qua log host, không chờ Pi.
Xem [rollback Pi voice](../testing/pi4-voice-rollback-2026-10-28/README.md).

Báo cáo [tích hợp KWS cũ](../testing/core-kws-three-relay-2026-10-28/README.md)
giữ nguyên kết quả lịch sử trước rollback.

## Phạm vi dọn nguồn

[Archive ngày 2026-10-28](../../archive/2026-10-28-cleanup/README.md) giữ nguyên
code cũ, pipeline huấn luyện đã dừng, build/cache và tài liệu lịch sử. Các file
đang được import/build, dữ liệu triển khai, model hiện tại, tài nguyên âm thanh,
thiết kế PCB và dependency đã khóa của hai Box được giữ. Active test vẫn kiểm
tra driver V1 qua bản nguồn gốc trong archive như một baseline tương thích.

Đợt dọn chỉ thay đổi repo trên máy phát triển. Không triển khai lại dịch vụ Pi,
không reset/nạp firmware, không đóng relay. OTA qua Internet, phân quyền tenant
sản xuất và thử tải điện thật chưa được xác nhận.
