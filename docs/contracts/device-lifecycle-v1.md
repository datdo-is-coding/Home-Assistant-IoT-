# Hợp đồng Vòng đời Thiết bị v1 (Device Lifecycle Contract v1)

**Phiên bản:** 1.0.0 — 19/10/2026  
**Trạng thái:** Chuẩn hóa giao thức liên tầng (Gateway - App Android - Firmware ESP32)  
**Tài liệu liên quan:** `docs/superpowers/specs/2026-10-19-device-lifecycle-android-design.md`, `docs/superpowers/plans/2026-10-19-commercialization-device-lifecycle-android.md`

---

## 1. Mục tiêu và Phạm vi

Hợp đồng này quy định chi tiết cấu trúc dữ liệu, giao thức truyền tin (Wire v2), quy tắc thẩm định (validation), trạng thái vận hành, và bộ giải mã đèn LED (LED pattern resolver) dùng chung cho cả ba tầng:
1. **Gateway** (Python 3.12 / SQLite / MQTT Broker)
2. **App Android / Client** (Flutter / Dart 3)
3. **Firmware** (ESP32 C++17 / FreeRTOS / ESP-NOW)

Mọi thay đổi trên cấu trúc gói tin hoặc trạng thái phải đảm bảo tương thích ngược hoặc nâng version giao thức có kiểm soát.

---

## 2. Định danh và Mô tả Thiết bị (`DeviceDescriptor`)

Mỗi thiết bị phần cứng trong hệ thống được định danh duy nhất bởi một bộ mô tả (`DeviceDescriptor`):

| Trường | Kiểu dữ liệu | Bắt buộc | Mô tả | Quy tắc kiểm tra |
|---|---|---|---|---|
| `device_uid` | `string` | Có | Định danh vật lý duy nhất của thiết bị | Độ dài 4–64 ký tự, ký tự chữ số/gạch dưới/gạch ngang. Không trùng lặp trong cùng Home (`DUPLICATE_UID`). |
| `board_model` | `string` | Có | Tên mã phần cứng của board | Thuộc danh sách hỗ trợ: `actionbox_v1`, `actionbox_v2`, `subbox_v1`. Không xác định -> `UNKNOWN_MODEL`. |
| `board_revision` | `string` | Có | Phiên bản phần cứng (PCB rev) | Ví dụ: `v1.2`, `v2.0` |
| `protocol_version` | `integer` | Có | Phiên bản giao thức truyền thông | Bắt buộc bằng `2` đối với Wire v2. Khác 2 -> `UNSUPPORTED_PROTOCOL`. |
| `capabilities` | `list[string]` | Có | Danh sách tính năng phần cứng hỗ trợ | Ví dụ: `["relay", "energy_meter"]`, `["relay", "energy_meter", "voice"]`, `["wifi", "espnow_router"]`. |
| `home_id` | `string` | Có | ID ngôi nhà sở hữu thiết bị | Chuỗi định danh Home |
| `owner_epoch` | `integer` | Có | Thế hệ sở hữu (owner epoch) | Số nguyên dương tăng đơn điệu (monotonic uint32). Tăng khi factory reset hoặc chuyển chủ. Nếu `owner_epoch < current_epoch` -> `OLD_EPOCH`. |
| `boot_id` | `string` | Có | Định danh phiên khởi động (boot session UUID) | Thay đổi sau mỗi lần khởi động lại phần cứng |
| `config_revision` | `integer` | Có | Phiên bản cấu hình người dùng đã lưu | Số nguyên tăng dần mỗi khi cập nhật cấu hình |

### Ma trận Số Kênh Relay theo Board Model

| `board_model` | Số kênh Relay (`channel_count`) | Mô tả phần cứng |
|---|---|---|
| `actionbox_v1` | **2** | ActionBox V1 — 2 relay đơn ổn định, đo dòng BL0942 |
| `actionbox_v2` | **3** | ActionBox V2 — 3 relay chốt (latching), đo dòng độc lập, voice |
| `subbox_v1` | **0** | SubBox điều phối — 0 relay tải, cầu nối Wi-Fi / ESP-NOW / Voice |

---

## 3. Quản lý Thao tác Vòng đời (`Operation`)

Mọi thao tác quản trị thiết bị (nhận diện, khởi động lại, đặt lại kết nối, khôi phục cài đặt gốc, xóa khỏi nhà, đẩy cấu hình) đều được quản lý dưới dạng một `Operation`:

| Trường | Kiểu dữ liệu | Bắt buộc | Mô tả |
|---|---|---|---|
| `kind` | `string` (enum) | Có | Loại thao tác (`identify`, `reboot`, `network_reset`, `factory_reset`, `remove_from_home`, `configure`) |
| `operation_id` | `string` | Có | UUID duy nhất cho từng yêu cầu thao tác |
| `device_uid` | `string` | Có | UID thiết bị đích chịu tác động |
| `state` | `string` (enum) | Có | Trạng thái thực thi hiện tại |
| `error_code` | `string` / `null` | Không | Mã lỗi nếu thao tác thất bại |
| `expires_at` | `float` (timestamp) | Có | Thời điểm hết hạn hiệu lực của thao tác (epoch seconds) |

