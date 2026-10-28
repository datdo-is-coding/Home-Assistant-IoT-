# Bản phát hành được giữ sau dọn repo

- `android/HomeCompetition.apk`: APK debug 1.3.0+19 đã cài trên điện thoại;
  giữ application ID, chữ ký và dữ liệu đăng nhập. Đây không phải bản release
  Play Store. SHA-256 nằm trong `SHA256SUMS`.
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
