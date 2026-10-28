# Các sửa lỗi sau đợt rà soát 2026-09-29

Phạm vi: Gateway, ActionBox, SubBox. Không sửa PCB, âm thanh, APK hoặc archive;
không flash thiết bị. Các thay đổi chưa commit có trước được giữ lại.

## Thay đổi

| Vấn đề trong báo cáo audit | Xử lý trong code |
|---|---|
| 1. Queue chứa `std::string` | Dùng `CommandQueueItem` chỉ chứa số, enum và mảng ký tự; `static_assert` kiểm tra khả năng sao chép byte; chuyển sang object C++ ở phía nhận. |
| 2. Phủ định thành lệnh bật | Chặn phủ định trước các nhánh điều khiển; câu chứa “đang” được phân loại truy vấn. Các câu hỏi có “không” bị từ chối thận trọng. |
| 3. Transcript độ tin cậy thấp vẫn chạy | Gateway trả `accepted:false` và text rỗng; SubBox chỉ sử dụng transcript được chấp nhận rõ ràng. |
| 4. MQTT không nối hai tầng | Nối `home/subbox/+/voice/request`, `/voice/response`, `/command`, `/event/actionbox`; học tuyến từ telemetry; lệnh gửi qua tuyến SubBox chỉ publish một lần. |
| 5. Hai tầng cùng thực thi ASR | SubBox khai báo `asr_only:true`; Gateway trả transcript rồi dừng. Khi cần chuyển lên Gateway, giữ nguyên câu nói; khử yêu cầu MQTT trùng trong bộ nhớ. |
| 6. Hardcode AB001 | Học ID vật lý từ JSON và MAC, dùng ID đó cho audio và lệnh. Board mới lấy ID từ MAC; ID đã lưu trong NVS được giữ. Từ chối ID trùng ở hai MAC. |
| 7. Thành công trước ACK | SubBox chờ ACK ứng dụng, kiểm tra node/request/session/MAC và trạng thái. Gateway chờ ACK khớp lệnh; timeout/lỗi, kể cả lệnh hàng loạt, không nói “đã bật”. Telemetry cập nhật registry thật. |
| 8. Cảm biến ngừng trả dữ liệu | Chặn bật khi chưa có mẫu hợp lệ hoặc mẫu quá hạn; kiểm tra định kỳ để cắt relay đang ON và chốt lỗi. `SAFETY_SENSOR_TIMEOUT_MS` mặc định 2000 ms. |
| 9. Giữ mutex khi stagger relay | Nhả mutex trước khi chờ, lấy lại và kiểm tra lỗi/trạng thái/mẫu cảm biến trước khi đóng. Lệnh tắt hoặc fault hủy yêu cầu bật đang chờ qua `target_state`. |
| 10. Chặn callback Wi-Fi | Callback ESP-NOW chỉ sao chép vào queue hữu hạn; worker xử lý. ASR start/feed/stop chạy ngoài khóa trạng thái AudioManager. Không dùng transcript của phiên bị lỗi gửi audio. |
| 11. ASR chặn asyncio | Chạy suy luận trong thread, giới hạn một lần suy luận; yêu cầu khi bận được từ chối thay vì tích lũy audio. |
| 12. Một cập nhật ghi lại mọi node | Bỏ ghi khi relay không đổi; chỉ sync SQLite node thay đổi. JSON vẫn được ghi nguyên tử khi trạng thái thay đổi để giữ cách lưu hiện có. |
| 13. Ngữ cảnh lẫn client | Gateway tách theo client, có TTL và giới hạn 128 phiên. SubBox chỉ dùng lịch sử cùng ActionBox trong 30 giây. |
| 14. Request ID lặp sau reboot | Thêm `session_id` ngẫu nhiên theo phiên; cache ActionBox xét cặp session/request; ACK mang lại session. |
| 15. Cache TTS vô hạn | LRU tối đa 16 MiB dữ liệu audio và 256 entry; dọn file audio quá 7 ngày hoặc vượt tổng 128 MiB lúc khởi tạo và sau khi ghi. |
| 16. Radio cố định rải rác | Một cấu hình `CONFIG_ACTIONBOX_ESPNOW_CHANNEL` trong `menuconfig > ActionBox radio`; peer dùng kênh radio hiện tại. Mặc định vẫn 11. |

Sửa thêm: phép thay chuỗi UTF-8 “mở/ngắt”; chuẩn hóa khoảng trắng trước đổi từ;
telemetry lớn hơn 250 byte bị transport loại; từ chối JSON quá dài thay vì cắt;
kiểm tra lỗi đọc cảm biến khi truy vấn; không biến lệnh relay không hỗ trợ thành
PING thành công; bỏ đánh giá rule bằng nhiệt độ giả 27,5°C.

## Kiểm chứng

- `python Gateway/tests/test_intent_engine_v3.py`: 84/84.
- `python -m unittest discover -s Gateway/tests -p test_runtime_utils.py`: 5/5.
- `python -m unittest discover -s Gateway/tests -p test_system_regressions.py`: 9/9.
- `python -m compileall -q Gateway/gateway`: thành công.
- SubBox: build ESP-IDF thành công.
- ActionBox: build ESP-IDF thành công sau `reconfigure build` để nhận Kconfig mới.
- `python Firmware/tests/test_nlu_native.py`: bỏ qua trên máy hiện tại vì không
  có compiler C++ host trên PATH. Test biên dịch và chạy các file NLU thật khi
  có `g++`/`c++`; không thay thế bằng kiểm tra chuỗi source.

## Giới hạn triển khai

- Cần cập nhật đồng bộ Gateway và hai firmware vì có trường `accepted`,
  `asr_only`, `session_id` và luồng ACK mới.
- Chưa đo độ trễ, mất gói, ngưỡng bảo vệ hoặc kiểm thử tải điện trên thiết bị thật.
  ACK xác nhận trạng thái phần mềm relay; không chứng minh tiếp điểm hay tải điện.
- Kênh AP phải cố định và khớp cấu hình ActionBox. Chưa có tự dò kênh khi AP đổi kênh.
- ID cũ bị trùng trong NVS cần được cấu hình lại riêng; không tự đổi danh tính board đã dùng.
- Khi nhiều relay cùng loại trong một phòng, SubBox từ chối chọn tùy tiện.
  Luồng MQTT bổ sung tập trung vào lệnh relay/voice/telemetry, không triển khai
  một hệ provisioning, OTA hay điều khiển nhiệt độ mới.
- JSON registry vẫn ghi đồng bộ khi relay đổi. Nếu đo được đây là nút thắt sau
  khi triển khai, bước tiếp theo là gom các lần ghi; chưa thêm worker lưu trữ.
- Khử MQTT trùng dùng cache hữu hạn trong RAM; không bảo đảm exactly-once qua
  mất điện của cả Gateway và ActionBox.
