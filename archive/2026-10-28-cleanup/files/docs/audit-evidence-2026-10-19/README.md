# Bằng chứng rà soát bổ sung — 19/10/2026

Source revision: `8d9d5ada848d05c136054ac5070b21a8235f0573`. Không thay đổi mã sản phẩm. Các script dưới đây assert hành vi lỗi hiện tại, không phải test chứng minh đã sửa lỗi.

| Ca | Hành vi tái hiện | Bằng chứng |
|---|---|---|
| G1 | Thiết bị chưa từng discovery, `send_cfg=False`, vẫn đăng ký thành công và online | [gateway-lifecycle.log](gateway-lifecycle.log) |
| G2 | Phòng đủ 4 node: từ chối node thứ 5 nhưng đã xóa node đó khỏi pending trong RAM | Cùng log Gateway |
| G3 | Hello `FACTORY_NEW` với ID đã đăng ký được tự ghép lại theo `cfg_mismatch` | Cùng log Gateway |
| G4 | Xóa thiết bị khỏi registry vẫn giữ quyền member trong auth DB riêng | Cùng log Gateway |
| F1 | Không chọn thiết bị, bấm tiếp vẫn tới “Kết nối thành công!” với 0 POST | [flutter-lifecycle.log](flutter-lifecycle.log) |
| F2 | Snapshot không đổi, 40 board/80 kênh hiện tại: 6 stream × 2 lần phát; Device bị tạo lại | Cùng log Flutter |
| F3 | Lệnh chờ của Gateway A ghi ON lên snapshot OFF của Gateway B sau đổi phiên | Cùng log Flutter |
| F4 | Gateway mất kết nối nhưng repository vẫn trả các Device có `online=true` | Cùng log Flutter |

Kết quả: **4 tình huống Gateway và 4 test Flutter tái hiện đạt**, exit code 0. Không gửi lệnh đến thiết bị, broker hoặc Wi-Fi thật; transport/subprocess được giả lập, DB nằm trong thư mục tạm. F2 là số đếm logic cập nhật, không phải benchmark FPS/CPU/Android.

Môi trường: Python 3.12.3, Flutter 3.44.8, Dart 3.12.2. SDK: `/home/tuan/snap/flutter/common/flutter/bin/flutter`. Chạy Flutter trên bản sao `lib`, `test`, `pubspec.yaml`, `pubspec.lock`, `analysis_options.yaml` trong `/tmp/iot-lifecycle-audit-20261019/flutter`. Không chạy lại toàn bộ baseline ngày 18/10 vì source sản phẩm không đổi.

`adb devices -l` ngoài sandbox trả danh sách trống: chưa có thiết bị Android kết nối. Do đó chưa đo cold start, frame timing, RAM, pin, nhiệt hay ANR trên điện thoại. Lần gọi ADB trong sandbox không mở được listener; ngoài sandbox gọi thành công. Đây không phải lỗi ứng dụng.

## Chạy lại

1. [gateway-lifecycle-probe.py.txt](gateway-lifecycle-probe.py.txt): sửa `ROOT` nếu chuyển checkout; bảo đảm thư mục `TMP` tồn tại. Chạy `/usr/bin/python3 gateway-lifecycle-probe.py.txt`. Script tự tạo DB tạm; cần dependency Python để import các module tương ứng. Không khởi tạo đầy đủ Gateway.
2. [flutter-lifecycle-probe.dart.txt](flutter-lifecycle-probe.dart.txt): sao chép thành `test/lifecycle_performance_audit_test.dart` trong **bản sao app**; chạy `flutter pub get --offline`, rồi `flutter test --no-pub test/lifecycle_performance_audit_test.dart --reporter expanded`. Không đưa các assertion hành vi lỗi này vào regression suite tương lai mà giữ nguyên kỳ vọng; khi sửa phải đảo thành kỳ vọng đúng.

Các nhận xét về LED, nút vật lý, NVS, portal và tuyến provisioning còn lại dựa trên đọc code, chưa được thử trên bo mạch. Các log cũ ngày 18/10 được giữ nguyên ở thư mục riêng.
