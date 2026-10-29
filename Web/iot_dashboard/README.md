# IoT Dashboard Web — HomeAssistant Smart Home

Bản ứng dụng Web Dashboard được đồng bộ và sao chép toàn diện từ mobile app (`App/HomeCompetition`), mang trọn vẹn toàn bộ tính năng, kiến trúc Riverpod, router, widget và phong cách giao diện Progressive Blur & Flagship Backdrop lên môi trường Web.

## 🚀 Tính năng nổi bật trên Web

- **Đồng bộ 100% màn hình & tính năng từ App**:
  - `/home`: `FeatureHomeScreen` với thẻ thiết bị, chip phòng, thanh điều khiển nhanh `QuickControlSheet`, trạng thái kết nối realtime.
  - `/devices`: `FeatureDevicesScreen` & `FeatureDeviceDetailScreen` hỗ trợ cấu hình relay, tên, kênh, icon.
  - `/energy`: `EnergyScreen` hiển thị công suất tiêu thụ BL0942, biểu đồ thời gian thực, tổng hợp năng lượng kWh và tiền điện.
  - `/automation`: `AutomationScreen` quản lý kịch bản tự động hóa và cảnh (Scenes).
  - `/voice`: `VoiceScreen` quản lý từ khóa giọng nói offline KWS & alias gateway.
  - `/infrared`: `InfraredScreen` điều khiển remote hồng ngoại (IR) qua SubBox / ESP32.
  - `/settings`: `SettingsScreen` quản lý cấu hình hệ thống, đổi theme sáng/tối, thông tin thiết bị.
- **Responsive Shell thích ứng màn hình**:
  - **Màn hình lớn / Desktop**: Tự động chuyển đổi sang thanh điều hướng dọc (`NavigationRail`) kết hợp `FlagshipBackdrop`.
  - **Màn hình điện thoại / Tablet**: Thanh điều hướng nổi dạng viên thuốc (`ProgressiveBlur` capsule navigation dock).
- **Tương thích hoàn toàn CanvasKit / HTML Web**:
  - Đã xử lý các API nền tảng di động (`dart:io`) với `kIsWeb` an toàn.

## 🛠️ Hướng dẫn Chạy & Biên dịch

### 1. Cài đặt dependencies
```bash
flutter pub get
```

### 2. Kiểm tra mã nguồn & Chạy kiểm thử
```bash
flutter analyze
flutter test
```

### 3. Biên dịch bản phát hành Web
```bash
flutter build web --release
```

### 4. Chạy Web Preview cục bộ
```bash
python3 -m http.server 5000 --directory build/web
```
Truy cập tại: `http://localhost:5000`
