# Giao diện có chiều sâu và remote hồng ngoại SubBox

Giữ thay đổi hiện có, không train model, không đổi quyền GPIO của ActionBox.

1. Khôi phục chiều sâu/ánh sáng bằng primitive đang dùng; nền sáng khuếch tán,
   viền bắt sáng và kính ở thanh điều hướng. Giữ chữ gọn, trạng thái xanh/cam,
   chấm online độc lập với bật/tắt, giới hạn blur để bảo vệ cuộn 120 Hz.
2. Thêm remote qua Firebase RPC hiện hữu, cùng nhà/phòng của SubBox. Lưu
   cấu hình, catalog có nguồn/giấy phép, lịch sử phát và khóa chống gửi lặp.
   Chỉ báo đã phát IR sau xác nhận của SubBox, không giả trạng thái thiết bị.
3. Dùng RMT của ESP-IDF cho IR_TX GPIO40 và IR_RX GPIO39 theo PCB V2.
   Công việc chạy tách khỏi audio, có giới hạn kích thước/tần số/thời gian,
   hết hạn và không phát lại lệnh cũ sau reconnect/restart.
4. App chọn SubBox → loại → hãng/model → thử → xác nhận → lưu; có đường học
   remote gốc cho mẫu chưa khớp. Ưu tiên Panasonic điều hòa nội địa Nhật;
   khung điều hòa chứa trạng thái nên không giả nút nhiệt độ là mã tăng/giảm
   dùng chung. Người dùng xác nhận prototype chỉ có LED phát; khóa RX/học.
   A75C4187 đã thử, được người dùng xác nhận phản ứng và lưu vào nhà.
5. Kiểm tra codec, phân quyền, idempotency/timeout, giao diện và build firmware.
   Sao lưu bo thật trước khi nạp; phân biệt phát GPIO/IR với thiết bị thật
   phản ứng. Không đưa remote vào trạng thái đã kiểm chứng nếu thiếu thử thật.

Đã triển khai app 1.4.0+25, Gateway và SubBox 2.2.0-ir1 qua USB; backup flash
16 MB đã đối chiếu digest trước khi chỉ ghi app. Kết quả và giới hạn:
[flagship-ir-2026-10-29](../../testing/flagship-ir-2026-10-29/README.md).
