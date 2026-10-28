# Dọn toàn repository — 2026-10-28

## Kết quả

Đã duyệt 32.319 file trước dọn, gồm file tracked, ignored/local và archive cũ.
Phạm vi bao gồm app, Gateway, toàn bộ các project firmware, công cụ, dữ liệu,
deployment, protocol, tài liệu và Hardware. Git internals, các thư mục metadata
quyền hạn của công cụ và kho skill không được coi là mã sản phẩm để di chuyển.

- 28.247 file, 7.692.969.961 byte (khoảng 7,69 GB) đã vào
  `archive/2026-10-28-cleanup/files/` qua 144 mục gốc.
- 8 file được giữ và đổi vị trí: 7 fixture inference/ghép câu và đúng APK
  1.2.3+18 đang cài. Hai image OTA đã ký đang chạy được chép từ bản phát hành
  được bảo vệ vào `releases/firmware/2.0.1-b1/`, không chép khóa ký riêng.
- 152 lần chuyển đều được đối chiếu nội dung trước/sau; kiểm tra cuối xác nhận
  hash của cả 28.255 file đã chuyển và target các symlink.
- Không xóa vĩnh viễn, không commit/stage/reset, không deploy/nạp bo, không đổi
  cấu hình Pi, không gửi lệnh relay. Archive vẫn chiếm dung lượng trên đĩa.

[`manifest.json`](../../archive/2026-10-28-cleanup/manifest.json) ghi source,
destination, lý do, mode và SHA-256 từng file. Hướng dẫn phục hồi và lệnh kiểm
tra nằm trong [README archive](../../archive/2026-10-28-cleanup/README.md).

## Cơ sở phân loại

Đã đối chiếu README/config với entrypoint Flutter, Python imports, CMake targets,
test fixtures, đường dẫn APK/firmware/audio và các service thực tế trên Pi.

- Cả 51 file Dart trong app hiện hành reachable từ `lib/main.dart`; không loại
  một màn hình chỉ vì tên giống màn hình cũ.
- Các module Gateway còn caller ở main, API, service tùy chọn hoặc test được
  giữ. Core, Firebase và OTA hiện còn cần nhau; không bỏ lớp tương thích trong
  một đợt dọn file.
- SubBox build 30 source C/C++; ActionBox_V2 build 14 source C/C++, cùng component
  `common/hc_core`. Các source này và dependencies đã khóa được giữ. Header
  `SubBox/src/system/device_reset.h` trùng hoàn toàn common và không có caller
  đã được lưu trữ; build sau dọn xác nhận header chung vẫn đủ.
- ActionBox V1, master cũ, simulator, standalone audio test và shared thế hệ cũ
  không thuộc hai build hiện hành nên được lưu trữ. Test driver V1 vẫn chạy với
  baseline gốc trong archive, explicit include common hiện hành; symlink của
  bản cũ không bị sửa byte.
- Pipeline huấn luyện đã dừng và 5 test chuyên pipeline được lưu nguyên. Bốn WAV
  và ba file dữ liệu cần cho regression model hiện tại được giữ ở
  `Firmware/tests/fixtures/kws`. Không chạy training/calibration hay đổi model.
- Firmware binary/APK cũ, recorder/demo serial COM cố định, mock HIL, benchmark,
  graphify và build/cache được tách khỏi cây nguồn duy trì. PCB/CAD, thư viện và
  fabrication exports được giữ; chỉ lịch sử backup/GUI cache CAD được lưu trữ.

## Những đường dẫn đã điều chỉnh

- Ba test firmware trỏ đúng nơi giữ fixture/baseline sau di chuyển.
- Đường tải APK của WebServer ưu tiên
  `releases/android/HomeCompetition.apk`, trả đúng tên HomeCompetition; các URL
  download cũ vẫn hoạt động. Test GET/HEAD thất bại với đường dẫn cũ, rồi qua
  sau sửa, dùng thư mục tạm riêng.
- README gốc, README hai Box và `docs/architecture/current_state.md` được thay
  bằng bản đồ nguồn hiện tại; các bản cũ nằm nguyên trong archive.
- `.gitignore` archive giữ khả năng theo dõi của các file trước đó đã
  tracked/unignored. Build cache và credentials vốn ignored không được tự đưa
  vào Git. 12 phần diff nguồn có sẵn trước dọn được đối chiếu không đổi; báo cáo
  commissioning có thêm ghi chú đường dẫn mới.

## Kiểm chứng sau thay đổi nguồn

| Kiểm tra | Kết quả |
| --- | --- |
| Gateway + Firebase RTDB emulator loopback | 450 test qua |
| Flutter analyze | Không có lỗi/cảnh báo |
| Flutter tests, concurrency 1 | 164 test qua |
| Firmware host tests với Python ESP-IDF | 34 test qua |
| ESP-IDF 6.0.2 SubBox / ActionBox_V2 | Cả hai build thành công |
| Toàn bộ file chuyển và symlink | Hash/target khớp trước và sau |
| Artifact APK, image, signed target | SHA-256 khớp; target signature/version/role hợp lệ |
| `git diff --check` | Qua |

Build/cache được đưa vào archive **sau** các lượt kiểm thử/build. Lượt build kế
tiếp sẽ tạo lại cache; giữ `managed_components`, lockfile, SDK config và metadata
package của app để không mất dependency đã dùng.

Trên Pi, service main vẫn PID 3308, radio/OTA vẫn PID 871. Lần đọc cuối SubBox
có heartbeat mới; DDF4 có heartbeat cũ và máy phát triển không thấy thiết bị
serial USB. Vì vậy báo cáo này không khẳng định DDF4 hiện online hoặc thử tải
thật. Các kết quả ghép và OTA thành công trước đó vẫn được lưu trong báo cáo
commissioning, riêng biệt với lần kiểm tra hiện tại.

## Chức năng gán kênh tiếp theo

Đợt này hoàn thành phần dọn repo. Chưa thay đổi hành vi gán thiết bị hoặc điều
khiển relay. Registry Core đã có logical device → physical channel và hàng đợi
lệnh, còn bảng KWS hiện hữu thuộc lớp tương thích. Cần nối app Firebase với
binding/command/state Core trước khi tuyên bố người dùng gán và điều khiển đủ
3 kênh. Tên tự đặt trên app không mở rộng từ vựng của model giọng nói.
