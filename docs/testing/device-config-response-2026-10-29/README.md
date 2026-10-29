# Cấu hình thiết bị, phản hồi trạng thái và lời đáp — 29/10/2026

Ngày báo cáo theo múi giờ Asia/Bangkok. Các mốc journal bên dưới là UTC
28/10/2026, tương ứng rạng sáng 29/10 tại máy người dùng.

## Thay đổi đã triển khai

- App release 1.3.3+23 đã cài trên điện thoại, giữ applicationId, chữ ký và dữ
  liệu đăng nhập. APK tại `releases/android/HomeCompetition.apk`; hash trong
  `releases/SHA256SUMS` và `evidence.json`.
- Tên gọi giọng nói mặc định theo tên thiết bị, giữ alias khi người dùng sửa
  riêng. App và Core lưu đủ năm loại thiết bị, tên và alias. Lưu có tiến trình,
  thông báo thành công và lỗi để thử lại, không đóng biểu mẫu khi lưu lỗi.
- ASR lấy tên/alias mới từ Core theo phạm vi nguồn micro; resolver ưu tiên
  tên/alias chính xác, kiểm tra revision và từ chối tên trùng. Không giảm ngưỡng
  confidence chung, không train hoặc thay model.
- Chạm bật/tắt hiển thị đang chờ ngay, chống đảo trạng thái bởi snapshot cũ,
  hoàn tác khi lỗi. Cầu Firebase đẩy theo state event; RPC đợi ACK trong cùng
  lượt để giảm vòng truyền. Trạng thái cuối vẫn cần ACK của bo.
- Pi đáp “Em đã bật/tắt <tên thiết bị>” chỉ sau APPLIED; pending/timeout/lỗi
  không được nói đã thực hiện. Có cache hai câu cà phê theo giọng Trúc Ly hiện
  hành. Gói command_result đánh dấu có TTS để không phát chime kết quả trùng.

## Kết quả kiểm tra

| Kiểm tra | Kết quả |
| --- | --- |
| Flutter analyze | Không có issue |
| Flutter tests | 175 đạt |
| Gateway tests sau sửa lời đáp | 483, đạt, 3 skip |
| Android arm64 release | Build/cài thành công, versionCode 23 |
| Tên nhập từ app | Cây nóng lạnh / Máy pha cà phê / Đèn chùm lưu ở DDF8 CH1/2/3 |
| Lệnh giọng nói cà phê | Chọn DDF8 CH2, APPLIED cho bật và tắt |
| Tên thiết bị khác | Lệnh bật Cây nóng lạnh và Đèn chùm có APPLIED đúng CH1/CH3 |
| Lời đáp mới | 17:54:38 ASR đúng; 17:54:39 APPLIED và đọc cache câu bật cà phê |
| Xác nhận loa | 17:54:40 SubBox xác nhận phát đủ 50240 byte; người dùng xác nhận OK |

Lượt lời đáp mới: `CMD-a7f077ef6341e2412a5993d8`, đích
`HC-28848533DDF8:CH2`, ON, APPLIED. Cache câu bật dài 1,57 giây ở PCM16 mono
16 kHz. Câu tắt được kiểm tra bằng regression và cache 51200 byte; không suy
diễn rằng hai chiều đều có bản ghi phát loa mới trong lượt này.

Lượt thao tác app trước đó ghi được ô “Đang bật…” trong ảnh chụp đầu ở 743 ms
sau khi bắt đầu thao tác ADB. ACK Core mất khoảng 0,6–0,9 giây từ lúc tạo lệnh;
một lượt tắt tính cả cloud khoảng 3,3 giây. Đây không phải phép đo render chính
xác, không phải cam kết mọi lệnh vật lý phản hồi dưới một giây. Ảnh điện thoại
không được đưa vào repo.

## Danh sách phòng tại thời điểm kiểm tra

Registry chỉ có `local-room` — Phòng ngủ, với SubBox 0B54 là primary.
DDE8/DDF8 online, DDF4 đăng ký nhưng offline; đều thuộc phòng này.
`ConnectedAddDeviceScreen` hiển thị toàn bộ `snapshot.rooms`, không lọc danh
sách phòng theo số SubBox. Sau khi chọn phòng, chỉ SubBox đã đăng ký trong
phòng đó mới là parent hợp lệ để ghép ActionBox.

Một lựa chọn Phòng ngủ hiện phù hợp dữ liệu, không phải lỗi dropdown. Cắm thêm
bo không tự tạo phòng. Luồng Firebase chưa cung cấp nút/API tạo phòng, dù Core
UI/API độc lập có chức năng đó; đây là phần thiết lập nhà còn thiếu. Trình tự
đúng là tạo phòng → đăng ký SubBox vào phòng → ghép ActionBox vào SubBox đó.
Không tự tạo phòng hoặc đổi gán phòng của người dùng trong lượt kiểm tra này.

## Sao lưu và giới hạn

Nguồn Gateway và SQLite được sao lưu kín trên Pi trước các lần triển khai.
Bản trước thay lời đáp ở `~/.local/state/device-config-response/` với tiền tố
`before-named-replies-20261028-175019`. Không khôi phục DB cũ vì có tên thiết bị
mới người dùng đã nhập. Hai file lời đáp live được kiểm tra SHA-256 trùng repo.
Chỉ restart Gateway để nạp Python, không nạp firmware mới trong lượt này.

Khi mở cổng theo dõi USB lúc chẩn đoán, cả ba bo đã reboot dù DTR/RTS tắt.
Không tính việc relay tắt do reboot là điều khiển giọng nói thành công. Lượt
không phản hồi ban đầu không có đủ log trước reboot để kết luận nguyên nhân;
sau đó các lệnh người dùng nói được đối chiếu ASR → command → ACK → phát loa.

APPLIED là `relay_reported`, không phải xác nhận bằng dòng điện/tải thật.
Chưa đánh giá nhận dạng dài hạn, tên gần âm, mạng chập chờn hoặc HIL đủ cả
năm loại. Không mở rộng sang quản lý phòng, hội thoại nối tiếp hay model mới.
