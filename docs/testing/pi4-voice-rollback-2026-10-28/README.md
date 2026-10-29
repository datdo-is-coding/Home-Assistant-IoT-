# Rollback giọng nói về Pi4 — 28/10/2026

Đã triển khai Gateway thật, nạp USB app-only cho SubBox HC-288485350B54 và
ActionBox HC-28848533DDE8. Hai bo hiện chạy 2.1.0-pi4. Người dùng xác nhận
điều khiển đèn, phản hồi loa và tiếng wake tức thời đã hoạt động.

## Đường đang chạy

- ActionBox: WakeNet Hi ESP, thu trọn câu, ESP-NOW; 3 relay SET/RESET 30 ms.
- SubBox: chỉ báo wake tại chỗ, đệm PCM trong PSRAM, gửi WSS sau END, phát loa.
  LocalKws/MFCC không được build hoặc khởi tạo trong app hiện hành.
- Pi: Sherpa-ONNX Zipformer Việt 30M INT8 → CoreVoice/registry/command queue →
  ACK APPLIED → VieNeu-TTS → SubBox xác nhận playback.
- Giữ xác thực enrollment, source/room scope, token từng SubBox và TLS CA đã
  ghim. Giữ dữ liệu Firebase, registry, binding và peer; không train thêm.

Mất gói, buffer overflow, thiếu END, PCM sai định dạng và source không thuộc
SubBox đều không được biến thành lệnh. Binding giọng nói LIGHT/FAN đang có
được dùng khi có nhiều kênh cùng loại; không suy đoán relay từ thứ tự kênh.

## Bằng chứng

- Firmware: 38 bài kiểm tra qua. Bao gồm buffer thật 80.000 mẫu/5 giây, không
  upload trước END hoặc khi mất gói; wake trước VAD, khử trùng chime và từ chối
  radio broadcast/peer lạ/gói wake sai/nguồn Core chưa đăng ký.
- Gateway: 476 bài, 3 skip, không lỗi; 6 bài giao thức Pi voice chuyên biệt qua.
  Đây là kiểm tra trên máy, tách riêng kết quả nói thật bên dưới.
- Hai build ESP-IDF thành công. Kiểm tra ELF không có LocalKws/MFCCExtractor.
- Flash đúng MAC/ota_0; ROM verify-flash khớp; prefix 0–0x20000 trước/sau bằng
  nhau. Backup app/NVS và nguồn Pi giữ kín ngoài Git; không khôi phục DB cũ.
- HIL pi3: 13:45:19 UTC nhận “bật đèn”, confidence 0,80; 13:45:20 success
  CMD-23d1075dd104665121dd49a2; ActionBox ghi Ch1 ON; 13:45:25 speaker xác
  nhận đủ 36.160 byte. Người dùng xác nhận đèn bật và nghe phản hồi.
- HIL pi4: 13:56:18 nhận “tắt đèn”, confidence 0,80; success, loa phát trọn
  phản hồi. Người dùng xác nhận “ok rồi ... đã thực hiện lệnh”.
- Pi4 wake: 4 cặp log host từ WakeNet detected tới enqueue chime lần lượt
  khoảng 8, 27, 26, 44 ms. Đây là thời gian đường điều khiển qua log serial,
  không phải phép đo độ trễ âm thanh bằng thiết bị đo.

## Giới hạn còn lại

- Nhiều câu hiện chạm giới hạn thu 4.995 ms do endpoint VAD; upload khoảng
  1,5–1,9 s; ASR thật khoảng 0,82–0,84 s. TTS tạo mới câu xác nhận đầu mất
  2,95 s; câu đã cache phát nhanh hơn. Chưa tối ưu các bước này.
- Một lượt “b đèn” confidence 0,65 bị từ chối; câu hỏi ngoài lệnh điều khiển
  cũng bị từ chối. Không hạ ngưỡng hoặc sửa từ thiếu thành lệnh phỏng đoán.
- Có một lượt khởi động upload khi TTS trước chưa ACK xong: phiên bị hủy và
  WSS tự kết nối lại; lượt sau điều khiển thành công. Chưa tối ưu nói chồng.
- Chưa kiểm thử dài hạn, nhiều SubBox đồng thời, mất điện hoặc đo tải điện.
  APPLIED là ACK thiết bị, không thay thế xác nhận tải từ phép đo dòng.
- Luồng điều khiển hiện không gọi LLM. Trên Pi có file Qwen2.5-3B Q4,
  Qwen2.5-0.5B Q4 và Qwen3-0.6B Q8; file có sẵn không có nghĩa đang phục vụ.
  Chưa đổi/benchmark model hội thoại và chưa thêm bộ nhớ hội thoại.

Kiểm tra hash và tóm tắt log đặt cạnh báo cáo. Log thô, PCM/flash backup, DB
và khóa enrollment không đưa vào repo.
