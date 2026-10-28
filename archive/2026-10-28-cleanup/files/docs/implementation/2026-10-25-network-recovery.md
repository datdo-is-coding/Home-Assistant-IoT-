# Khôi phục sau khi ngắt/bật lại Wi-Fi

## Chẩn đoán trên hệ thống đang chạy

Pi đã vào Wi-Fi XIAOMI và Gateway vẫn chạy, HTTP8000/WS8765/broker8883 đang lắng nghe. Registry vẫn báo SubBox và ActionBox offline. SubBox có kết nối WS tới Pi nhưng không có luồng telemetry mới.

Đọc USB bằng file descriptor, không đổi DTR/RTS và không khởi động lại bo: `PROVISION_STATUS` xác nhận đã có Wi-Fi và MQTT credentials. Cấu hình vận hành lại ghi `mqtt://192.168.11.30:1883`. Driver MQTT yêu cầu `mqtts://` và CA/tài khoản riêng nên từ chối URI này.

Nguyên nhân: discovery lấy `mqtt_port` (cổng kết nối nội bộ Gateway) khi beacon không khai báo `mqtt_tls_port`, rồi main ghi URI thường vào cấu hình SubBox. Có lỗi độc lập trong cùng luồng: sau 5 lần Wi-Fi thất bại, handler thử mở setup nhưng không tiếp tục STA reconnect; khi factory setup thiếu hoặc cửa sổ setup hết hạn có thể không tự hồi phục.

## Sửa

- Discovery không được thay broker bảo mật bằng URI thường. Nếu không quảng bá cổng TLS8883, giữ broker đã cấu hình.
- Khi đọc cấu hình cũ bị hạ thành `mqtt://`, khôi phục từ `subbox_sec.mqtt_uri` nếu đó là URI TLS hợp lệ. Không ghi đè enrollment đã có `mqtts://`.
- Tiếp tục reconnect tới Wi-Fi đã lưu, kể cả setup thất bại/đang hoạt động. Chỉ tự thử mở setup một lần ở lần mất kết nối thứ 5; có IP sẽ đặt lại bộ đếm.
- Không xóa Wi-Fi, credentials, peer, tên thiết bị hoặc registry Pi.

## Xác minh

- Hồi quy trước sửa: handler thật dừng reconnect; discovery đổi TLS sang plaintext; loadConfig trả URI hạ cấp. Cả ba kiểm thử thất bại đúng lỗi mong đợi.
- Sau sửa: 4 test SubBox và 1 test reset/storage host đạt; firmware SubBox build thành công; `git diff --check` sạch.
- Sao lưu NVS trước nạp: `/home/tuan/.codex/device-backups/20261025-network-recovery/288485350B54-nvs.bin` (chứa dữ liệu riêng, không đưa vào git).
- Nạp chỉ app0 tại 0x20000 trên SubBox 288485350B54; esptool xác nhận hash.
- SHA256 firmware: `f28d50f8f1a734ed601af23e0c52d5483caf0c89a7725ba4040f51981ee6fcf1`.
- Sau nạp: USB báo broker `mqtts://192.168.11.29:8883`; API có last_seen mới và online cho SB288485350B54, AB28848533DDE8, AB28848533DDF8, AB28848533DDF4. WS audio nối lại Pi.

Chưa chủ động ngắt router lần nữa, chưa kiểm thử chuyển sang nhà/IP/router mới. Beacon hiện dùng cấu hình TLS của MQTT client nội bộ để quảng bá cổng cho thiết bị; cần tách hai cấu hình này khi hoàn thiện discovery. Bản sửa bảo toàn broker TLS đã biết khi thiếu thông tin discovery đáng tin cậy, không xác nhận tự đổi IP trong mọi trường hợp. Chưa thử câu nói thật sau nạp.

## Âm thanh thực tế trên đường ActionBox → SubBox → Pi

> Cập nhật 25/10/2026: phần nhận dạng đã chuyển về SubBox. Các mô tả ASR trên Pi
> trong mục này là trạng thái trước thay đổi; xem
> [`2026-10-25-local-kws.md`](2026-10-25-local-kws.md). Pi hiện chỉ nhận kết quả có cấu
> trúc và phát TTS, không nhận PCM micro để nhận dạng lệnh.

- ActionBox nhận mic I2S, phát hiện Hi ESP bằng WakeNet cục bộ. Bắt đầu truyền khi wake-word hợp lệ hoặc phiên hỏi tiếp đã được cho phép.
- Định dạng gửi: raw PCM signed16, little-endian, một kênh, 16.000 mẫu/giây; không có header WAV, không nén MP3/Opus ở luồng hiện tại.
- ESP-NOW START (0x20): sample rate, số bit, số kênh, codec, nguồn kích hoạt, timestamp.
- ESP-NOW CHUNK (0x21): 1 byte loại + 1 byte seq + 2 byte độ dài + tối đa 240 byte PCM. Gói đang gửi 244 byte, chứa 120 mẫu = 7,5ms. Seq8bit quay vòng; đây không phải packet TCP.
- ESP-NOW END (0x22): số chunk và tổng byte PCM. START/END có gửi lặp để giảm khả năng mất mốc phiên; audio chunk không có cơ chế truyền lại cấp ứng dụng trong đoạn gửi hiện tại.
- SubBox gắn dữ liệu với bo nguồn, chọn phiên mic đang hoạt động và đệm PCM. `LocalKws`
  chạy MFCC/model ngay trên SubBox; PCM micro không còn gửi qua WebSocket tới Pi.
- Kết quả nhận dạng cuối câu được SubBox giải quyết và điều khiển ActionBox_V2 qua
  ESP-NOW. Pi nhận sự kiện kết quả có cấu trúc qua MQTT; không nhận transcript để hiểu
  lệnh và không gửi lại lệnh relay.
- Pi phát trả lời TTS về SubBox dưới dạng PCM để phát loa. MQTT mang lệnh/trạng thái/
  telemetry, không mang luồng PCM này.

Payload âm thanh thuần: 16.000 × 2 × 1 = 32.000 byte/s = 256kbit/s. Năm giây khoảng 160kB, chưa tính header và chi phí truyền radio/TCP.
