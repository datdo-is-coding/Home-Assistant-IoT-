# Tính năng, đặc tính, ưu điểm và tồn tại của hệ thống

Ngày cập nhật: 2026-09-29  
Phạm vi: code hiện hành trong `Gateway/`, `Firmware/firmware_esp/SubBox/` và
`Firmware/firmware_esp/ActionBox/`. PCB, APK, dữ liệu âm thanh và code trong
`archive/` không thuộc phạm vi đánh giá.

## 1. Tổng quan

Hệ thống được chia thành ba tầng:

```mermaid
flowchart LR
    U[Người dùng] <-->|Mic, loa, nút bấm| AB[ActionBox]
    AB <-->|ESP-NOW: audio, lệnh, ACK, telemetry| SB[SubBox]
    SB <-->|WebSocket: PCM và transcript| GW[Gateway trên Raspberry Pi 4]
    SB <-->|MQTT: lệnh liên phòng, sự kiện, voice request| GW
    GW <-->|Web UI, API, Home Assistant| APP[Ứng dụng và dịch vụ]
```

- **ActionBox** tiếp xúc trực tiếp với tải điện và người dùng: relay, nút bấm,
  micro, loa, đo điện và bảo vệ tại chỗ.
- **SubBox** là bộ điều phối cấp phòng: gom nhiều ActionBox, chọn luồng audio,
  xử lý NLU đơn giản, định tuyến lệnh và phản hồi về đúng thiết bị.
- **Gateway** là bộ não trung tâm: ASR/TTS, NLU tiếng Việt đầy đủ hơn, registry,
  Web UI, MQTT, xác minh lệnh, lịch sử, OTA và tích hợp Home Assistant.

Kiến trúc hiện tại là **lai giữa edge và central**. Bảo vệ điện nằm ở
ActionBox; định tuyến nhanh nằm ở SubBox; nhận dạng giọng nói và quản trị toàn
hệ thống nằm ở Gateway.

## 2. Tính năng hiện có

### 2.1. Gateway

| Nhóm | Tính năng |
|---|---|
| Giọng nói | Nhận PCM 16 kHz qua WebSocket, chạy ASR ngoài event loop, trả transcript kèm confidence và cờ `accepted`. |
| NLU tiếng Việt | Chuẩn hóa lỗi ASR, fast path theo luật, nhận dạng lệnh ghép, phủ định, truy vấn, ngữ cảnh đa lượt theo từng client; có đường LLM local/Gemini dự phòng. |
| Điều khiển | Phân giải phòng, thiết bị và kênh relay; chọn WebSocket hoặc tuyến MQTT qua SubBox. |
| Xác minh | Chờ ACK khớp node, sequence/request và session; timeout không được báo thành công. |
| Thiết bị | Registry JSON + SQLite, pending/provision node mới, telemetry, trạng thái relay và cấu hình mong muốn/thực tế. |
| Giao diện | Web UI/API, sự kiện realtime, quản lý thiết bị, provisioning, OTA, voice và tài khoản. |
| Tích hợp | MQTT, Home Assistant discovery, discovery nội bộ và API key/session token. |
| Phản hồi | EdgeTTS hoặc TTS local, âm thanh hệ thống, cache RAM và cache đĩa có giới hạn. |
| Quan sát | Lịch sử lệnh, correction, journal, telemetry và log tác vụ chủ động. |

Điểm vào chính: [Gateway/gateway/main.py](../Gateway/gateway/main.py), giao thức
audio: [Gateway/gateway/audio_server.py](../Gateway/gateway/audio_server.py),
NLU: [Gateway/gateway/intent_engine.py](../Gateway/gateway/intent_engine.py).

### 2.2. SubBox

| Nhóm | Tính năng |
|---|---|
| Audio phòng | Nhận audio từ tối đa 4 ActionBox, VAD theo năng lượng, chọn nguồn nói và gửi một luồng lên Gateway để ASR. |
| NLU cục bộ | Chuẩn hóa tiếng Việt, phân loại intent/entity, nhớ ngữ cảnh ngắn theo ActionBox và từ chối câu phủ định không an toàn. |
| Định tuyến | Lệnh cùng phòng đi ESP-NOW; lệnh phức tạp hoặc liên phòng đi MQTT lên Gateway. |
| Quản lý node | Registry ActionBox, ánh xạ node ID với MAC, trạng thái online, relay, dòng điện và fault. |
| Vòng kín | Gắn `request_id` + `session_id`, chờ ACK ứng dụng, kiểm tra node/MAC/trạng thái trước khi nói thành công. |
| Phản hồi | Đưa TTS/chime về đúng ActionBox đã phát lệnh. |
| Vận hành | NVS, Wi-Fi provisioning, MQTT reconnect, CLI phát triển và các task FreeRTOS tách theo chức năng. |

Điểm vào chính: [SubBox/src/main.cpp](../Firmware/firmware_esp/SubBox/src/main.cpp),
pipeline task: [SubBox/src/system/task_manager.cpp](../Firmware/firmware_esp/SubBox/src/system/task_manager.cpp).

