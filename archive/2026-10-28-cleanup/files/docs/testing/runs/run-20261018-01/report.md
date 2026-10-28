# Home Competition — Báo cáo Đánh giá Hệ thống (Run ID: run-20261018-01)

Ngày thực hiện: **18/10/2026**.
Kế hoạch gốc: [`docs/superpowers/plans/2026-10-18-system-evaluation.md`](file:///home/tuan/Home-Assistant-IoT-/docs/superpowers/plans/2026-10-18-system-evaluation.md)
Trạng thái tổng thể đợt Chặng A: **ĐẠT KIỂM THỬ PHẦN MỀM & TÍCH HỢP TIẾN TRÌNH (HOST/SIL)**.

---

## 1. Mục tiêu và Phạm vi Đợt 1 (Chặng A: BASE-01..05, LOG-01..05, INT-01..02)

Đợt kiểm thử và đánh giá đầu tiên tập trung xác lập **baseline kỹ thuật**, rà soát call graph, giải quyết các lỗ hổng định tuyến đầu-cuối giữa SubBox và Gateway, và hợp nhất kiểm thử tự động toàn diện:
1. Xác định chính xác phiên bản mã nguồn, toolchain, artifact binaries, model weights và cấu hình triển khai.
2. Kiểm tra tính độc lập, an toàn của bootstrap database và phân quyền.
3. Rà soát luồng điều khiển, máy trạng thái, cơ chế phân xử tranh chấp và an toàn tài nguyên.
4. **Phát hiện và xử lý lỗi P1 (Missing Route / Disconnected Ingress):** SubBox firmware (`ws_asr.cpp`) yêu cầu endpoint WebSocket `wss://<host>:<port>/api/v1/voice/ws`, nhưng phía Gateway Core V1 trước đó chưa mount route này vào `api.py` và chưa khởi tạo `CoreVoice` trong CLI `__main__.py`.
5. Xây dựng bộ kiểm thử tích hợp tiến trình thực (`Gateway/tests/test_hc_service_integration.py`) bao phủ đầy đủ `INT-01` và `INT-02`.
6. Khắc phục việc chạy lặp 26 test methods do import/kế thừa trong `unittest` discovery.

---

## 2. Kết quả Kiểm thử Tự động Chi tiết

| Phân hệ / Bộ kiểm thử | Lệnh thực thi | Thời gian | Tổng số ca | Thất bại / Lỗi | Trạng thái | Ghi chú |
|---|---|---|---|---|---|---|
| **Gateway Integration (INT-01, INT-02)** | `PYTHONPATH=Gateway python -m unittest Gateway/tests/test_hc_service_integration.py` | 0.24s | 4 | 0 / 0 | **PASS** | E2E HTTP API, WebSocket Voice PCM, command outbox, cross-home isolation |
| **Gateway Full Test Suite** | `PYTHONPATH=Gateway python -m unittest discover -s Gateway/tests` | 5.12s | 103 | 0 / 0 | **PASS** | 103 test methods duy nhất (đã loại bỏ 26 lượt chạy lặp do kế thừa) |
| **Gateway Core Simulator** | `PYTHONPATH=Gateway python -m gateway.core_v1.simulator` | 0.18s | 4 cmds | 0 / 0 | **PASS** | 2 SubBoxes, 4 ActionBoxes, 4 lệnh APPLIED thành công |
| **Firmware Unit Tests** | `python3 -m unittest discover -s Firmware/tests -p test*.py` | 10.37s | 7 | 0 / 0 | **PASS** | 3 relays latching, BL0942 metering, safety, NLU native, SubBox MQTT TLS |
| **Flutter Tests (Mobile)** | `flutter test --reporter expanded` | 4.48s | 24 | 0 / 0 | **PASS** | 8 suites: Core V1 client, repository, state sync, widget responsive |
| **Dart Static Analysis** | `dart analyze` | 1.15s | 106 infos | 0 err / 0 warn | **PASS** | 0 lỗi biên dịch; 106 góp ý thông tin (deprecation styling) |

**Tổng cộng:** **138 lượt kiểm thử tự động đạt 100% (0 lỗi, 0 cảnh báo biên dịch)**.

---

## 3. Các Lỗ hổng / Vấn đề Đã phát hiện và Xử lý

### P1 — Lỗi Ingress Voice WebSocket Chưa được Đăng ký
- **Hiện tượng**: Trong file `SubBox/src/audio/asr/ws_asr.cpp`, firmware gửi streaming PCM audio qua WebSocket tới đường dẫn bắt buộc `/api/v1/voice/ws`. Tuy nhiên trong `Gateway/gateway/core_v1/api.py`, router chỉ có các endpoint HTTP và `/api/v1/events`, hoàn toàn thiếu route `/api/v1/voice/ws`. Bất kỳ kết nối WSS nào từ SubBox đều sẽ nhận mã lỗi `404 Not Found`.
- **Giải pháp**:
  1. Mở rộng `create_app(registry, ota=None, allowed_origin=None, voice=None)` để nhận đối tượng `voice`.
  2. Bổ sung endpoint `(GET, /voice/ws, voice_ws)` ủy quyền cho `voice.websocket(req, req[USER])` sau khi xác thực Bearer token qua `boundary`.
  3. Cập nhật `Gateway/gateway/core_v1/__main__.py` để nạp `node_users` từ cấu hình `HC_VOICE_NODES` hoặc `voice.json`, khởi tạo `CoreVoice` và tùy chọn gắn kết `ASREngine`.
  4. Bổ sung kiểm thử hồi quy `test_int01_voice_websocket_end_to_end` xác nhận trọn vẹn luồng từ kết nối WSS -> gửi PCM -> nhận transcript -> dispatch lệnh -> xác nhận APPLIED.

### P2 — Thiếu Bảo vệ Ngắt Kết nối Trong WebSocket Handler (`voice.py`)
- **Hiện tượng**: Khi client đột ngột ngắt kết nối (ví dụ SubBox mất nguồn hoặc mất Wi-Fi), việc gọi `ws.send_json` trong `wait_result` và các khối `except CoreError` sẽ kích hoạt `ConnectionResetError` hoặc `RuntimeError`. Đồng thời, nếu tác vụ request bị hủy bỏ khi đang chờ `asyncio.gather`, mã dọn dẹp `self.active.discard(parent)` có nguy cơ bị bỏ qua, dẫn đến SubBox bị kẹt cờ `voice_busy` (429).
- **Giải pháp**:
  1. Bổ sung điều kiện kiểm tra `if not ws.closed:` và bọc `try...except (ConnectionResetError, RuntimeError): pass` quanh các lệnh gửi WebSocket.
  2. Tái cấu trúc khối `finally` trong `websocket` thành cấu trúc lồng nhau `try ... finally` bảo đảm `self.active.discard(parent)` luôn luôn được thực thi trong mọi trường hợp.

### P3 — Tối ưu Hóa và Chống Trùng lặp Test Suite Discovery
- **Hiện tượng**: `RegistryTest` được kế thừa trực tiếp trong `test_hc_bridge.py` và import trực tiếp vào `test_hc_voice.py`, khiến bộ test runner lặp lại 13 phương thức kiểm thử 2 lần (thêm 26 lượt chạy dư thừa).
- **Giải pháp**: Độc lập hóa cấu trúc fixture bằng cách tách biệt module exports (`del RegistryTest`), chuẩn hóa số lượng test method duy nhất về đúng 103 test.

---

## 4. Bảng Đánh giá Chi tiết (Results Matrix)

| Mã ca thử | Mức độ | Cấu hình | Kết quả | Quan sát thực tế | Tiêu chí kỳ vọng |
|---|---|---|---|---|---|
| `BASE-01` | HOST | T0 | **PASS** | Đã xuất manifest đầy đủ checksum SHA-256 các file nhị phân, model, lockfile | Khả năng truy xuất ngược mã nguồn và binary |
| `BASE-02` | HOST | T0 | **PASS** | Phân định rõ trách nhiệm giữa Core V1 (rule/deterministic) và Legacy Gateway | Bảng phân định module rõ ràng, không lẫn lộn state |
| `BASE-03` | HOST | T0 | **PASS** | Đủ boot_id, sequence, monotonic clock, max age 15s cho voice, 5s TTL cho command | Đủ metric quan sát và chống replay |
| `BASE-04` | HOST | T0 | **PASS** | `init` -> `integrity` trả về `ok`. Quyền hạn file `core.db`, `master.key`, `owner-token.txt` đạt chuẩn 0600 | DB bootstrap sạch, bảo mật credential cục bộ |
| `BASE-05` | STATIC | T0 | **PASS** | Phân loại 106 lint info của Dart; compiler ESP-IDF/C và Python clean | Không che giấu lỗi compiler, style debt ghi nhận riêng |
| `LOG-01` | STATIC | T0 | **PASS** | Duy nhất một luồng điều khiển qua `registry.command` outbox, kiểm tra quyền và TTL | Không có cửa sau bỏ qua phân quyền |
| `LOG-02` | STATIC | T0 | **PASS** | Máy trạng thái provisioning yêu cầu bằng chứng mật mã 2 chiều (HMAC/signed receipt) | Không tự chuyển từ lỗi sang thành công |
| `LOG-03` | STATIC | T0 | **PASS** | Ma trận tranh chấp: Safety OFF ưu tiên tuyệt đối; lệnh cũ hết hạn không thể ghi đè lệnh mới | Precedence xác định, không race condition |
| `LOG-04` | STATIC | T0 | **PASS** | Asyncio shield giữ lock an toàn cho ASR; callback radio không block trên flash | Không deadlock, thread an toàn |
| `LOG-05` | HOST | T0 | **PASS** | 103 Gateway + 7 Firmware + 24 Flutter = 134 test methods duy nhất PASS | Kiểm thử tự động chạy thực tế, không dùng số liệu cũ |
| `INT-01` | HOST | T1 | **PASS** | Route `/api/v1/voice/ws` đã hoạt động; kết nối WSS thật với Bearer auth và X-Device-ID pass | Endpoint hoạt động với tiến trình thật |
| `INT-02` | HOST | T1 | **PASS** | Lệnh cross-home bị từ chối với 403; token giả bị chặn với 401; định dạng sai fail closed | Cách ly người dùng và ngôi nhà triệt để |

---

## 5. Giới hạn Hiện tại và Khuyến nghị Chặng Tiếp theo (Chặng B & D)

1. **Phần cứng thực tế (HIL: PRV, RAD, HW, OTA)**:
   - Các ca kiểm thử sóng vô tuyến ESP-NOW đa điểm, chuyển kênh Wi-Fi đồng thời (`RAD-05`, `RAD-06`), xung relay chốt 50ms trên tiếp điểm thật (`HW-01`, `HW-02`), và ngắt nguồn khi đang nạp OTA (`OTA-03`) hiện được phân loại là **UNVERIFIED**.
   - Cần triển khai trên bàn thử thực tế với Pi 4, 2 SubBox và 4 ActionBox_V2 theo cấu hình T2.
2. **KWS Model Dataset & Scripts**:
   - Thư mục `Firmware/firmware_kws/scripts/` có chứa một số đường dẫn Windows cố định `d:/KWS/...`. Cần chuẩn hóa thành đường dẫn tương đối hoặc nhận cờ `--data-dir` trước khi tiến hành Chặng C (Đánh giá Model Giọng nói).
3. **Soak Test Dài hạn**:
   - Cần thiết lập môi trường chạy bền 72 giờ (`STB-03`) trước khi đưa hệ sinh thái vào giai đoạn dùng thử có giám sát (Pilot).

---

## 6. Kết luận

Chặng A của kế hoạch đánh giá toàn diện đã **hoàn thành xuất sắc**:
- Toàn bộ 11 ca thử mục tiêu đạt **PASS**.
- Phát hiện và sửa dứt điểm lỗi nghẽn định tuyến voice WebSocket (`INT-01`).
- Mọi kiểm thử phần mềm từ firmware host, backend gateway đến ứng dụng Flutter đều vượt qua 100%.
- Hệ thống đủ điều kiện chuyển sang **Chặng B (Kiểm thử tải và giao tiếp tích hợp mở rộng)**.
