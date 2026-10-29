# Giao diện ánh sáng và SubBox IR — 29/10/2026

App **1.4.0+25** đã cài trên điện thoại, cùng chữ ký và dữ liệu đăng nhập.
SubBox **0B54** đã nạp USB **2.2.0-ir1**, Pi đã cập nhật và kết nối lại WSS.
Không nạp lại ActionBox, không thay driver relay SET/RESET 30 ms.

## Kết quả thực tế

- Tab Thiết bị có nút Remote hồng ngoại; biểu mẫu thực lấy SubBox Phòng ngủ
  và catalog từ Firebase RPC. Lượt thử đi qua app → Firebase → Pi → WSS →
  SubBox. Hai lượt CWA75C4179/A75C4187 có ACK phát và trạng thái SENT; riêng
  **A75C4187** được người dùng xác nhận “Có phản ứng đúng”. Sau xác nhận mới
  đánh dấu và lưu “Điều hòa Panasonic”; hàng cấu hình đã có trong SQLite,
  màn điều khiển mở thành công, database integrity_check/quick_check đều ok.
- Bo hiện chỉ có LED phát. Firmware quảng bá TX/RX riêng, RX bị tắt và nút
  học remote bị khóa trên app. Chưa kiểm thử thu IR vật lý.
- Nút Nguồn của A75C4187 là khung ghi sẵn. Không hiện thanh nhiệt độ tùy ý
  cho bộ này vì chưa có codec phù hợp. Không suy diễn các bản ghi Tmp_UP/DN
  thành lệnh tăng/giảm tương đối. Ba bộ Panasonic 216-bit khác có codec
  nhiệt độ/mode/quạt/đảo gió nhưng chưa được xác nhận phù hợp điều hòa này.
- Màn Nhà/Thiết bị giữ chữ gọn, tên nhà xanh/cam và chấm online. Thêm viền
  bắt sáng, glow khi bật, nền ambient tĩnh và nghiêng khi chạm. Chỉ thanh
  điều hướng có BackdropFilter; không blur từng thẻ hoặc chạy ticker nền.
  Đã xem giao diện thật trên điện thoại ở chế độ tối. Ảnh có lớp nổi cá nhân
  được giữ trong /tmp, không đưa vào repo.

## Kiểm tra phần mềm

- Flutter analyze: không issue; **181 test app đạt**, gồm save cần thử + xác
  nhận người dùng, RX thiếu thì không học, sửa nhiệt độ chỉ là bản nháp.
- **490 test Gateway đạt, 3 skip có sẵn**; kiểm tra codec/checksum, giới hạn
  waveform, quyền, chống gửi lặp, thiếu receiver, nonce lỗi, socket sai và
  IR chậm không chặn vòng điều khiển. Một lượt toàn bộ trước đó có race dọn
  thư mục ở test presence cũ; chạy lại toàn bộ đạt, không sửa logic presence.
- **39 test firmware đạt**, gồm biên dạng IR và biên dịch WsASR thật với
  kiểm tra gói JSON phân mảnh/khóa gửi/nhận. Lượt đầu dùng Python thiếu gói
  NVS/numpy; chạy lại với SDK Python và numpy sẵn có đạt.
- ESP-IDF 6.0.2 build đạt, image 1,208,928 byte. Flash chỉ ota_0 0x20000,
  esptool xác nhận hash đã ghi khớp. Bản flash 16 MB trước sửa đã readback/
  verify digest; otadata CRC hợp lệ, seq=1/state=VALID. Giữ bootloader/NVS/
  otadata và phân vùng còn lại. WSS Pi voice relay đăng ký lại thành công.
- Android không có lỗi flutter/AndroidRuntime trong log sau cài và thử IR.
- Lượt tiếp tục sau khi môi trường khởi động lại: chạy lại **490 test Gateway
  đạt, 3 skip**, bổ sung thời điểm hoàn tất cho phản hồi IR để cơ chế dọn hộp
  thư Firebase hoạt động. Đã đồng bộ bản cuối lên Pi sau sao lưu. Điện thoại
  không còn xuất hiện trong ADB ở lượt này; không cài/nạp lại ngoài lượt đã
  xác nhận ở trên.

## Giới hạn và khôi phục

SENT chỉ xác nhận firmware hoàn tất phát, không phải phản hồi từ điều hòa.
Lệnh dùng nonce/deadline monotonic, xác thực WSS, idempotency bền và không
gửi lại khi không biết ACK. Không hàng đợi phát khi offline. Catalog nhỏ
CC0 có nguồn/hash từng file; không đại diện mọi remote A75C hay kho Xiaomi.
IR hiện điều khiển bằng app, chưa nối vào phân giải lệnh giọng nói.

Chưa đo carrier bằng máy hiện sóng, chưa đo FPS Flutter liên tục, chưa thử
IR trong đồng thời phát TTS dài và chưa build iOS. Không dùng bài này làm
bằng chứng điều khiển tải điện hoặc nhiệt độ điều hòa tuyệt đối.

Backup flash chứa dữ liệu nhạy cảm, giữ riêng tại
`/home/tuan/.codex/device-backups/20261029-flagship-ir/` (600).
Backup database/mã Pi giữ tại
`/home/pi4/.local/state/flagship-ir/before-20261028-200817/` (thời gian UTC).
Backup trước sửa bản dọn hộp thư giữ tại
`/home/pi4/.local/state/flagship-ir/mailbox-final-20261029-023619/`.
Thư mục tạm `/tmp/homecompetition-flagship-ir-20261029/` của phiên trước đã
được dọn khi môi trường khởi động lại; bản flash và backup Pi nêu trên vẫn
còn và checksum flash đã được kiểm lại. Không dựa vào /tmp để khôi phục.
Không cần khôi phục database để gỡ bản code; tránh làm mất cấu hình mới của
người dùng. Image USB mới và APK nằm trong `releases/`, SHA trong SHA256SUMS.
