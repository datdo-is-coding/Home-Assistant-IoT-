# SIC — Home Assistant IoT

Code đang phát triển tập trung vào ba thành phần:

| Thư mục | Vai trò |
| --- | --- |
| `Gateway/` | Gateway Python, MQTT, xử lý giọng nói và Web UI |
| `Firmware/firmware_esp/ActionBox/` | Firmware thiết bị chấp hành ESP32-S3 |
| `Firmware/firmware_esp/SubBox/` | Firmware điều phối phòng, audio và NLU |

Các thư mục hỗ trợ được giữ lại:

- `MQTT_Server/`: broker Mosquitto và bộ dịch vụ Docker hiện có.
- `Firmware/firmware_esp/Audio_Hardware_Test/`: firmware kiểm tra phần cứng âm thanh.
- `Firmware/tools/` và các script test/visualizer: công cụ kiểm tra thiết bị.
- `Gateway/tests/`, `Gateway/benchmark/`, `Gateway/training_data/`: kiểm thử, đo hiệu năng và dữ liệu NLU.
- `Hardware/`, `sound/`, `apk/`, các firmware binary và tài liệu thiết kế: giữ nguyên.
- `archive/`: code cũ, có [bảng đường dẫn khôi phục](archive/README.md).

## Build firmware

Trên Windows có ESP-IDF 6.0.2, chạy từ thư mục gốc repo:

```powershell
.\Firmware\firmware_esp\ActionBox\build.ps1
.\Firmware\firmware_esp\SubBox\build.ps1
```

Script dùng profile `C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1`.
Tham số `-Clean` thực hiện `fullclean` trước khi build. Các script build/flash
truyền đường dẫn project bằng `-C`, nên không phụ thuộc thư mục terminal hiện tại.
Nếu chạy trong terminal thiếu biến kiến trúc CPU và gặp lỗi `Windows-`, đặt biến
cho phiên terminal trước khi build:

```powershell
$env:PROCESSOR_ARCHITECTURE = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().Replace('X64', 'AMD64')
```

Nạp firmware khi đã chọn đúng board và cổng COM:

```powershell
.\Firmware\firmware_esp\ActionBox\flash.ps1 -Port COM9 -NoMonitor
.\Firmware\firmware_esp\SubBox\flash.ps1 -Port COM10 -NoMonitor
```

## Gateway

```powershell
python -m pip install -r Gateway/requirements.txt
python Gateway/gateway/main.py
```

Cấu hình nằm trong `Gateway/gateway/config.py`; dịch vụ Linux nằm trong
`Gateway/systemd/`. ASR/TTS local cần model và dependency riêng theo cấu hình.

Kiểm thử offline từ thư mục gốc, không điều khiển thiết bị thật:

```powershell
python Gateway/tests/test_intent_engine_v3.py
python Gateway/tests/test_runtime_utils.py
```

`test_clean_gateway.py` là script tích hợp có khởi tạo Gateway/registry, không nằm
trong bộ test offline trên. Chỉ chạy với cấu hình và dữ liệu thử nghiệm riêng.

## Tìm kiếm code

`.ignore` loại code archive và thư viện bên thứ ba khỏi tìm kiếm `rg` mặc định;
dùng `rg --no-ignore` khi cần tra cứu chúng. `.graphifyignore` giữ graph tập trung
vào code hiện hành. Các file archive vẫn có thể được quản lý bằng Git.
