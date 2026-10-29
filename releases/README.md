# Bản phát hành được giữ sau dọn repo

- `android/HomeCompetition.apk`: APK release 1.7.0+43 với tự cập nhật từ
  catalog Firebase và APK trên GitHub Releases; giữ Progressive Blur,
  nền Light Rays và dock nổi; giữ học IR, nhiệt độ/giọng nói và Quản trị nhà.
  Xem [kiểm tra giao diện](../docs/testing/progressive-blur-2026-10-29/README.md);
  giữ application ID, chữ ký và dữ liệu đăng nhập. Đây không phải bản release
  Play Store. SHA-256 nằm trong `SHA256SUMS`.
  Catalog công khai nằm trong `android/release.json`. App cũ cần cài bản này
  một lần; các bản tiếp theo được kiểm tra khi mở/trở lại app và tự tải trên
  mạng không tính phí. Android yêu cầu xác nhận cài, chỉ nhận đúng chữ ký cũ.
  [Tải APK công khai](https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/app-v1.7.0/HomeCompetition.apk),
  [kết quả phát hành](../docs/testing/app-self-update-2026-10-29/README.md).
- `firmware/2.3.0-control1/SubBox.bin` và `ActionBox_V2.bin`: đúng hai image
  app-only đã nạp USB cho SubBox 0B54 (0x20000) và ActionBox DDF4 (0x310000),
  hash nạp đã kiểm tra; giữ NVS/bootloader/otadata/model. Thêm IR RX có khai báo
  phần cứng và lệnh quản trị Core có deadline/ACK. DDF4 đã reboot qua Firebase
  và giữ đăng ký. DDF8 đã cập nhật qua OTA với `HC-28848533DDF8.target` và
  manifest cùng thư mục, counter 3; xác nhận hash/health/boot mới và reboot qua
  Firebase thành công. Target này dành riêng compatibility DDF8, không dùng
  cho DDF4 hoặc SubBox. Xem [kết quả DDF8](../docs/testing/ddf8-maintenance-2026-10-29/README.md).
  Học IR/nhiệt độ điều hòa thật chờ lắp mắt thu và người dùng kiểm thử sau.
  Xem [bằng chứng và cách dùng](../docs/testing/ir-climate-admin-2026-10-29/README.md).
- `firmware/2.2.0-ir1/HC-288485350B54.bin`: app SubBox đã nạp USB vào ota_0
  (0x20000), giữ NVS/bootloader/otadata. IR TX GPIO40, RX bị khóa vì prototype
  chỉ có LED phát; giữ nhận giọng nói trên Pi. Đây là image app-only cho lượt
  USB này, chưa phải gói OTA có target/manifest ký để phát hành cho khách.
  Panasonic A75C4187 đã được người dùng xác nhận phản ứng và lưu trên app;
  xem [kiểm tra](../docs/testing/flagship-ir-2026-10-29/README.md).
- `firmware/2.0.1-b1/`: đúng hai image đã OTA thành công cho DDF4 và SubBox 0B54,
  cùng target đã ký và manifest công khai. Chữ ký, loại bo, version và digest đã
  được kiểm tra. Không có khóa ký riêng hay dữ liệu nhà máy trong các image này.
- `firmware/2.0.2-b2/`: bản đã OTA và kiểm tra phát lời đáp cho SubBox
  0B54, counter 5. ActionBox vẫn dùng 2.0.1-b1. Bản trung gian 2.0.2-b1 giữ làm
  bằng chứng chẩn đoán; dùng b2 để có xác nhận kết thúc phát đúng.
- `firmware/2.0.3-b1/`: SubBox 0B54 đã OTA thành công, counter 6; DDE8 được
  chuyển sang ActionBox_V2 bằng USB sau sao lưu đầy đủ. Gói ký cho DDE8 được
  giữ để phát hành, chưa phải bằng chứng DDE8 đã OTA. Bản này nối cấu hình
  Firebase, KWS và ba relay chốt SET/RESET 30 ms. KWS nói thật chưa đạt;
  xem [báo cáo tích hợp](../docs/testing/core-kws-three-relay-2026-10-28/README.md).

APK/image là artifact local, được Git bỏ qua. Các artifact build trung gian và
bản cũ nằm trong `archive/2026-10-28-cleanup/files/` theo vị trí gốc. Chạy build
lại sẽ tạo `build/` mới. Không dùng `idf.py flash` cả phân vùng để thay thế một
lượt OTA app-only trên bo đã ghép.

Kiểm tra các artifact hiện có từ thư mục này:

```sh
sha256sum -c SHA256SUMS
```
