# Bằng chứng audit thương mại — 18/10/2026

Revision được kiểm tra: `8d9d5ada848d05c136054ac5070b21a8235f0573`.

Bộ này đi kèm [báo cáo chi tiết](/home/tuan/.codex/worktrees/d283/Home-Assistant-IoT-/docs/commercial-code-audit-2026-10-18.md). Chỉ bổ sung tài liệu, log và mã tái hiện dưới dạng `.txt`; không sửa ứng dụng, firmware hay cấu hình triển khai. Script tái hiện dùng dữ liệu giả, không phát lệnh tới thiết bị thật.

## Kết quả và log

| Bằng chứng | Kết quả |
|---|---|
| [gateway-tests.log](gateway-tests.log) | 48 test offline đạt; không chạy `test_clean_gateway.py`. |
| [intent-tests.log](intent-tests.log) | 84/84 assertion NLU đạt; thời gian in trong log là trên máy audit, không phải Raspberry Pi. |
| [flutter-tests.log](flutter-tests.log) | 18 test hiện có đạt, trước khi thêm các ca tái hiện vào bản sao tạm. |
| [flutter-analyze.log](flutter-analyze.log) | 76 info, 0 warning, 0 error; exit code 1. |
| [flutter-pub.log](flutter-pub.log) | Resolve dependency offline thành công. |
| [firmware-tests-with-pinned-cache.log](firmware-tests-with-pinned-cache.log) | 6 host test đạt sau khi cấp cJSON đúng phiên bản. |
| [reproduce.log](reproduce.log) | Kết quả tái hiện Gateway bằng transport và subprocess giả. |
| [flutter-reproduce.log](flutter-reproduce.log) | 3 test bổ sung xác nhận hành vi lỗi hiện tại. |
| [sqlite-lock-probe.log](sqlite-lock-probe.log) | Đo bổ sung ảnh hưởng của write lock tới event loop; thời gian thay đổi giữa các lần chạy. |

**Lưu ý cách đọc:** “test tái hiện đạt” có nghĩa lỗi đã được tái hiện bằng assertion, không có nghĩa lỗi đã được sửa. R9 là quan sát vòng đời permanent API key, không được tính là một phát hiện lỗi độc lập. R4 xác nhận verifier trả `ack_only` trước khi có báo cáo tải, là một phần của phát hiện 7.

## Môi trường và phạm vi thực thi

- Python `/usr/bin/python3` 3.12.3; g++ 13.3.0.
- Flutter `/home/tuan/snap/flutter/common/flutter/bin/flutter` 3.44.8; Dart 3.12.2.
- Python có NumPy. Các gói runtime tùy chọn như `aiomqtt`, `httpx`, `edge_tts`, `websockets` không có trong interpreter này; các test offline sử dụng fallback/mock. Kết quả không xác nhận khởi động production đầy đủ.
- Các file dữ liệu phục vụ audit nằm trong `/tmp/iot-commercial-audit-20261018`; app và firmware được sao chép để chạy test mà không tạo build/dependency trong nguồn chính.
- Gateway asyncio ban đầu treo khi teardown trong sandbox. Chạy lại cùng bộ test offline ngoài sandbox hoàn thành. Không dùng kết quả lần bị treo để kết luận test đạt.
- Firmware host ban đầu thiếu managed component cJSON. Bản sao dùng `espressif/cjson` `1.7.19~2`, component hash `e788323270d90738662d66fffa910bfe1fba019bba087f01557e70c40485b469`, khớp `ActionBox_V2/dependencies.lock`.
- Chưa chạy broker, ASR/TTS model, flash, Wi-Fi commissioning, OTA thật, RF, tải điện, full ESP-IDF build hay thử tải Raspberry Pi.

## Cách chạy lại

Các lệnh dưới đây mô tả cách dựng lại phạm vi kiểm tra đã chạy. Dùng checkout đúng revision và interpreter có dependency tương ứng. Các đường dẫn cache chỉ tồn tại trên máy audit; trên máy khác cần chuẩn bị SDK/component đúng phiên bản.

### Gateway baseline và NLU

Chạy trong một terminal riêng để biến môi trường chỉ áp dụng cho phiên kiểm tra:

```bash
AUDIT_ROOT=/home/tuan/.codex/worktrees/d283/Home-Assistant-IoT-
AUDIT_TMP=$(mktemp -d /tmp/iot-audit-rerun.XXXXXX)
mkdir -p "$AUDIT_TMP/firmware"
export FIRMWARE_DIR="$AUDIT_TMP/firmware"
export AUTH_DB="$AUDIT_TMP/auth.db"
export GATEWAY_DB="$AUDIT_TMP/gateway.db"
export REGISTRY_FILE="$AUDIT_TMP/device_registry.json"
export BOOTSTRAP_PASSWORD=audit-only-bootstrap-password
export AI_ENABLED=false
export PYTHONPATH="$AUDIT_ROOT/Gateway/tests:$AUDIT_ROOT/Gateway/gateway"
/usr/bin/python3 -m unittest -v \
  test_audio_relay test_autohotspot test_hardening_contracts \
  test_runtime_utils test_system_regressions test_vocabulary_alias test_web_relay
/usr/bin/python3 "$AUDIT_ROOT/Gateway/tests/test_intent_engine_v3.py"
```

`test_clean_gateway.py` dựng `SmartHomeGateway()` đầy đủ và không nằm trong kết quả 48 test. NLU là script assertion riêng, không cộng số 84 vào số unittest 48.