### Enums Thao tác

- **`OperationKind`**:
  - `identify`: Yêu cầu nháy đèn nhận diện vị trí thiết bị (tối đa 15 giây, không đóng/ngắt relay tải).
  - `reboot`: Khởi động lại vi điều khiển an toàn (đưa tải OFF trước khi reboot).
  - `network_reset`: Xóa cấu hình mạng/liên kết peer để ghép nối lại, giữ nguyên quyền sở hữu và hiệu chuẩn.
  - `factory_reset`: Khôi phục cài đặt gốc toàn diện: xóa Wi-Fi, peer keys, cấu hình người dùng; tăng `owner_epoch`; đưa mọi relay OFF.
  - `remove_from_home`: Thu hồi quyền truy cập, tombstone bản ghi tại Gateway và điều phối factory reset nếu thiết bị online.
  - `configure`: Đẩy cấu hình mới xuống thiết bị qua Wire v2 framing.

- **`OperationState`**:
  - `accepted`: Gateway đã tiếp nhận yêu cầu hợp lệ.
  - `awaiting_confirmation`: Đang chờ xác nhận vật lý (nhấn nút xác nhận trong 5 s).
  - `running`: Đang truyền tin hoặc đang thực thi trên thiết bị.
  - `awaiting_reconnect`: Thiết bị đang khởi động lại hoặc đổi mạng, chờ kết nối lại.
  - `succeeded`: Thao tác hoàn tất và đã nhận ACK xác nhận từ thiết bị.
  - `failed`: Thao tác bị lỗi từ chối hoặc lỗi phần cứng.
  - `timed_out`: Quá hạn thời gian phản hồi mà không nhận được xác nhận từ thiết bị.

---

## 4. Đặc tả Giao thức Đóng gói Cấu hình Wire v2 (Framing)

Để đảm bảo tương thích với giới hạn kích thước gói tin của ESP-NOW và các liên kết vô tuyến công suất thấp:

### Các Hạn Mức Vật Lý & Vận Hành

- **`WIRE_V2_MAX_FRAME_LEN = 250` bytes**: Giới hạn kích thước một frame vô tuyến.
- **`WIRE_V2_MAX_CHUNK_LEN = 160` bytes**: Giới hạn payload dữ liệu tối đa của một mảnh cấu hình (chunk). Mọi chunk có độ dài > 160 bytes sẽ bị từ chối với lỗi `OVERSIZE_FRAGMENT`.
- **`WIRE_V2_MAX_CONFIG_LEN = 4096` bytes**: Giới hạn kích thước toàn bộ blob cấu hình. Cấu hình > 4096 bytes bị từ chối với lỗi `OVERSIZE_CONFIG`.
- **`WIRE_V2_REASSEMBLY_TIMEOUT_SEC = 10.0` giây**: Thời gian tối đa cho phép ghép hoàn chỉnh các chunk kể từ khi nhận gói `Begin`. Nếu quá 10 s chưa nhận đủ -> `REASSEMBLY_TIMEOUT`.
- **Giới hạn đồng thời (Concurrency Limits)**:
  - ActionBox: Tối đa **1** thao tác cấu hình diễn ra tại một thời điểm (`WIRE_V2_MAX_CONCURRENT_OPS_ACTIONBOX = 1`).
  - SubBox: Tối đa **2** thao tác cấu hình diễn ra đồng thời (`WIRE_V2_MAX_CONCURRENT_OPS_SUBBOX = 2`).
  - Vượt quá giới hạn -> `CONCURRENCY_LIMIT_EXCEEDED`.

### Quy trình Truyền Nhận Cấu hình: Begin - Chunk - Commit

1. **`WireV2ConfigBegin`**:
   - `operation_id`: UUID thao tác cấu hình
   - `config_revision`: Phiên bản cấu hình mới
   - `total_len`: Tổng dung lượng payload cấu hình (bytes, <= 4096)
   - `chunk_count`: Tổng số mảnh phân đoạn
   - `crc32`: Mã kiểm tra CRC-32 (IEEE 802.3) của toàn bộ dữ liệu cấu hình
2. **`WireV2ConfigChunk`**:
   - `operation_id`: UUID thao tác cấu hình
   - `chunk_index`: Chỉ số mảnh (0-indexed, từ `0` đến `chunk_count - 1`)
   - `payload`: Mảng byte dữ liệu (độ dài <= 160 bytes)
3. **`WireV2ConfigCommit`**:
   - `operation_id`: UUID thao tác cấu hình
   - `config_revision`: Phiên bản cấu hình mới
   - `crc32`: Mã kiểm tra CRC-32 xác nhận lại tính toàn vẹn
4. **Kiểm tra Toàn vẹn (Integrity Check)**:
   - Khi nhận đủ các chunk, bên nhận ghép lại theo đúng thứ tự chỉ số và tính CRC-32.
   - Nếu `calculated_crc != begin.crc32` hoặc `calculated_crc != commit.crc32` -> từ chối lưu và báo lỗi `CRC_MISMATCH`.

