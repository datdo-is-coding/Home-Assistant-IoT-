# Sửa cấu hình thiết bị, giọng nói và phản hồi trạng thái

Theo yêu cầu: giữ UI/120 Hz đang mượt; sửa đúng đường Firebase/Core hiện có.

1. App gửi đúng năm loại, lưu alias; alias tự theo tên cho tới khi người dùng
   sửa riêng. Form có validation, tiến trình lưu, báo lỗi và báo thành công.
2. Core lưu alias trong metadata hiện có, chiếu về app; đổi tên/loại/alias
   tăng revision, không giữ lệnh đang chờ theo cấu hình cũ.
3. Voice đọc tên/alias Core trong phạm vi phòng/SubBox mỗi phiên. ASR nhận
   vocabulary tương ứng và không phạt tên tải mới chỉ vì ngoài keyword cũ.
   Giữ chặn âm nhỏ, câu mơ hồ, nguồn/quyền sai và ACK trước thành công.
4. App cập nhật yêu cầu bật/tắt ngay, phân biệt trạng thái đang gửi với ACK;
   tuần tự hóa từng kênh, bỏ overlay khi lỗi/session đổi. Đẩy trạng thái Core
   khi có sự kiện thay vì đợi heartbeat 3 giây, giảm vòng RPC chờ ACK.
5. Test các luồng đổi tên/loại/alias, bỏ tên cũ, thêm bo, trùng tên, lỗi lưu,
   thay đổi mặc định alias, overlay tức thời/rollback và ACK. Build release,
   backup Pi, triển khai và cài điện thoại nếu kết nối. Không train, không
   đụng pin/driver/firmware relay và không reset dữ liệu người dùng.
