# HomeCompetition

Ứng dụng Firebase, Gateway Pi4 và các Box ESP32-S3. Bản đồ nguồn đã rà soát ngày
2026-10-28:

| Thành phần | Nguồn duy trì | Điểm vào |
| --- | --- | --- |
| App duy nhất | `App/HomeCompetition/` | `lib/main.dart` → `FirebaseHomeClient` |
| Web Dashboard | `Web/iot_dashboard/` | `app.py` / `lib/main.dart` |
| Gateway chính | `Gateway/gateway/` | `main.py`, cầu nối `firebase_commissioning.py` |
| Đăng ký/quyền/kênh/lệnh Core | `Gateway/gateway/core_v1/` | Registry SQLite, provisioning, command queue |
| OTA đã ký | `Gateway/gateway/fleet_ota/` | `python -m gateway.fleet_ota.local` cho pilot Pi |
| ActionBox 3 relay / 3 BL0942 | `Firmware/firmware_esp/ActionBox_V2/` | `src/main.cpp` |
| SubBox điều phối / âm thanh | `Firmware/firmware_esp/SubBox/` | `src/main.cpp` |
| Giao thức/OTA/bảo mật chung | `Firmware/firmware_esp/common/hc_core/` | Component ESP-IDF của cả hai Box |
| Giọng nói đang dùng | `Gateway/gateway/asr_engine.py`, `core_v1/speaker_voice.py` | Pi4 nhận PCM, ASR, lệnh Core và phản hồi; WakeNet ở ActionBox |
| Model/MFCC KWS đã dừng | `Firmware/firmware_esp/common/kws/` | Giữ lịch sử; không build/chạy LocalKws trên SubBox |

Thông tin đang chạy và các phần chưa nối xong nằm trong
[trạng thái hệ thống](docs/architecture/current_state.md). Bản phát hành đã giữ ở
[`releases/`](releases/README.md). Bản sao cũ, công cụ demo, dữ liệu huấn luyện đã
dừng và build/cache dư nằm trong
[`archive/2026-10-28-cleanup/`](archive/2026-10-28-cleanup/README.md), kèm manifest
hash và vị trí gốc. Archive giữ dữ liệu để phục hồi, không giảm dung lượng đĩa.

## App

```sh
cd App/HomeCompetition
flutter pub get
flutter analyze
flutter test --concurrency=1
flutter build apk --release
```

Giữ Android application ID đã đăng ký Firebase. Sau khi đổi nhánh hoặc khôi phục
cache, chạy `flutter pub get` để tạo lại phần đăng ký native plugin. Xem
[hướng dẫn app](App/HomeCompetition/README.md).

## Web Dashboard

Ứng dụng web dashboard và server Flask phục vụ giao diện:

```sh
cd Web/iot_dashboard
python3 app.py
# Hoặc chạy trực tiếp Flutter Web:
# flutter run -d chrome
```

## Firmware

Trong môi trường ESP-IDF 6.0.2 đã kích hoạt, từ gốc repo:

```sh
idf.py -C Firmware/firmware_esp/ActionBox_V2 build
idf.py -C Firmware/firmware_esp/SubBox build
```

`managed_components/`, `dependencies.lock`, `sdkconfig` và `sdkconfig.defaults`
của hai project được giữ. `build/` sẽ tạo lại khi build. Không dùng firmware
ActionBox đời cũ hoặc simulator để nạp thay cho `ActionBox_V2`.

## Gateway và kiểm thử

Dịch vụ Pi dùng `Gateway/systemd/smarthome-gateway.service`; cấu hình ghép qua
Firebase xem [`Gateway/firebase/README.md`](Gateway/firebase/README.md).
`deployment/`, `MQTT_Server/`, `protocol/`, `Hardware/` và `sound/` vẫn chứa cấu
hình triển khai, hợp đồng, thiết kế điện và tài nguyên được sử dụng.

```sh
PYTHONPATH=Gateway python -m unittest discover -s Gateway/tests -v
python -m unittest discover -s Firmware/tests -v
```

Gateway cần các dependency đã cài; test Firebase Rules cần emulator loopback
riêng theo hướng dẫn trong test. Firmware host tests cần `g++`, `numpy` và Python
của ESP-IDF cho các bài NVS. Mẫu KWS dùng kiểm thử nằm ở
`Firmware/tests/fixtures/kws/`; không cần chạy lại huấn luyện.

`archive/` được loại khỏi tìm kiếm mặc định. Dùng `rg --no-ignore` khi tra cứu
lịch sử. Nguồn Gateway có các module tương thích được main, API hoặc test gọi;
không tách chúng khỏi dịch vụ chỉ vì app hiện dùng Firebase.