---

## 5. Trạng thái Vòng đời & Kết nối (Enums)

- **`LifecycleState`**:
  - `unclaimed`: Thiết bị mới xuất xưởng hoặc vừa factory reset; chưa gán chủ sở hữu.
  - `claiming`: Đang trong cửa sổ ghép nối / xác thực quyền sở hữu (setup window tối đa 180 s).
  - `claimed`: Đã được gán vào Home, đã đồng thuận khóa và cấu hình hoạt động.
  - `resetting`: Đang trong tiến trình xóa cấu hình / khởi động lại an toàn.
  - `decommissioned`: Đã gỡ khỏi Home; thu hồi quyền truy cập.

- **`ConnectivityState`**:
  - `unknown`: Chưa xác định trạng thái kết nối.
  - `connecting`: Đang trong tiến trình đàm phán kết nối mạng / broker.
  - `online`: Đang kết nối ổn định và phản hồi heartbeat bình thường.
  - `offline`: Mất kết nối mạng / không phản hồi quá ngưỡng timeout.

- **`FaultKind`**:
  - `none`: Không có cảnh báo lỗi.
  - `over_current`: Quá dòng trên một hoặc nhiều kênh tải.
  - `over_temperature`: Quá nhiệt trên board điều khiển.
  - `relay_welded`: Lỗi dính tiếp điểm relay (phát hiện điện áp khi relay mở).
  - `meter_fault`: Lỗi giao tiếp hoặc hỏng chip đo điện năng (BL0942/PZEM).
  - `system_fault`: Lỗi hệ thống khác (bộ nhớ NVS hỏng, sụt nguồn, watchdog reset).

---

## 6. Ma trận Đèn LED Trạng Thái (`LedPattern Resolver`)

Đèn LED trạng thái (LED1/system) báo hiệu trực quan cho người dùng theo thứ tự ưu tiên nghiêm ngặt từ cao xuống thấp:

```
ƯU TIÊN CAO NHẤT:
  1. FAULT (Lỗi an toàn phần cứng / tải)
  2. AWAITING RESET CONFIRMATION (Chờ nhấn nút xác nhận Factory / Network reset)
  3. SETUP & LIFECYCLE (Config applying / Claiming / Unclaimed)
  4. IDENTIFY (Đang nháy đèn nhận diện thiết bị)
  5. CONNECTIVITY (Connecting / Offline khi đã Claimed)
  6. READY (Claimed & Online: sáng 2 s rồi tắt hẳn)
ƯU TIÊN THẤP NHẤT
```

### Chi tiết Chu Kỳ Nhịp Đèn LED

| Tên mẫu (`LedPattern`) | Định nghĩa xung nhịp (Timing) | Tổng chu kỳ (Period) | Diễn giải trên App |
|---|---|---|---|
| `fault` | 4 nhịp [200 ms ON / 200 ms OFF], nghỉ 2000 ms | 3600 ms | “Lỗi an toàn phần cứng / relay” |
| `awaiting_factory_reset` | 5 nhịp [200 ms ON / 200 ms OFF], nghỉ 1000 ms (tối đa 5 s) | 3000 ms | “Chờ nhấn nút xác nhận khôi phục cài đặt gốc” |
| `awaiting_network_reset` | 3 nhịp [200 ms ON / 200 ms OFF], nghỉ 1000 ms (tối đa 5 s) | 2200 ms | “Chờ nhấn nút xác nhận đặt lại kết nối” |
| `claiming` | Nháy đều 250 ms ON / 250 ms OFF (2 Hz, tối đa 180 s) | 500 ms | “Sẵn sàng thêm — Đang mở ghép nối” |
| `config_applying` | 2 nhịp [200 ms ON / 200 ms OFF], nghỉ 800 ms | 1600 ms | “Đang lưu cấu hình trên thiết bị” |
| `unclaimed` | Nháy đều 500 ms ON / 500 ms OFF (1 Hz, liên tục) | 1000 ms | “Chưa được thêm vào Nhà” |
| `identify` | 3 nhịp [200 ms ON / 200 ms OFF], nghỉ 1800 ms (tối đa 15 s) | 3000 ms | “Thiết bị này đang nháy đèn nhận diện” |
| `offline` | 2 nhịp [200 ms ON / 200 ms OFF], nghỉ 2000 ms | 2800 ms | “Mất kết nối — Ngoại tuyến” |
| `connecting` | 1 nhịp [200 ms ON / 200 ms OFF], nghỉ 1000 ms | 1400 ms | “Đang kết nối lại mạng” |
| `ready` | Sáng liên tục 2000 ms khi bắt đầu vào trạng thái, sau đó tắt | 2000 ms | “Đang hoạt động bình thường” |
| `off` | Tắt hoàn toàn (0% duty cycle) | ∞ | Tắt đèn |

### Hàm logic pure tính mức sáng `status_led_is_active(pattern, elapsed_ms)`:
- `elapsed_ms`: Thời gian trôi qua (milliseconds) tính từ thời điểm kích hoạt mẫu hiện tại.
- Trả về `true` (LED ON) hoặc `false` (LED OFF).
