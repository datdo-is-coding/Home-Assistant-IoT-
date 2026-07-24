# ⚡ DTV TEAM - ENERGY MONITORING & AI ECOSYSTEM
## Báo Cáo Tổng Quan Kiến Trúc Hệ Thống & Trạng Thái Dự Án (System Overview & Project Status)

---

### 📌 1. Tổng Quan Kiến Trúc Hệ Thống (Architecture Overview)

Hệ thống **DTV Energy Hub** là giải pháp giám sát điện năng tiêu thụ và tư vấn tiết kiệm năng lượng bằng AI đa nền tảng, bao gồm 4 thành phần chính:

```mermaid
graph TD
    PZEM["⚡ Cảm Biến PZEM-004T v3.0"] -->|UART Serial| ESP32["📟 ESP32 WROOM-32 Firmware"]
    ESP32 -->|HTTP REST /data| RUST["🦀 Rust Backend Server (Axum + Tokio)"]
    ESP32 -->|HTTP REST /data| ANDROID["📱 Android App (Jetpack Compose)"]
    
    RUST -->|HTTP Server :8080| WEB["🌐 White Liquid Glass Web UI"]
    RUST -->|Proxy AI| GEMINI["🤖 Google Gemini 2.0 Flash AI"]
    
    ANDROID -->|System Notifications| WATCH["⌚ HarmonyOS Smartwatch (Huawei Health)"]
    ANDROID -->|TTS & STT| VOICE["🎙️ Giọng Nói Tiếng Việt (STT / TTS)"]
```

---

### 🧩 2. Danh Sách & Chức Năng 4 Thành Phần Hệ Thống

#### 1. 📟 Firmware ESP32 Hardware (`004_pzem004t_tft_2_2_inch_esp32.ino`)
- **Cảm biến & Màn hình**: Đọc cảm biến PZEM-004T ($V$, $A$, $W$, $kWh$, $Hz$, $PF$) và hiển thị lên màn hình TFT 2.2" ILI9341 với nhận diện thương hiệu **DTV Team** & đồng hồ thời gian thực (NTP / millis fallback).
- **Khắc phục lỗi ổn định**:
  - Đã sửa triệt để lỗi crash/reboot liên tục (`printf` format specifier `%02lu` & lifetime chuỗi `.c_str()`).
  - Tắt Wi-Fi modem sleep (`WiFi.setSleep(false)`) giúp duy trì kết nối WPA2 ổn định 24/7.
- **Lệnh Serial**: Hỗ trợ lệnh `scan` (tìm Wi-Fi) và `wifi <SSID> <PASS>`.

#### 2. 🦀 Backend Server Rust Async (`dtv_energy_rust`)
- **Công nghệ**: Xây dựng bằng **Rust 1.96** với `tokio`, `axum`, `reqwest` (`rustls-tls` biên dịch thuần Rust).
- **Tính năng**:
  - Engine tính **Tiền điện 6 Bậc EVN + VAT 8%** chính xác vi giây.
  - Proxy kết nối **Google Gemini 2.0 Flash AI** (`gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-flash-latest`) tự động fallback.
  - Phục vụ Web Frontend chuẩn phong cách **White Liquid Glassmorphism (Kính Trắng Trong Suốt)** tại `http://localhost:8080`.
  - **Đồng bộ chuẩn 100%**: Trả về `is_online: false` khi mất kết nối ESP32, không tự bịa số liệu.

#### 3. 📱 Ứng Dụng Mobile Android (`DTV_Energy_Hub`)
- **Công nghệ**: Jetpack Compose + Kotlin + Material 3.
- **Giao diện**: **White Liquid Glass** chuẩn trend, độ tương phản chữ cực cao (Deep Slate `#0F172A` trên nền trắng `#FFFFFF`).
- **4 Tab chức năng**:
  1. 🏠 **Trang Chủ**: Đồng hồ chỉ số trực quan, đồ thị sóng Oscilloscope Canvas.
  2. 📊 **Tiền Điện EVN**: Bảng phân bổ 6 bậc EVN & Ngân sách.
  3. 🔍 **Dấu Chân Thiết Bị**: AI đoán các thiết bị đang bật trong nhà.
  4. ⚙️ **Cấu Hình**: Nhập IP ESP32/Rust Server, Gemini API Key và Nút Đẩy Thông Báo Smartwatch.