### Ca tái hiện Gateway

Mã: [gateway-reproduce.py.txt](gateway-reproduce.py.txt). Script giữ đường dẫn máy audit để tương ứng log; sửa `ROOT` và `TMP` nếu chạy ở checkout khác. Script tự tạo thư mục firmware giả trước khi import config, dùng DB auth tạm và không gọi `nmcli` thật.

```bash
/usr/bin/python3 "$AUDIT_ROOT/docs/audit-evidence-2026-10-18/gateway-reproduce.py.txt"
```

| ID | Đầu vào / quan sát | Phát hiện trong báo cáo |
|---|---|---|
| R1 | HTTP không token gọi Wi-Fi connect, tới subprocess `nmcli` đã mock | 3 |
| R2 | Socket không hello/token gửi ACK dù config có token | 1 |
| R3 | LOAD_REPORT sai channel, mẫu cũ, 0 W vẫn thành `confirmed_load` | 7 |
| R4 | ACK đến trước LOAD_REPORT làm verifier trả ngay `ack_only` | 7 |
| R5 | Telemetry ba kênh ghi đè registry thành mảng hai kênh | 8 |
| R6 | URL tải OTA do Gateway tạo trả 401 khi không có credential | 10 |
| R7 | Node OTA đích offline, socket node khác nhận payload | 9 |
| R8 | MQTT publish trả false nhưng trigger OTA trả success | 9 |
| R9 | Logout permanent API key không thu hồi key | Quan sát, không tính lỗi độc lập |
| R12 | ACK_ONLY và CONFIRMED_LOAD đều tạo voice reply thất bại | 6 |
| R13 | Member không có device vẫn đọc vocabulary của node khác | 18 |

File firmware giả dùng trong R6–R8 cũng minh họa `save_firmware()` chấp nhận nội dung không phải ESP image. Không có hoạt động flash trong script.

### Flutter

Bản sao đã kiểm tra: `/tmp/iot-commercial-audit-20261018/flutter`. Lệnh baseline trên bản sao, trước khi thêm file tái hiện:

```bash
cd /tmp/iot-commercial-audit-20261018/flutter
/home/tuan/snap/flutter/common/flutter/bin/flutter pub get --offline
/home/tuan/snap/flutter/common/flutter/bin/flutter test --reporter expanded
/home/tuan/snap/flutter/common/flutter/bin/flutter analyze --no-pub
```

Sau baseline, chép [flutter-reproduce.dart.txt](flutter-reproduce.dart.txt) thành `test/commercial_audit_repro_test.dart` **trong bản sao**, rồi chạy:

```bash
/home/tuan/snap/flutter/common/flutter/bin/flutter test test/commercial_audit_repro_test.dart --reporter expanded
```

R10 dùng HTTP MockClient: Gateway trả `success:false` và snapshot OFF nhưng `GatewayClient` kết thúc ở ON. R11 dựng lại repository production làm mất automation. R14 đưa board ba kênh, 50 W vào repository production nhưng chỉ nhận hai thiết bị và tổng 100 W. Không dùng repository fake cho ba ca này.

### Firmware host

Bản sao có `Firmware/tests`, `firmware_esp/{ActionBox,ActionBox_V2,SubBox}/src` và `firmware_esp/common`. Đặt component cJSON vào `ActionBox_V2/managed_components/espressif__cjson` từ cache đúng lockfile, rồi chạy:

```bash
/usr/bin/python3 -m unittest discover \
  -s /tmp/iot-commercial-audit-20261018/Firmware/tests -v
```

Cache đã dùng: `/home/tuan/.cache/Espressif/ComponentManager/service_d92d8f1e/espressif__cjson_1.7.19~2_e7883232`. Các test biên dịch code C++ thật với GPIO, UART, timer, NVS và FreeRTOS giả; không thay thế kiểm chứng trên board.

### SQLite và event loop

Mã: [sqlite-lock-probe.py.txt](sqlite-lock-probe.py.txt). Tạo DB tạm, giữ write transaction ở thread phụ 250 ms, rồi gọi `RegistryManager.save()` đồng bộ trên event loop đang chạy timer 10 ms. Phép đo ban đầu trong phiên audit là 337,7 ms. Log kèm theo là phép đo lại để có artifact lưu được; không yêu cầu tái hiện đúng một con số thời gian.

```bash
/usr/bin/python3 "$AUDIT_ROOT/docs/audit-evidence-2026-10-18/sqlite-lock-probe.py.txt"
```

## Nguồn của các số liệu quy mô

173 file / 36.794 dòng: file được Git quản lý có đuôi `.py`, `.dart`, `.cpp`, `.c`, `.h`, `.kt` trong `Gateway/gateway`, `App/dtv_energy_flutter/lib` và ba thư mục firmware `src` nêu trên. Không đếm test, generated code, managed components, build hoặc asset binary.

19 file / 2.330 dòng trùng: so nội dung byte giữa hai cây `ActionBox/src` và `ActionBox_V2/src` theo đường dẫn tương đối, bao gồm file cấu hình build giống nhau. Đây là mức trùng có thể xem xét gom, không phải cam kết xóa nguyên số dòng đó mà không cần thay đổi build/test.

Mốc 40 ActionBox/5 người dùng và các SLO trong báo cáo là đề xuất nghiệm thu. Log hiện tại không chứng minh đạt tải hoặc độ tin cậy thương mại.
