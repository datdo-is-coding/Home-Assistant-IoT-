# SubBox: VAD từng từ, đệm giữa — 2026-10-28

- Giữ model, MFCC, ngưỡng nhận 0,75 và giao diện ASREngine hiện tại. Không train,
  đổi ActionBox/GPIO hay nạp bo trong lượt sửa nguồn này.
- Thay cửa sổ trượt trong LocalKws bằng VAD lát 50 ms giống firmware KWS cũ;
  ngưỡng RMS có hysteresis và noise floor học từ các lát nền.
- Preroll 100 ms chỉ chứa mẫu trước onset; mỗi mẫu thu vào đúng một lần.
  Ngắt từ sau 100 ms im lặng; tối thiểu 100 ms tiếng nói thật, không tính
  preroll hoặc im lặng. Hỗ trợ từ ngắn 100/200 ms theo yêu cầu.
- Đoạn từ dài tối đa 1 giây, cộng tối đa 100 ms preroll và 100 ms đuôi.
  Khi tiếng nói vượt 800 ms chỉ thu hẹp hai phần ngữ cảnh, giữ đủ phần tiếng
  nói vừa cửa sổ model. Khi chạm 1 giây thì suy luận cửa sổ đó và tiếp tục
  nhận PCM; chỉ STREAM_END mới kết thúc câu. Không coi giới hạn cửa sổ là lỗi.
  Lý do khác giới hạn 800 ms cũ: WAV regression có nền kéo dài gần 1 giây;
  không nên cắt tiếng nói để giữ ngữ cảnh. Buffer tối đa 1,2 giây trong PSRAM.
- Đệm zero hai bên thành 16.000 mẫu trước MFCC/model; giữ tên nguồn và chỉ
  phát kết quả cuối khi stream kết thúc. Cancel/lỗi không phân loại đuôi.
- Kiểm tra bằng PCM tổng hợp (vị trí/padding, lặp onset, min/max, ranh giới
  packet, stop/cancel), fixture WAV hiện có, regression firmware và build IDF.
- Sai lệch floor MFCC trong audit là việc riêng, được giữ nguyên để không
  trộn thay đổi MFCC với thay đổi VAD; chưa khẳng định đạt nhận câu trên bo.

Sau khi người dùng yêu cầu “nạp code”: đã nạp SubBox `0B54` qua OTA có chữ ký,
`2.0.4-b1`, counter 7, job `OTA-9854d6202ef747a496f425e4` SUCCEEDED. Đối chiếu
hash/boot/kết nối và cấu hình KWS revision 4; chưa kiểm thử câu nói thật.
Xem [bằng chứng nạp](../../testing/subbox-word-vad-2026-10-28/ota-installation.json).

Sửa tiếp theo log thật của người dùng: b1 hủy phiên trước khi nói hết vì giới
hạn đoạn 1 giây. b2 đã bỏ hủy theo độ dài, giữ kiểm tra PCM/model lỗi; nạp app-only
qua USB theo yêu cầu. Phiên nói thật xác nhận final/loa sau STREAM_END, nhưng
chưa nhận đủ lệnh. [Báo cáo b2](../../testing/subbox-vad-no-early-stop-2026-10-28/README.md).