- **Cửa sổ AI Chat nổi độc lập (Floating Glass Widget)**: Cuộn tin nhắn trong khung chat **cách ly 100%** không làm trôi trang chính.
- **Giao tiếp Giọng nói (Voice STT & TTS)**:
  - Micro `🎙️` nhận diện giọng nói Tiếng Việt với cơ chế Fallback 2 lớp (`SpeechRecognizer` trực tiếp & Intent).
  - Tự động đọc câu trả lời của AI bằng giọng nói Tiếng Việt `🔊` qua động cơ `TextToSpeech`.
- **Tích hợp Đồng hồ thông minh Smartwatch HarmonyOS**:
  - Phát Kênh Notification Ưu Tiên Cao (`dtv_energy_channel`).
  - Đẩy thông báo chỉ số $W$, $V$, $A$, $VNĐ$ và cảnh báo tải cao kèm rung cổ tay sang đồng hồ Huawei/HarmonyOS qua Huawei Health.

#### 4. ⌚ Ứng Dụng Đồng Hồ HarmonyOS (`dtv_energy_harmony_watch`)
- Mã nguồn nguyên mẫu HAP cho đồng hồ thông minh Huawei Watch GT / Watch 3 / Watch 4 / Fit series bằng **ArkTS / JS Lite**.
- Màn hình OLED đen tương phản cao, tự động rung cổ tay (`vibrator.vibrate()`) khi công suất $> 1500W$.

---

### 📁 3. Đường Dẫn Mã Nguồn Chi Tiết (File Index)

| Thành Phần | Đường Dẫn Mã Nguồn | Mô Tả |
| :--- | :--- | :--- |
| **ESP32 Firmware** | `[004_pzem004t_tft_2_2_inch_esp32.ino](file:///home/tuan/Documents/PlatformIO/Projects/260724-000053-upesy_wroom/src/004_pzem004t_tft_2_2_inch_esp32.ino)` | PlatformIO C++ ESP32 Firmware |
| **Rust Server Engine** | `[main.rs](file:///home/tuan/SIC_Project/dtv_energy_rust/src/main.rs)` | Async Tokio + Axum Rust Server |
| **Web UI Frontend** | `[index.html](file:///home/tuan/SIC_Project/dtv_energy_rust/src/index.html)` | White Liquid Glass HTML5/CSS3/JS |
| **Rust Cargo Config** | `[Cargo.toml](file:///home/tuan/SIC_Project/dtv_energy_rust/Cargo.toml)` | Rust manifest dependencies |
| **Android Main Activity** | `[MainActivity.kt](file:///home/tuan/SIC_Project/DTV_Energy_Hub/app/src/main/java/com/example/dtvenergyhub/MainActivity.kt)` | Kotlin NotificationChannel & Permissions |
| **Android UI Screen** | `[HomeScreen.kt](file:///home/tuan/SIC_Project/DTV_Energy_Hub/app/src/main/java/com/example/dtvenergyhub/ui/HomeScreen.kt)` | Jetpack Compose White Liquid Glass UI |
| **Android ViewModel** | `[EnergyViewModel.kt](file:///home/tuan/SIC_Project/DTV_Energy_Hub/app/src/main/java/com/example/dtvenergyhub/ui/EnergyViewModel.kt)` | EVN Calculation, TTS, Polling logic |
| **Android Repository** | `[EnergyRepository.kt](file:///home/tuan/SIC_Project/DTV_Energy_Hub/app/src/main/java/com/example/dtvenergyhub/data/EnergyRepository.kt)` | Dual REST client (ESP32 / Rust Server) |
| **Android APK** | `[app-debug.apk](file:///home/tuan/SIC_Project/DTV_Energy_Hub/app/build/outputs/apk/debug/app-debug.apk)` | Compiled Debug APK (~12MB) |
| **HarmonyOS Watch Config**| `[config.json](file:///home/tuan/SIC_Project/dtv_energy_harmony_watch/entry/src/main/config.json)` | Wearable HAP config manifest |
| **HarmonyOS Watch UI** | `[index.hml](file:///home/tuan/SIC_Project/dtv_energy_harmony_watch/entry/src/main/js/default/pages/index/index.hml)` | Circular Watch UI markup |

---

### 🚀 4. Trạng Thái Vận Hành Hiện Tại (Current Runtime Status)

- **Backend Rust Server**: Đang chạy background task tại **`http://localhost:8080`**.
- **Android App Binary**: Đã biên dịch APK mới nhất sẵn sàng cài đặt.
- **Gemini API Key**: `AIzaSyAC9PKO176Zs6ax3uhq9avfpgOUS215kko`.
- **Biểu giá điện EVN**: Áp dụng 6 bậc thang quy định hiện hành + Thuế 8% VAT.
