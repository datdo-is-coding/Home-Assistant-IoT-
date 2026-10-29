# Không hủy câu khi chạm giới hạn VAD — 28/10/2026

Đã sửa và nạp **SubBox 0B54, 2.0.4-b2 qua USB**. Log bo xác nhận phiên bản,
LocalKws ready, WSS/MQTT kết nối lại. Nghe giọng thật không còn hủy sớm ở giới
hạn cửa sổ; nhận đủ nội dung lệnh vẫn chưa đạt.

## Lỗi và thay đổi

Ở b1, đoạn năng lượng liên tục vượt 1 giây làm LocalKws.feedAudio trả false;
AudioManager hủy session và phát phản hồi dù ActionBox còn đang gửi PCM.
Log người dùng: hủy ở 21.488 s, tới 25.398 s mới nhận STREAM_END. Đây là giới
hạn đoạn được triển khai sai, không phải bằng chứng model lỗi hoặc thiếu RAM.

b2 chốt suy luận khi cửa sổ đầy rồi tiếp tục nhận âm thanh, giống cơ chế giới
hạn cửa sổ của KWS cũ. Khoảng ngắt 100 ms vẫn tách/đệm từ ngắn; final chỉ xuất
ở STREAM_END. Ngưỡng 0,75, model/MFCC, kiểm tra xung đột và kiểm tra PCM/model
lỗi được giữ nguyên. Thêm log KWS_VAD_LIMIT/KWS_RESULT để phân biệt giới hạn
cửa sổ với lỗi model; không ghi PCM hay huấn luyện.

37 bài regression qua; 16 ca VAD qua AddressSanitizer/UBSan. Ca mới tái hiện
lỗi với PCM liên tục 2,5/4,5 giây: không hủy phiên, chưa có final trước stop.
Đây là kiểm tra luồng với model stub; WAV/model thật có bài regression riêng.

## Nạp và kiểm tra bo

- Xác minh MAC, sao lưu đủ 16 MiB ngoài repo và đối chiếu digest flash.
- Giải mã CRC/sequence otadata: slot đang chạy ota_0 tại 0x20000, state VALID.
- Chỉ ghi app 1.197.920 byte vào 0x20000, xác minh ghi khớp. Đọc lại vùng
  0–0x20000 trước khi boot, byte khớp bản sao lưu: bootloader/NVS/otadata
  không đổi. Bảng phân vùng build cũng khớp bảng trên bo.
- SHA-256 app: `d3eb02b06f8e52c308148e76b9c4bb5997248785134fc0e64c97c25293c5e53f`.
- Boot USB in `App version: 2.0.4-b2`, LocalKws ready; SRAM lúc idle 11–14 KiB.
  Chín lượt suy luận quan sát được mất khoảng 141–161 ms, không có log lỗi
  KWS buffer/model. KWS revision 4 đã đồng bộ theo boot mới.

Phiên nói thực tế đầy đủ trong [log đã lọc](device-log.txt):

| Mốc | Thời gian trên bo |
| --- | --- |
| STREAM_START | 52.997 s |
| STREAM_END | 58.287 s |
| Final “đèn” | 58.437 s — sau END 150 ms |
| Loa bắt đầu phản hồi | 58.627 s — sau END 340 ms |

Gateway báo `incomplete_command`, không tạo lệnh relay; ba kênh DDE8 vẫn OFF.
Trường firmware cache trong Gateway còn b1 do chỉ cập nhật từ OTA_RESULT;
phiên bản thực b2 được xác nhận từ USB và hash ghi, không sửa cache để giả
thành xác nhận OTA.

## Giới hạn

Đã xác nhận sửa lỗi kết thúc sớm, chưa xác nhận nhận đúng cả câu: phiên trên
chỉ nhận “đèn”; nhiều đoạn vẫn phải chốt theo giới hạn 1 giây thay vì VAD
phát hiện khoảng ngắt. Chưa có nhãn câu người dùng xác nhận cho các lượt này.
Sai lệch MFCC đã ghi ở audit trước vẫn còn; không thay đổi trong bản sửa này.

Xem [metadata USB](usb-installation.json), [Gateway sau nạp](gateway-after-usb.json),
[regression](firmware-regression.log) và [sanitizer](sanitizers.json).
