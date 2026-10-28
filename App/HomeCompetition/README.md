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
flutter build apk --debug
```

APK mới build: `build/app/outputs/flutter-apk/app-debug.apk` (bản phát triển).
Bản 1.2.3+18 đang cài được giữ tại `releases/android/HomeCompetition.apk`.
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

Để tương thích firmware Firebase hiện có, điều khiển ghi boolean vào
`devices/<id>/channels/<ch>/state`. Ghi dùng HTTPS REST có Firebase ID token,
không dùng hàng đợi ghi offline của SDK để tránh phát lại lệnh khi có mạng.
Trạng thái hiển thị là **giá trị trên Firebase**, không phải ACK relay hay xác
nhận tải điện. Ghi bị từ chối được trả lỗi; không tự sửa UI thành thành công.
Timeout không tự gửi lại vì không thể khẳng định server đã nhận hay chưa.

Firebase Rules phải kiểm tra quyền đọc/ghi phía server cho tài khoản của nhà.
Đăng ký tài khoản không tự cấp quyền thiết bị. Chỉ custom claim `role=admin`
cho phép mở thao tác sửa metadata trong UI; Rules vẫn phải tự kiểm tra claim.
Không dùng luật `.read/.write: true` trên dữ liệu nhà. Thay đổi này không deploy
Rules, tạo tài khoản, hoặc ghi vào database thật. Giữ nguồn cấu hình Firebase
cũ; cần kiểm tra SHA signing key/Google provider trên project khi cài điện thoại.

Firmware `archive/2026-10-28-cleanup/files/Firmware/firmware_actionbox_sim` có số đo mô phỏng; dữ liệu do nó gửi không phải
bằng chứng đo tải thật. Firmware ActionBox_V2/SubBox và Pi Gateway hiện không
được thay bằng cầu nối Firebase trong lần gộp app này.

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