### 2.3. ActionBox

| Nhóm | Tính năng |
|---|---|
| Chấp hành | Hai kênh relay, bật/tắt/toggle, nút bấm cục bộ và LED trạng thái. |
| Đo điện | Đọc BL0942, cung cấp dòng, áp, công suất, năng lượng và telemetry định kỳ. |
| An toàn | Giới hạn dòng, ngắt quá dòng, chốt fault, watchdog và khóa bật khi mẫu cảm biến thiếu hoặc quá hạn. |
| Audio | Thu âm, VAD và gửi PCM qua ESP-NOW; nhận phản hồi âm thanh cho loa. |
| Giao thức | Lệnh JSON, ACK và telemetry; cache 32 request gần nhất để retry không toggle hai lần. |
| Định danh | ID mới sinh từ MAC; cấu hình node/phòng/kênh và ngưỡng dòng được lưu NVS. |
| Thời gian thực | Safety và relay có ưu tiên cao; callback radio chỉ đẩy dữ liệu vào queue để worker xử lý. |

Điểm vào chính: [ActionBox/src/main.cpp](../Firmware/firmware_esp/ActionBox/src/main.cpp),
bảo vệ: [safety_supervisor.cpp](../Firmware/firmware_esp/ActionBox/src/safety/safety_supervisor.cpp),
giao thức: [actionbox_protocol.cpp](../Firmware/firmware_esp/ActionBox/src/protocol/actionbox_protocol.cpp).

## 3. Tính chất kỹ thuật

- **Phân tán theo phòng:** mỗi SubBox giới hạn tối đa 4 ActionBox, giảm tải cho
  Gateway và giới hạn vùng ảnh hưởng khi một phòng gặp lỗi.
- **Event-driven và bất đồng bộ:** Gateway dùng `asyncio`; firmware dùng queue,
  callback và task FreeRTOS. Tác vụ chậm được tách khỏi callback mạng.
- **Vòng kín ở mức phần mềm:** kết quả điều khiển dựa trên ACK từ ActionBox thay
  vì coi publish/gửi packet là thành công.
- **Idempotent trong một phiên:** retry cùng `session_id/request_id` trả lại kết
  quả đã cache mà không thực thi relay lần nữa.
- **Fail-safe tại thiết bị:** ActionBox tự cắt tải khi quá dòng hoặc mất mẫu đo,
  không chờ Gateway hay MQTT.
- **Tài nguyên có giới hạn rõ:** queue firmware, thời lượng audio, context NLU và
  cache TTS đều có trần để tránh tăng bộ nhớ vô hạn.
- **Chuyên biệt tiếng Việt:** có normalizer, alias phòng/thiết bị, sửa lỗi ASR,
  phủ định, đại từ và lệnh ghép.
- **Cập nhật đồng bộ bắt buộc:** bốn trường giao thức mới `accepted`, `asr_only`,
  `session_id` và ACK vòng kín yêu cầu Gateway, SubBox và ActionBox chạy phiên
  bản tương thích.

## 4. Ưu điểm

1. **An toàn không phụ thuộc mạng:** đường bảo vệ quá dòng và cảm biến nằm trên
   ActionBox, là tầng gần tải điện nhất.
2. **Phân vai hợp lý:** ESP32 xử lý phần thời gian thực; Raspberry Pi xử lý ASR,
   TTS, dữ liệu và logic nặng.
3. **Không báo thành công giả khi mất ACK:** lời nói phản hồi phản ánh trạng thái
   xác nhận ở firmware thay vì trạng thái suy đoán.
4. **Retry ít gây tác dụng phụ:** cache request và session giảm nguy cơ lệnh
   `TOGGLE` chạy hai lần do truyền lại packet.
5. **Mở rộng theo phòng:** có thể thêm SubBox theo phòng mà không đưa toàn bộ
   audio thô về một điểm cùng lúc.
6. **Luồng giọng nói có chốt an toàn:** transcript confidence thấp bị từ chối;
   chế độ `asr_only` tránh Gateway và SubBox cùng thực thi một câu nói.
7. **Dễ chẩn đoán hơn:** telemetry, registry, Web UI, CLI firmware và test offline
   giúp khoanh vùng lỗi theo từng tầng.
8. **Code vận hành đã được giới hạn tài nguyên:** ASR chỉ chạy một lượt đồng thời,
   cache TTS dùng LRU, context có TTL và callback Wi-Fi không làm việc nặng.

## 5. Tồn tại và rủi ro còn lại

### Mức cao — xử lý trước khi triển khai ngoài mạng thử nghiệm

1. **Cấu hình bảo mật mặc định chưa phù hợp production.** MQTT dùng
   `mqtt://...:1883`, ASR dùng `ws://...`, credential MQTT nằm trong source và
   hệ thống có tài khoản quản trị mặc định. Cần chuyển secret sang biến môi
   trường/NVS bảo vệ, bắt buộc đổi mật khẩu lần đầu và dùng TLS hoặc một VLAN IoT
   cô lập. Tham chiếu: [Gateway config](../Gateway/gateway/config.py),
   [SubBox config](../Firmware/firmware_esp/SubBox/src/config/subbox_config.h),
   [auth manager](../Gateway/gateway/auth_manager.py).
