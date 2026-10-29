# SubBox dùng VAD từng từ — 28/10/2026

**Bản b1 dưới đây đã được thay bằng b2:** log nói thật phát hiện giới hạn 1 giây
hủy cả câu quá sớm. [Bản sửa và nạp USB](../subbox-vad-no-early-stop-2026-10-28/README.md).

Đã thay cửa sổ trượt 250 ms bằng VAD tách từ, đệm giữa 1 giây rồi chạy model
một lần cho mỗi đoạn hợp lệ. Đã nạp OTA `2.0.4-b1` lên SubBox `HC-288485350B54`
theo yêu cầu tiếp theo của người dùng.
Không train hoặc thu thêm dữ liệu. Model, MFCC, nhãn và ngưỡng nhận 0,75 giữ nguyên.

## Luồng xử lý

ActionBox vẫn chạy WakeNet và chuyển PCM 16 kHz sang SubBox. VAD mới nằm trong
`LocalKws`, không phụ thuộc VAD 1.500 ms của AudioManager. Pi4 tiếp tục phản hồi
từ kết quả điều khiển; ActionBox tiếp tục giữ toàn quyền GPIO/relay.

- Gom đủ lát 50 ms, độc lập kích thước packet PCM.
- Ngưỡng mở = `noise_rms × 2,2 + 0,006`, ngưỡng im lặng = `noise_rms × 1,3 + 0,002`.
  Nền khởi tạo 0,005; chỉ cập nhật từ các lát dưới ngưỡng mở khi đang chờ từ.
- Preroll 100 ms chỉ giữ mẫu trước onset. Không chép lại lát onset như code cũ.
- Tối thiểu 100 ms các lát có năng lượng đạt ngưỡng tiếng nói; preroll và
  im lặng cuối không được tính để vượt mức tối thiểu. Một xung 50 ms bị loại.
- Sau 100 ms im lặng thì kết thúc từ. Đệm zero hai bên tới đúng 16.000 mẫu.
  Nếu STREAM_END tới sớm, bổ sung phần đuôi zero còn thiếu, xử lý cả lát lẻ.
- Khi đoạn tiếng nói dài 800–1.000 ms, thu hẹp preroll/đuôi đối xứng để giữ
  toàn bộ tiếng nói trong cửa sổ. Quá 1 giây liên tục thì hủy cả stream,
  không suy luận một đoạn bị cắt. Buffer tối đa 1,2 giây, ưu tiên PSRAM;
  tổng bộ đệm tăng 16.000 byte so với bản cửa sổ trượt.
- Chỉ phát final khi stream kết thúc. Mất gói, timeout, cancel hoặc lỗi
  phân đoạn/model không được biến các từ đã nhận thành lệnh thiếu. Xung đột
  bật/tắt, đèn/quạt, phòng vẫn bị KwsCommand loại như trước.

Khác giới hạn 800 ms trong firmware cũ: các WAV regression có nền kéo dài
gần 1 giây. Cho phép tiếng nói vừa đủ cửa sổ 1 giây và bỏ bớt ngữ cảnh tránh
loại hoặc cắt từ chỉ để giữ preroll. Không hạ ngưỡng confidence để qua test.

## Bằng chứng trên máy

`Firmware/tests/test_kws_word_vad.py` biên dịch LocalKws thật, chỉ thay ranh giới
MFCC/model để quan sát chính xác đầu vào và kiểm tra vòng đời. 15 ca đều qua,
kể cả khi chạy AddressSanitizer + UndefinedBehaviorSanitizer:

| Đầu vào tiếng nói tổng hợp | Vị trí mẫu tiếng nói trong cửa sổ 1 giây |
| --- | --- |
| 100 ms | 450–550 ms; không lặp onset |
| 200 ms | 400–600 ms; đúng một lần suy luận |
| 125 ms, kết thúc ngay, packet 7 mẫu | 437,5–562,5 ms; không mất lát lẻ |
| 1.000 ms, kết thúc ngay | 0–1.000 ms; bỏ ngữ cảnh, giữ đủ tiếng nói |

Các ca khác: xung 50 ms không chạy model; khoảng ngắt 50 ms không tách từ;
100 ms tách hai từ; nền nhỏ không chạy model; packet 1/7/120/160/480/4.000
mẫu cho cửa sổ giống nhau; cancel/restart không rò mẫu; đoạn 1.050 ms hủy
stream; model trả NaN hoặc PCM null bị từ chối; lỗi khởi tạo MFCC không cho
start; lỗi sau khi đã nhận “bật đèn” không trả cụm này thành final.

Bộ regression firmware: **37 test qua**. Trong đó LocalKws + MFCC + model thật
nhận “bật đèn phòng ngủ” từ bốn WAV có sẵn và chỉ xuất final ở cuối stream.
Model cũng qua bài kiểm tra 355 vector MFCC có sẵn; kiểm tra transport,
nguồn/phòng, relay, audio playback, provisioning và OTA hiện có đều qua.
Các test trên máy không kích relay thật. Xem [log](firmware-regression.log)
và [kết quả sanitizer](sanitizers.json).

Build ESP-IDF thành công: app 1.197.456 byte, còn 61% phân vùng OTA.
SHA-256: `be98ea9efd33876fef7e0b341da754d22898c14b069e6a94c58f5e1e1a8475c9`.
Chi tiết phiên bản, hash nguồn/build và kết quả: [results.json](results.json).

## Nạp thực tế

- Gói ký counter 7; job `OTA-9854d6202ef747a496f425e4` **SUCCEEDED**.
  Bo báo version/hash đang chạy khớp bản build, boot ID mới và ONLINE.
- Sau hơn 87 giây kể từ xác nhận thành công, boot ID vẫn giữ nguyên,
  heartbeat mới 1,263 giây. Gateway và dịch vụ OTA đều active.
- Cấu hình KWS giống bản sao lưu, revision 4; đã đồng bộ với boot mới.
  Ba relay DDE8 đều báo OFF, `ct_valid=1`, `fault_flags=0`.
  Lượt này chỉ đọc trạng thái, không gửi lệnh đóng/cắt relay.
- Gói `2.0.3-b1` cũ đã đối chiếu hash; snapshot database và gói cũ được giữ
  trong thư mục riêng trên Pi. Không sao chép khóa/database riêng vào Git.

Xem [trước nạp](ota-preflight.json), [manifest đã ký](ota-target-manifest.json)
và [xác nhận sau nạp](ota-installation.json). Bằng chứng này xác nhận cài/boot,
không thay thế kiểm tra nhận câu nói thật.

## Giới hạn nghiệm thu

Đã nạp/kiểm tra boot và kết nối. Chưa đo latency suy luận, RAM khi có audio,
mất gói và nói thật trên bo ở lượt sửa này.
Đây là VAD năng lượng theo firmware KWS cũ; nền nhiễu lớn hoặc câu nói liền
không có khoảng ngắt 100 ms vẫn có thể bị gom thành một đoạn và bị từ chối.
Giữ nguyên ngưỡng ban đầu theo firmware cũ, cần đo với micro thật để xác nhận.

Sai lệch floor log-Mel giữa firmware và training nêu trong
[audit trước](../kws-pipeline-audit-2026-10-28/README.md) vẫn còn. Test MFCC hiện có
so sánh với reference dùng floor firmware; nó không chứng minh parity với
training. Lượt sửa này chỉ đổi VAD/padding, không xác nhận model đã đạt nhận
dạng câu/âm ngoài từ vựng trên thiết bị thực tế.
