# Thiết bị báo ngoại tuyến — 2026-10-29

Đang chẩn đoán, chưa sửa xong. App kết nối Firebase và đọc được cấu hình, nhưng
luồng nhịp sống thực từ các Box không được duy trì. Không đổi UI để giả online.

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
