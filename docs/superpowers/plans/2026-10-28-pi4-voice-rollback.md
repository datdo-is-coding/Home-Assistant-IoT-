# Rollback xử lý giọng nói về Pi4

Theo yêu cầu người dùng: ActionBox giữ WakeNet/thu âm và relay SET/RESET 30 ms;
SubBox chỉ chuyển PCM lên Pi qua WSS và phát phản hồi. Pi chạy Sherpa tiếng
Việt hiện có, phân giải phòng/thiết bị và gửi lệnh qua Core đã xác thực.

1. Giữ app Firebase, registry/gán kênh, enrollment, CA, OTA và dữ liệu hiện tại.
   Backup Pi cũ có ở `20261025-before`, nhưng không khôi phục database cũ.
2. Bật ASR trên Gateway; tái dùng CoreVoice cho kiểm tra nguồn/phòng/quyền,
   idempotency, TTL và chờ ACK. Giữ binding giọng nói LIGHT/FAN hiện có khi
   trong phòng có nhiều kênh cùng loại; tên thiết bị cụ thể vẫn phân giải riêng.
3. Cho thiết bị Core đã xác thực WSS gửi PCM; giữ token từng SubBox, CA và
   xác nhận playback. PCM bị hủy/mất gói không được chuyển thành lệnh.
4. Firmware SubBox dùng WsASR, không khởi tạo/build LocalKws/MFCC hoặc xử lý
   lại transcript. Cấu hình peer/room vẫn đồng bộ. Giữ pin/driver relay ActionBox;
   thu trọn câu thay vì gửi riêng từng từ.
5. Sao lưu nguồn Pi và app/NVS SubBox; build, kiểm tra đường truyền/ủy quyền,
   nạp app-only qua USB như người dùng đã yêu cầu và kiểm tra trên thiết bị.
6. Kiểm tra câu nói thật qua Pi, kết quả ACK và loa riêng với test mô phỏng;
   không train thêm và không tuyên bố nhận dạng đạt chỉ từ build/khởi động.

HIL đầu phát hiện rơi 5 gói PCM trong lúc vừa nhận ESP-NOW vừa truyền WSS. Giữ
fail-closed cho câu thiếu gói, tăng ưu tiên RX và retry giới hạn khi TX đầy.
SubBox ở chế độ Pi gom trọn câu tối đa 6 giây trong PSRAM rồi mới mở phiên
upload; không truyền Wi-Fi trong lúc nhận âm thanh radio. Đã bổ sung kiểm tra
đủ 80.000 mẫu/5 giây và không upload câu thiếu gói.

HIL pi3: Pi nhận đúng “bật đèn”, Core APPLIED, bo ghi Ch1 ON và loa xác nhận
đã phát đủ; người dùng xác nhận đèn bật và nghe phản hồi. Tiếng wake còn chậm
vì AUDIO_START chỉ tới sau onset VAD. Pi4 firmware gửi thêm gói WAKE 0x24 ngay
khi WakeNet nhận Hi ESP, chỉ phát chime trên SubBox, không mở phiên PCM/ASR;
khử trùng hai bản gửi và không chime lần nữa khi AUDIO_START. Kiểm tra trust,
độ dài, trigger và nguồn Core như các gói âm thanh khác.
