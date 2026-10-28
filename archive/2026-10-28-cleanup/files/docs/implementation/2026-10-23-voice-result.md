# Sửa wake-word và phản hồi giọng nói — 23/10/2026

## Luồng được giữ nguyên theo yêu cầu mới nhất

ActionBox V2 phát hiện “Hi ESP”, thu PCM 16 kHz → ESP-NOW → SubBox →
WebSocket → Pi nhận dạng tiếng Việt và xử lý lệnh → PCM về loa SubBox.
Không chuyển xử lý lệnh sang ESP32. Không đổi cấu trúc đăng ký thiết bị.

## Nguyên nhân và bản sửa

1. Nhận dạng từ khóa thử nghiệm chạy đồng bộ trong luồng thu microphone.
   Đo trên bo DDF8: mỗi lượt tốn tối đa 262 ms, vượt dung lượng thời gian của
   bộ đệm DMA 90 ms. Một lượng mẫu tương đương 3 giây phải mất khoảng 5,18 giây
   mới xử lý xong. Bỏ việc khởi tạo/chạy KWS quan sát khỏi `voice_capture.cpp`;
   model và mã KWS vẫn còn để thử nghiệm riêng. Sau sửa, cùng lượng mẫu được
   xử lý đều mỗi 3 giây. Cả hai bo đã phát hiện wake-word thật.
2. Pi từ chối nguồn AB trên kết nối đứng tên SB. `audio_server.py` giữ danh tính
   kết nối SubBox và nguồn microphone ActionBox riêng. Chỉ chấp nhận nguồn đang
   online, đã thuộc đúng SubBox và không nằm trong danh sách pending; kiểm tra
   lại liên kết/owner epoch trước khi xử lý câu. Vẫn giữ kiểm tra token, epoch
   của kết nối và từ chối ACK giả danh. Phản hồi đi về loa SubBox của kết nối.
3. Một số nhánh phản hồi hủy lệnh/không hiểu/hỏi bổ sung trả WAV nhưng bị coi
   là PCM. Đổi các nhánh đó sang `synthesize_pcm`, dùng đường chuyển đổi 16 kHz
   mono có sẵn. Lần đầu tạo giọng từng tốn 13,38 giây vì nạp model; Gateway nay
   nạp model VieNeu trước khi mở dịch vụ nghe.
4. Cấu hình giọng đã lưu bị giá trị mặc định ghi đè khi khởi động. Đưa các giá
   trị mặc định TTS lên trước phần đọc `local_config.json`. Theo lựa chọn của
   người dùng, Pi dùng VieNeu v3nano / Trúc Ly, giữ tốc độ và cấu hình khác
   đang dùng. Đã tạo sẵn PCM cho câu không hiểu và câu hủy lệnh.

## Kiểm chứng

- Gateway: 274 bài chạy, 267 đạt, 7 bỏ qua.
- Trên Pi: 17 bài audio relay và 1 bài lưu lựa chọn giọng đạt.
- Firmware: kiểm thử chạy vòng thu âm thật với I2S/WakeNet giả lập đạt; không
  phát âm thanh trước wake-word, không chạy KWS nền, phát START/PCM/END sau wake.
  Kiểm thử SubBox chuyển nguyên PCM và không thực thi transcript tại bo đạt.
- Build ActionBox đạt; nạp app ở 0x20000 lên DDF8 và DDE8, hash được xác minh.
  NVS, model, bảng phân vùng và bootloader được giữ nguyên.
- Thử thật: cả hai bo nhận “Hi ESP”; Pi nhận đúng “xin chào”. Lượt sau sửa
  ghi nhận ASR 0,39 giây; phản hồi PCM bắt đầu trong khoảng một giây sau hết
  câu (một mẫu thử, không phải benchmark p95).
- Người dùng xác nhận loa đọc “Chưa rõ khẩu lệnh. Bạn muốn điều khiển thiết bị
  nào?”. Đây là phản hồi của chế độ điều khiển nhà cho câu chào, không phải
  lỗi mất kết nối. Người dùng muốn giọng bớt trầm và đã chọn Trúc Ly.

## Phạm vi chưa kiểm chứng

Chưa đo tỷ lệ đánh thức sai/bỏ sót ở xa hoặc trong tiếng TV; chưa kiểm thử tải
nhiều phòng dài hạn. Chưa xác nhận bằng thao tác thực tế một lệnh đóng/cắt tải
trong lần sửa giọng nói này. Luồng đó được kiểm tra bằng các bài regression.
Chất lượng giọng Trúc Ly vẫn cần người dùng nghe và đánh giá.

Khởi động Gateway lâu thêm thời gian nạp model TTS; câu chưa có cache vẫn cần
thời gian tổng hợp. Không coi một lần thử thành công là chuẩn thương mại.

## File và khôi phục

- Firmware: `Firmware/firmware_esp/ActionBox_V2/src/audio/voice_capture.cpp`.
- Pi: `Gateway/gateway/audio_server.py`, `main.py`, `config.py`.
- Test: `Firmware/tests/test_voice_capture.py`, `Gateway/tests/test_audio_relay.py`,
  `Gateway/tests/test_voice_settings.py`.
- Bằng chứng: `docs/audit-evidence-2026-10-23-voice/`.
- Bản firmware trước sửa: `before-voice.bin` trong thư mục bằng chứng.
- Mã nguồn Pi trước sửa có hậu tố `.before-voice-20261023`; cấu hình giọng cũng
  được sao lưu riêng. Không đưa file cấu hình chứa thông tin riêng vào báo cáo.
