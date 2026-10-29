# IR nhiệt độ, giọng nói và quản trị — 2026-10-29

App 1.5.0+26 đã cài trên điện thoại, giữ chữ ký, dữ liệu và phiên Google.
Tài khoản Google đang liên kết đã được cấp **Owner / Quản trị nhà** trong Core;
đã nhìn thấy nhãn Quản trị nhà ở Cài đặt → Tài khoản trên điện thoại thật.
Không tạo mật khẩu chung, không thay quyền Firebase IAM hay custom claims.

## Cách dùng

1. Vào Thiết bị → Remote. Chọn đúng SubBox/phòng và remote đã lưu, đặt tên và
   tên gọi giọng nói. Tên/alias được dùng chung cho ASR và phân giải điều khiển.
2. Prototype hiện chỉ có LED phát. Sau khi **lắp mắt thu đúng GPIO39**, mở mục
   Mắt thu hồng ngoại và xác nhận đã lắp. Phần mềm hiện vẫn để tắt.
3. Học riêng **Bật**, **Tắt**, hoặc **Đặt nhiệt độ**. Khi học nhiệt độ, chọn mức
   16–30°C rồi phát đúng trạng thái đó từ remote gốc. Không lấy nút nguồn đổi
   trạng thái làm cả Bật và Tắt. Chưa có remote gốc: người dùng sẽ thử sau.
4. Khung Panasonic 216-bit hợp lệ cho phép sinh trạng thái đầy đủ. Giao thức
   khác chỉ hiện các mức nhiệt độ đã học. A75C4187 hiện có là bộ nút tương đối
   128-bit: Nguồn, Tăng 1°, Giảm 1°; chưa có bằng chứng Bật/Tắt/26°C tuyệt đối.
   Không dùng bộ này để giả một nhiệt độ tuyệt đối.
5. Khi có mã phù hợp, nói “Hi ESP”, chờ ting, rồi “bật điều hòa”, “tắt điều hòa”,
   hoặc “đặt điều hòa 26 độ”. Có thể dùng tên/alias riêng. “Tăng nhiệt độ máy
   lạnh 1 độ” cần một nhiệt độ tuyệt đối đã gửi trước đó và mã mức đích phù hợp.
   IR trả lời “Em đã gửi lệnh…” sau ACK phát, không coi đó là đo trạng thái máy.
6. Để quản trị, vào Thiết bị → Bộ điều khiển → chọn bo → Bảo trì & Khôi phục.
   Có Khởi động lại, Khôi phục cài đặt gốc, Gỡ khỏi Nhà. Hai mục sau yêu cầu
   xác nhận, bo online và firmware hỗ trợ; reset đưa relay OFF, giữ hiệu chuẩn.
   SubBox còn ActionBox con không được reset/xóa. Đặt lại mạng riêng và nhận
   diện LED từ xa chưa có cho bo Core, nên các nút đó không hiện trên Core.

## Triển khai và kiểm tra thật

| Thành phần | Kết quả |
| --- | --- |
| Main + radio Pi | Mã Python triển khai khớp repo; cả hai service active |
| SubBox 0B54 | USB 2.3.0-control1, active slot 0x20000, hash nạp khớp |
| ActionBox DDF4 | USB 2.3.0-control1, active slot 0x310000, hash nạp khớp |
| DDF8 | Có sao lưu; chưa nạp, hoãn OTA theo yêu cầu |
| App Android | 1.5.0 / versionCode 26, cùng application ID và chứng thư |
| Quyền trên điện thoại | Nhãn Quản trị nhà; mở/hủy được hộp reset và gỡ DDF4 |
| Reboot qua Firebase | accepted → running → succeeded, boot mới xác thực |
| Enrollment DDF4 | REGISTERED sau reboot, không ghép lại |
| IR receiver | Vẫn tắt; không có mắt thu trên prototype |

Reboot thật dùng Firebase mailbox của tài khoản đang liên kết, không gọi tắt
API local từ app. Operation: `HCM-d7e37e2e175659eccce989a8`. Chỉ báo thành công
sau khi radio nhận boot mới được xác thực. Hai bo vẫn online, báo version
2.3.0-control1 và capability cùng boot khi kiểm tra cuối.

Cả hai bo đã sao lưu đủ 16 MiB trước nạp; esptool kiểm tra MD5 của mỗi lần đọc.
Phần bootloader/bảng phân vùng và active app còn được đối chiếu lại độc lập.
Không dùng so sánh toàn flash sau reboot để kết luận, vì NVS thay đổi khi chạy.
Chỉ ghi active app, giữ bootloader, NVS, otadata và model; model không train lại.
Relay chốt vẫn SET 30 ms / RESET 30 ms.

Sao lưu riêng trên máy: `/home/tuan/.codex/device-backups/20261029-control1`.
Sao lưu Pi: `/home/pi4/.local/state/ir-climate-admin/before-20261029-042120`;
chỉnh cuối voice có bản sao `voice-final-20261029-044245` cùng thư mục cha.
Không đưa flash backup, credential, Core DB hay ảnh điện thoại cá nhân vào repo.
Khi rollback chỉ chọn đúng active slot của đúng bo; không phục hồi DB nhà cũ
đè lên dữ liệu mới. Backend mới có cột alias IR bổ sung: giữ backend hiện tại
khi lùi riêng app/firmware, tránh dùng lại INSERT positional của backend cũ.

## Kiểm tra phần mềm

- Gateway: 500 test chạy, đạt với 3 skip có sẵn; sau sửa cuối có thêm 4 test
  voice/IR đạt, gồm không tự đoán nhiệt độ từ mã Bật chưa biết giao thức.
- Flutter: 184 test đạt; analyze sạch. Sau dọn nút bảo trì, 12 test liên quan
  đạt lại. APK arm64 release build thành công.
- Firmware: 40 host test đạt; cả SubBox và ActionBox build ESP-IDF thành công.
- Codec kiểm checksum, phân biệt A75C ngắn tương đối và Panasonic 216-bit,
  chỉ dùng nhiệt độ đã học. Voice kiểm phạm vi phòng, trùng tên, phủ định và
  chống gửi lại lệnh tương đối. Reset kiểm deadline, quyền, ACK và giữ transport
  tới lúc gửi receipt. Đây là kiểm tra phần mềm, không thay kiểm thử điều hòa.

## Phạm vi chưa kiểm chứng

Chưa học IR thật hoặc điều khiển nhiệt độ/bật/tắt tuyệt đối trên điều hòa này;
người dùng hoãn thử và prototype chưa có mắt thu. Chưa nói thật các khẩu lệnh
IR mới để xác nhận ASR/loa; test phần mềm đã đi qua phân giải đến khung phát.
Chưa factory-reset/gỡ bo thật; chỉ kiểm tra giao diện, host tests và reboot
thật để giữ hệ thống đang dùng. DDF8 chưa cập nhật. Image 2.3.0-control1 trong
releases là raw app-only USB, chưa đóng gói và ký OTA cho DDF8/khách hàng.
Không có đo tải điện thật, FPS mới, iOS build hay triển khai OTA Internet.

Hash và kết quả không chứa bí mật nằm trong [evidence.json](evidence.json).
