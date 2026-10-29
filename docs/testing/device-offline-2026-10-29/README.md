# Thiết bị báo ngoại tuyến — 2026-10-29

Đã khôi phục kết nối Pi và xác minh Gateway, SubBox 0B54, ActionBox DDF8 online
trên Firebase. DDF4/DDE8 vẫn offline; chưa xác minh kết nối phần cứng hai bo này.
Các quan sát dưới đây trước phần kết quả là bằng chứng trong lúc xảy ra lỗi.

- Pi trả ping và /api/health trên cả .29/.30; hai IP có cùng MAC quan sát được.
  Vì vậy không coi đổi IP là nguyên nhân đã được chứng minh.
- SubBox bắt Wi-Fi XIAOMI, kênh 11, RSSI -29 dBm. MQTTS tới port 8883 thất bại
  ở TLS; WSS nối được rồi đóng. Kiểm tra từ máy cũng nhận TLS reset/EOF ở 8883.
- SSH đóng kết nối trước banner ở cả hai IP, người dùng cũng tái hiện được.
- API /api/wifi/status và /api/wifi/scan đều trả lỗi khởi chạy nmcli:
  `[Errno 5] Input/output error: 'nmcli'`. Đây là dấu hiệu đọc dữ liệu hệ thống
  trên Pi bị lỗi. Có thể liên quan lưu trữ/nguồn, chưa có kernel log để kết luận.
- UDP discovery báo .30 và MQTT 1883, trong khi bo giữ broker TLS đã provision
  ở .29:8883. Chưa sửa discovery vì hai IP hiện cùng tới Pi và có lỗi hệ thống
  rõ hơn cần giải quyết trước.

Không nạp firmware, không đổi enrollment/binding/database và không gửi lệnh
relay. Cần console trực tiếp trên Pi để đọc log kernel/dịch vụ. Nếu không có
console, phải chuẩn bị đường truy cập hoặc sao lưu thẻ trước khi sửa filesystem;
không format hoặc tự ghi lại thẻ từ những bằng chứng hiện có.

[Thông tin đã lược bỏ bí mật](evidence.json). Log serial gốc giữ riêng trong
`App/HomeCompetition/build/offline-diagnosis-20261029/`, không đưa vào Git.

## Cập nhật từ console Pi

Ảnh console tiếp theo cho thấy `hostname -I` chỉ có `10.42.0.1` và ba địa chỉ
bridge `172.17/18/19.0.1`, không còn địa chỉ mạng nhà `192.168.11.x`.
`sudo systemctl restart ssh` đã trả lại prompt và không hiện lỗi trong ảnh.
Log cảnh báo có `mmc1: Controller never released inhibit bit(s).` và
`brcmf_scan_timeout: timer expired`; chưa đủ bằng chứng kết luận thẻ nhớ hỏng.
Địa chỉ `10.42.0.1` phù hợp với mạng shared/hotspot của NetworkManager và đường
fallback trong `Gateway/systemd/autohotspot.sh`, nhưng chưa đọc được profile
đang hoạt động trên Pi để xác nhận chế độ AP.

Máy tính vẫn ở `192.168.11.51/24`; SSH chưa truy cập được cả `.29`, `.30` và
`10.42.0.1`. Bước tiếp theo là nối Pi lại Wi-Fi nhà qua console trực tiếp, rồi
đọc trạng thái dịch vụ. Chưa đổi kết nối mạng máy tính hoặc cấu hình Pi từ xa.

## Kết quả sau khi Pi nối lại Wi-Fi

- Pi dùng profile `XIAOMI`; `wlan0` có cả `.29` và `.30`. SSH hoạt động lại.
- `/api/health` trả OK; `/api/wifi/status` chạy `nmcli` thành công.
- Broker thực tế là container `emqx_broker`, hoạt động; system service
  `mosquitto` không phải broker đang dùng. TLS 8883 và 8765 bắt tay thành công.
- MQTT có client SubBox và hai tiến trình Gateway. Core nhận nhịp sống mới từ
  SubBox 0B54 và ActionBox DDF8, khoảng 1–2 giây trước thời điểm đọc.
- Đọc trực tiếp Firebase xác nhận Gateway, 0B54 và DDF8 online; dữ liệu mới
  trong 1,3–1,6 giây. DDF4/DDE8 vẫn offline, chưa có `last_updated`.
- Root là `/dev/sda2`, ext4 read/write; `vcgencmd get_throttled` trả `0x0`.
  Chưa có bằng chứng kết luận ổ lưu trữ hỏng; không sửa filesystem.

Không nạp firmware, không sửa mã backend, không đổi dữ liệu đăng ký và không
thử relay/giọng nói trong lượt khôi phục mạng này. Chưa xác nhận lại màn hình app
trực tiếp; đã xác minh đường truyền dữ liệu thật tới Firebase.