2. **Chưa xác minh end-to-end trên phần cứng thật.** Build và test logic không
   thay thế thử mất gói, reboot giữa lệnh, nhiễu Wi-Fi, ngắt cảm biến, relay tải
   thật hoặc đo thời gian cắt quá dòng.
3. **ACK chỉ xác nhận phần mềm/GPIO.** ACK không chứng minh tiếp điểm relay đã
   đóng hoặc tải thực sự nhận điện. Muốn xác minh vật lý cần đối chiếu dòng/công
   suất với độ mới mẫu và đặc tính tải.

### Mức trung bình — ảnh hưởng độ bền và khả năng mở rộng

4. **Voice chưa hoạt động độc lập khi Gateway mất kết nối.** SubBox có NLU cục
   bộ nhưng ASR hiện dùng `WsASR` trên Gateway; mất Gateway thì không tạo được
   transcript mới. `DummyASR` chỉ phục vụ phát triển.
5. **Kênh ESP-NOW phải khớp kênh Wi-Fi.** Kênh được cấu hình tập trung nhưng chưa
   tự dò/chuyển khi access point đổi kênh.
6. **Exactly-once không tồn tại qua mất điện.** Cache khử trùng nằm trong RAM;
   reboot đồng thời có thể làm mất lịch sử request dù `session_id` giảm nguy cơ
   đụng ID cũ.
7. **ID cũ trong NVS không tự sửa.** Board đã được ghi cùng một ID phải provision
   lại riêng; firmware chỉ tạo ID theo MAC cho cấu hình mới.
8. **Thiết bị cùng loại trong một phòng cần định danh rõ.** Khi có nhiều relay
   cùng capability, SubBox chủ động từ chối chọn tùy tiện. Cần provision tên/kênh
   cụ thể hoặc bổ sung cú pháp phân biệt cho người dùng.
9. **Registry JSON vẫn ghi đồng bộ khi trạng thái đổi.** SQLite chỉ cập nhật node
   thay đổi, nhưng ghi file JSON vẫn có thể chặn event loop khi số node hoặc tần
   suất thay đổi tăng mạnh. Chỉ nên thêm worker/batching sau khi có số đo thực tế.
10. **Giới hạn 4 ActionBox/phòng là cố ý.** Mở rộng vượt mức này cần đo RAM, kích
    thước queue, băng thông ESP-NOW và chất lượng chọn nguồn audio trước khi tăng
    hằng số.

### Khoảng trống kiểm thử

11. Test NLU Gateway đã chạy offline; regression ACK/cache/context đã có. Hai
    firmware đã build thành công, nhưng test NLU native của SubBox chưa chạy trên
    máy hiện tại vì thiếu compiler C++ host trong `PATH`.
12. Chưa có số đo chuẩn trên thiết bị cho độ trễ đầu-cuối, packet loss, RSSI tối
    thiểu, độ chính xác BL0942, ngưỡng VAD, nhiệt relay và tuổi thọ flash/NVS.
13. Chưa có test hỗn loạn dài giờ cho reconnect MQTT/WebSocket, đầy queue, mất
    Wi-Fi, Gateway restart và nhiều người nói gần đồng thời.

## 6. Trạng thái kiểm chứng hiện tại

| Hạng mục | Trạng thái |
|---|---|
| NLU Gateway | 84/84 test đạt |
| Utility Gateway | 5/5 test đạt |
| Regression hệ thống | 9/9 test đạt |
| Python compile | Thành công |
| Build SubBox ESP-IDF | Thành công |
| Build ActionBox ESP-IDF | Thành công |
| Test NLU C++ native | Chưa chạy do thiếu compiler host |
| Test trên board và tải điện thật | Chưa thực hiện trong đợt rà soát này |

Chi tiết lỗi ban đầu và cách sửa nằm tại
[system-logic-audit-2026-09-29.md](system-logic-audit-2026-09-29.md) và
[system-logic-fixes-2026-09-29.md](system-logic-fixes-2026-09-29.md).

## 7. Ưu tiên tiếp theo

1. Thay credential mặc định, tách secret khỏi source và cô lập/TLS hóa mạng điều
   khiển trước khi cho hệ thống ra ngoài LAN thử nghiệm.
2. Flash đồng bộ ba tầng và chạy ma trận thử nghiệm: lệnh bình thường, mất ACK,
   packet trùng, reboot từng tầng, mất cảm biến và fault relay.
3. Đo độ trễ giọng nói, tỉ lệ mất audio/ESP-NOW, thời gian cắt tải và sai số đo
   điện trên phần cứng thật.
4. Chỉ tối ưu registry, queue hoặc tăng số node sau khi profiling chỉ ra nút thắt.
