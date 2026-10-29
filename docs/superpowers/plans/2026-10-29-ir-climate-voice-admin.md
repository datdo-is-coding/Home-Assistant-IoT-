# IR đầy đủ, giọng nói và quản trị nhà

Giữ toàn bộ WIP, luồng ASR trên Pi và relay chốt SET/RESET 30 ms.

1. Học Bật, Tắt, từng nhiệt độ tuyệt đối; nhận dạng Panasonic 216-bit để sinh
   đầy đủ trạng thái khi đúng giao thức. Không đổi mã nút A75C4187 thành mã
   nhiệt độ tuyệt đối. Người dùng không có remote gốc, sẽ kiểm thử IR sau.
2. Cấu hình mắt thu theo phần cứng người dùng khai báo, mặc định tắt. Nối tên
   remote và phòng vào nhận dạng/phân giải giọng nói, dùng chung bộ phát có
   deadline/idempotency; phản hồi chỉ sau ACK phát, không giả trạng thái tải.
3. Quyền quản trị lấy từ vai trò nhà đã xác thực trên Pi. Cấp Owner cho tài
   khoản Google đã liên kết theo yêu cầu; không tạo mật khẩu dùng chung.
4. Nối thao tác quản trị qua Firebase tới Core, không gửi lệnh legacy cho bo
   đã enroll. Reset/xóa cần xác nhận, kiểm tra con đang ghép, deadline và ACK
   của firmware; giữ dữ liệu nhà máy/calibration, cho phép ghép lại sau reset.
5. Kiểm tra codec/voice/quyền/reset và giao diện, build, sao lưu trước nạp,
   đồng bộ Pi và cài app. Không tự xóa/reset bo đang dùng để chứng minh UI.

## Kết quả

Đã triển khai phần mềm, cài app 1.5.0+26, đồng bộ main/radio Pi và nạp USB
2.3.0-control1 cho 0B54/DDF4. Owner xác nhận trên app; reboot DDF4 qua Firebase
thành công và giữ enrollment. Học IR/điều hòa thật chờ phần cứng/remote theo yêu
cầu người dùng; DDF8 hoãn OTA. Không reset/xóa bo thật trong lượt này.
Xem [bằng chứng và hướng dẫn](../../testing/ir-climate-admin-2026-10-29/README.md).
