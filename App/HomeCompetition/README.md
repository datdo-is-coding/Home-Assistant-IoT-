# HomeCompetition

App hợp nhất từ `dtv_energy_flutter` và `dtv_home_assistant`. Thư mục chuẩn:
`App/HomeCompetition`; package Dart: `home_competition`; entrypoint: `lib/main.dart`;
app shell: `lib/app/home_competition_app.dart`. Dashboard cũ được lưu tại
`archive/2026-10-28-cleanup/files/App/iot_dashboard`. Bản nguồn `dtv_home_assistant` được giữ ở
`archive/Application/dtv_home_assistant` để đối chiếu/khôi phục.

## Chạy và build

```sh
cd App/HomeCompetition
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

APK dùng hằng ngày: `build/app/outputs/flutter-apk/app-release.apk`.
Bản release 1.6.0+41 được giữ tại `releases/android/HomeCompetition.apk`.
Bản 1.6.0 dùng Progressive Blur ở dock nổi và nền Light Rays vẽ tĩnh, áp dụng
cùng bề mặt kính xuyên sáng cho năm tab, màn đăng nhập và bảng điều khiển.
Giảm hiệu ứng/tương phản cao dùng nền đọc rõ, không thêm blur vào từng thẻ.
Xem [ảnh và kiểm tra](../../docs/testing/progressive-blur-2026-10-29/README.md).
Giao diện đã tinh giản: tên nhà xanh/cam báo kết nối, chấm online trên thẻ,
phần giải thích và kỹ thuật được thu gọn. Xem
[`app-minimal-ui-2026-10-29`](../../docs/testing/app-minimal-ui-2026-10-29/README.md).
Bản 1.4.0 bổ sung nền ánh sáng, viền nổi, phản hồi nghiêng khi chạm và kính ở
thanh điều hướng. Remote IR mở từ biểu tượng remote ở tab Thiết bị; cấu hình
và điều khiển đi qua Firebase RPC tới Pi rồi tới SubBox đã enroll qua WSS.
Chọn SubBox, bộ mã, thử và xác nhận thiết bị phản ứng trước khi lưu. Bản 1.5.0
thêm học riêng Bật/Tắt/Đặt nhiệt độ, tên gọi giọng nói và khai báo mắt thu.
Prototype hiện chỉ có LED phát: chỉ bật mục “Đã lắp mắt thu hồng ngoại” sau khi
lắp đúng phần cứng. Panasonic 216-bit hợp lệ có bảng nhiệt độ đầy đủ; giao thức
khác chỉ hiện những mức đã học. A75C4187 là bộ nút nguồn/tăng/giảm tương đối,
không được coi là mã Bật/Tắt/nhiệt độ tuyệt đối.
Sau khi có mã phù hợp, nói “bật điều hòa”, “tắt điều hòa”, “đặt điều hòa 26 độ”;
Pi chọn remote trong phòng của micro, chờ SubBox xác nhận phát rồi trả lời.
IR không đo được trạng thái điều hòa. Xem
[kiểm tra 1.5.0](../../docs/testing/ir-climate-admin-2026-10-29/README.md).
Tên gọi giọng nói mặc định theo tên thiết bị, cho phép sửa riêng. Lưu cấu hình
có tiến trình/kết quả/lỗi; bật/tắt hiển thị trạng thái đang chờ trước ACK của bo.
Chi tiết kiểm tra app và Pi tại
[`device-config-response-2026-10-29`](../../docs/testing/device-config-response-2026-10-29/README.md).
Chỉ dùng `flutter run` hoặc APK debug khi phát triển/chẩn đoán; không dùng FPS
của bản debug để đánh giá hiệu năng bản phát hành.
Android applicationId giữ `com.dtv.homeassistant.dtv_home_assistant` để khớp app
đã đăng ký Firebase; namespace mới `com.homecompetition.app`, tên hiển thị
HomeCompetition. Không đổi applicationId khi chưa đăng ký lại Firebase/Google
Sign-In. Cấu hình iOS của app cũ được chuyển cùng; chưa build iOS trên Linux.
Linux native chưa được các plugin Firebase trong bản này hỗ trợ, dùng Android/web.

## Dữ liệu và tài khoản

- Firebase project `home-companion-fed2e`, Realtime Database vùng asia-southeast1.
- Đăng nhập/đăng ký email, Google và đặt lại mật khẩu dùng Firebase Authentication.
  Firebase tự quản lý phiên; app không lưu mật khẩu/API key Gateway.
- Thiết bị đọc bằng listener `devices`; không nhập địa chỉ Pi/cổng8000, không
  gọi HTTP/SSE local, không tự quay về Gateway khi cloud lỗi.
- Giữ màn hình nhà, phòng, thiết bị, yêu thích, kịch bản, giao diện sáng/tối.
  Điện năng & Cảnh báo mở từ biểu tượng báo cáo hoặc Cài đặt.
- Tên nhà/yêu thích/theme là tùy chọn trên điện thoại; lịch tự động cũng chỉ là
  cấu hình cục bộ theo tài khoản, chưa có dịch vụ chạy lịch trên cloud.
- Thêm thiết bị dùng lại wizard và logic ghép bo của Gateway qua Firebase.
  Gateway cần bật cầu nối và gán tài khoản được ghép theo
  `Gateway/firebase/README.md`; không nhập IP/cổng local trên app. Chỉ báo thành
  công khi bo xác nhận đăng ký. OTA và cấu hình giọng nói cần backend riêng.
- Báo cáo dùng số đo từng kênh. Không cộng điện năng tổng của bo lần nữa.
  Chưa có dữ liệu lịch sử trong schema hiện tại: không vẽ biểu đồ từ số liệu mẫu.

Schema giữ tương thích nguồn Firebase của app cũ:

```json
{
  "devices": {
    "action_box_01": {
      "name": "Action Box", "room": "Phòng khách", "online": true,
      "last_updated": 1793059200000,
      "total_power": 40.0, "total_energy_kwh": 1.25,
      "channels": {
        "ch1": {"name": "Đèn", "device_type": "light", "state": true,
          "voltage": 220.0, "current": 0.182, "power": 40.0, "energy_kwh": 1.25}
      }
    }
  }
}
```

`last_updated` nên là Unix timestamp giây/mili giây. Firmware mô phỏng hiện gửi
uptime: app chỉ coi là mới sau khi quan sát timestamp thay đổi khi đang kết nối.
Sau15giây không có mẫu mới, kênh chuyển ngoại tuyến và khóa điều khiển.
Thiếu state hoặc số đo không được giả thành trạng thái/số0 đã xác nhận.

## Điều khiển và quyền

Thiết bị Core đã enroll được điều khiển qua Firebase RPC tới Pi, kiểm tra quyền
nhà, cấu hình kênh và ACK từ bo. UI phản hồi chạm bằng trạng thái đang chờ;
không coi ghi cloud là đã đóng relay. APPLIED là trạng thái firmware báo lại,
không phải đo tải điện. Đường tương thích cũ vẫn ghi boolean qua HTTPS REST có
Firebase ID token; không dùng hàng đợi ghi offline để phát lại lệnh khi có mạng.

Firebase Rules phải kiểm tra quyền đọc/ghi phía server cho tài khoản của nhà.
Đăng ký tài khoản không tự cấp quyền thiết bị. Với Core, Owner là Quản trị nhà;
Installer có quyền cấu hình nhưng không có quyền reset/xóa bo. Vai trò được
lấy từ Pi đã xác thực, kiểm tra lại phía server trên mỗi thao tác. Xem quyền ở
Cài đặt → Tài khoản → Cập nhật quyền. Tài khoản Google đang liên kết đã được
cấp Owner theo yêu cầu ngày 29/10; không tạo mật khẩu chung hay cấp quyền IAM.
Khởi động lại, khôi phục gốc và gỡ khỏi nhà có theo dõi kết quả; reset/xóa cần
xác nhận và firmware hỗ trợ. SubBox còn ActionBox con không được reset/xóa.
Không dùng luật `.read/.write: true` trên dữ liệu nhà.

Firmware `archive/2026-10-28-cleanup/files/Firmware/firmware_actionbox_sim` có số đo mô phỏng; dữ liệu do nó gửi không phải
bằng chứng đo tải thật. Đường Core/Firebase hiện chạy với firmware ActionBox_V2,
SubBox và Pi Gateway; không lấy mô phỏng làm bằng chứng điều khiển phần cứng.

## Kiểm chứng

Các test mock SDK/REST kiểm tra mapping, freshness, mất kết nối, thu hồi quyền,
đăng xuất, đường ghi Firebase và giao diện đăng nhập. Không ghi database thật,
không đóng relay. Xem báo cáo tại `docs/implementation/2026-10-27-homecompetition-merge.md`.

Tham khảo API: [RTDB Flutter](https://firebase.google.com/docs/database/flutter/read-and-write),
[Firebase Rules](https://firebase.google.com/docs/database/security/).

Bản APK có tên riêng: `build/app/outputs/flutter-apk/HomeCompetition.apk`.
Đã kiểm tra: analyze sạch,146 test đạt và build APK debug thành công (2026-10-27).

Từ1.2.0: tab **Điện năng** nằm trực tiếp trong thanh điều hướng dưới cùng.
Có thanh tỷ trọng công suất từng kênh và tổng các chỉ số kWh đã có; vẫn giữ
trạng thái cuộn/bộ lọc của tab Nhà. Chi tiết đo hiệu năng trên máy thật:
`docs/implementation/2026-10-27-homecompetition-energy-performance.md`.
Bản1.2.0 đã build **release** và cài thử trên điện thoại;154 test đạt.
Benchmark Flutter Driver trên điện thoại đang dùng cần `--keep-app-running` để
tránh hành vi tự gỡ app và mất dữ liệu cục bộ khi kết thúc test.
