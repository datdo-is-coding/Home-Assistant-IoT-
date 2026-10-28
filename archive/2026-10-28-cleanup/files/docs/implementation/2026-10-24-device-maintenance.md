# Bản sửa bảo trì thiết bị — 24/10/2026

## Trạng thái

Đã sửa code, kiểm thử trên máy phát triển và build APK release / firmware ActionBox V2 / SubBox. **Chưa cài lên điện thoại, chưa nạp bo, chưa triển khai Pi và chưa reset thiết bị thật.** Người dùng đang vắng nhà; USB không có thiết bị và SSH tới Pi 192.168.11.29 bị timeout.

Code đang ở `/home/tuan/Home-Assistant-IoT-`, trên nền commit `b131fe43484d4700cc1efc4d9fe549ff534b72a3`. Các thay đổi lần này chưa commit/push.

## Nguyên nhân và thay đổi

1. Lệnh bảo trì từ Gateway chưa khớp giao thức firmware: thiếu thông tin định danh, phiên và mã yêu cầu; ActionBox chưa xử lý IDENTIFY / REBOOT / NETWORK_RESET / FACTORY_RESET. Đã nối đủ đường Pi → MQTT SubBox → ESP-NOW ActionBox → ACK → Pi → app. SubBox cũng xử lý lệnh nhắm chính nó. Lệnh reset phải có xác nhận và owner_epoch hợp lệ; ACK phải khớp thiết bị, SubBox, request và session.
2. Gateway trước đây tăng owner_epoch, thu hồi quyền và đánh dấu chưa đăng ký ngay khi gửi factory reset, dù thiết bị chưa thực hiện. Nay chỉ thay đổi sau ACK thành công; timeout hoặc lỗi gửi không tự xóa đăng ký. Sửa trạng thái reboot bị ghi đè thành chờ kết nối sau lỗi không tìm thấy tuyến. Xác nhận bước hai lưu lại thời hạn thao tác đúng vào ledger.
3. Firmware gửi kết quả sau thao tác lưu/xóa NVS rồi mới reboot. SubBox chờ outbox MQTT trước khi khởi động lại; ActionBox gửi ACK rồi chờ ngắn trước reboot. IDENTIFY nháy đèn 15 giây, không đổi relay. Các lỗi lưu NVS trên đường reset được trả về thay vì báo thành công giả.
4. SubBox từng có thể dùng lại Wi-Fi mặc định được biên dịch trong code sau khi xóa Wi-Fi. Load NVS giờ để trống Wi-Fi khi không có cấu hình, để đường khởi động hiện tại mở thiết lập mạng.
5. App nhận diện SubBox từ mã phần cứng SB và metadata, không sinh relay giả cho SubBox; hiển thị SubBox ở danh sách thiết bị và đổi nhãn nhóm ở trang chủ. `status=offline` không bị `is_online=true` cũ ghi đè. Hướng dẫn reset mạng của SubBox nói rõ cần ở gần bo để cấu hình lại.

Registry đã đọc ở lần kiểm tra trực tiếp trước: **2 ActionBox DDF8/DDE8 và 1 SubBox 0B54**, phù hợp khả năng SubBox bị app hiển thị nhầm thành ActionBox thứ ba. Chưa có bằng chứng kiểm tra lại nguồn/online trên phần cứng trong lượt này.

## Kết quả kiểm thử

- Gateway: toàn bộ 304 tests, 297 đạt / 7 skipped; sau đó thêm kiểm tra ACK sai kiểu dữ liệu và chạy lại nhóm maintenance: 9/9 đạt.
- Firmware host: 20/20 đạt, gồm parser maintenance, reset không reboot trước ACK, báo lỗi commit, giữ UID/calibration và không nạp lại Wi-Fi mặc định sau reset.
- Flutter: toàn bộ 128/128 đạt; sau đó thêm một widget test cho reset mạng SubBox, nhóm maintenance đạt 11/11.
- ESP-IDF 6.0.2: build ActionBox V2 và SubBox thành công.
- Flutter APK release: build thành công. Lần build đầu lỗi GeneratedPluginRegistrant/integration_test khi chạy cùng test; build tuần tự sau khi test kết thúc đã thành công, không cần sửa dependency.
- `git diff --check`: đạt.

Bằng chứng, APK, firmware, bản chụp hai file Gateway và SHA-256 nằm ở `/home/tuan/.codex/artifacts/device-maintenance-2026-10-24/`. APK: `dtv-energy-maintenance.apk`; firmware: `ActionBox_V2.bin`, `SubBox.bin`. Đây là bản ứng dụng firmware, không phải ảnh flash gộp.

## Việc còn phải làm khi có phần cứng

1. Kết nối lại USB điện thoại và các bo; kiểm tra ID cổng từng bo. Sao lưu DB và file đang chạy trên Pi trước triển khai, giữ nguyên NVS khi nạp firmware. Chỉ nạp app firmware vào offset đã xác minh của bo hiện tại (trước đây là 0x20000); không chạy erase-flash và không ghi lại phân vùng NVS/model.
2. Cài APK bằng cập nhật giữ dữ liệu; nếu chữ ký khác thì dừng, không tự gỡ app. Triển khai hai file Gateway sau khi đối chiếu phiên bản đang chạy, rồi khởi động lại service.
3. Đối chiếu DDF8: snapshot trước đó có Gateway owner_epoch=7/unclaimed sau factory reset timeout, trong khi lần claim thành công tương ứng epoch=6. Firmware mới đưa `reported_owner_epoch` và `reported_claimed` vào telemetry. **Phải đọc trạng thái bo thật và lịch sử operation trước khi sửa registry; không tự hạ epoch chỉ dựa trên phỏng đoán và không tự phục hồi quyền đã thu hồi.**
4. Thử IDENTIFY trên SubBox, DDE8 và DDF8: LED nháy, app nhận kết quả, relay không đổi. Kiểm tra danh sách 2 ActionBox + 1 SubBox, không có relay giả của hub.
5. Rút nguồn một ActionBox; sau thời hạn hiện diện của Gateway (hiện 90 giây), app phải báo offline. Cắm lại và kiểm tra online phục hồi.
6. Thử reboot; sau đó chọn bo thử phù hợp, sao lưu cấu hình và kiểm tra reset mạng/factory reset khi người dùng ở gần để ghép lại. SubBox mất Wi-Fi sẽ làm các bo phía sau tạm không điều khiển được qua app. Factory reset xóa cấu hình/ghép nối; ActionBox đưa relay OFF.

## Giới hạn còn lại

Kiểm thử host và build không chứng minh ACK đến kịp trước reboot trên sóng thật. Khi ACK bị mất sau khi thiết bị đã reset, timeout vẫn có thể xảy ra: phải đối chiếu trạng thái thiết bị, không tự gửi lại reset phá cấu hình. Việc phục hồi đăng ký DDF8 và kiểm thử mất nguồn/đăng ký lại vẫn đang chờ phần cứng. Chưa thay đổi kiến trúc thoại, mô hình wake-word hoặc topology hiện tại.
