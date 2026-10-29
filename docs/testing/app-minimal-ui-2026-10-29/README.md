# HomeCompetition — giao diện tối giản 29/10/2026

## Thay đổi

- Giữ năm tab đang có: Nhà, Thiết bị, Điện năng, Kịch bản, Cài đặt.
- Bỏ thanh Firebase lớn. Tên nhà xanh khi kết nối và không có lỗi, cam khi
  mất kết nối hoặc có lỗi. Chạm tên nhà xem thông tin và thử lại khi cần.
- Thẻ thiết bị/bộ điều khiển có chấm xanh khi online, xám khi offline.
  Chấm kết nối độc lập với bật/tắt relay; có nhãn hỗ trợ đọc màn hình.
- Bớt mô tả, kênh kỹ thuật và nhãn trạng thái lặp trên thẻ. Giữ tên, phòng,
  công tắc, trạng thái chờ lệnh và công suất khi có. Màn chi tiết giữ số đo.
- Màn Nhà tập trung vào điều khiển; phần bộ điều khiển nằm trong mục thu gọn
  ở tab Thiết bị. Kịch bản bỏ mô tả lặp; Cài đặt gom nhóm và ẩn phần nâng cao.
- Điện năng dùng số và thanh tỷ trọng. Vẫn giữ A/kWh từng thiết bị, phạm vi
  số đo và giá trị chưa biết; không đổi thiếu dữ liệu thành số 0. Giải thích
  cách tính, tích lũy và hạn chế lịch sử được đưa vào nút thông tin.
- Bề mặt phẳng, viền mảnh, bớt bóng/gradient; sửa màu icon tab được chọn để
  đủ tương phản trong cả hai chế độ màu. Không thêm dependency.

## Kiểm tra

Flutter analyze không có issue; bộ đầy đủ **178 test đạt**. Sau tinh chỉnh
cuối phần gợi ý Kịch bản, cả **7 test điều hướng** tiếp tục đạt.
Bao gồm hồi quy cuộn không dựng lại thẻ không đổi, phản hồi chạm, cấu hình/
alias, startup offline, tên nhà đổi màu/lỗi/phục hồi, chấm online không đổi
khi relay tắt, công tắc không kích điều hướng và chữ lớn 1,6 lần ở màn hẹp.

Một lượt chạy đồng thời có bài alias cũ báo thất bại mà không in chi tiết.
Chạy riêng bài đó và chạy lại toàn bộ với reporter expanded đều đạt; không
thay logic alias hoặc Gateway trong lượt UI này.

Đã cài APK release Android arm64 **1.3.4+24**, giữ chữ ký, dữ liệu và đăng nhập.
Đã mở đủ năm tab trên điện thoại; kiểm tra thêm màn Nhà ở chế độ sáng và trả
về chế độ tối ban đầu. Quan sát trực tiếp chữ/tên dài, chấm trạng thái, tương
phản icon tab và bố cục số đo. Lớp nổi của ứng dụng khác che một phần màn hình; ảnh chụp
được giữ riêng trong thư mục tạm, không đưa vào repo.

Cấu hình 120 Hz và cấu trúc thẻ độc lập khi cuộn được giữ. Chưa đo FPS liên
tục, chưa gây mất mạng thật trên điện thoại và chưa kiểm thử iOS.
Không dùng lần kiểm tra UI này làm bằng chứng điều khiển tải điện thật.

APK tại `releases/android/HomeCompetition.apk`; SHA-256 trong
`releases/SHA256SUMS`. Bản trước và nguồn trước sửa được giữ ở
`/tmp/homecompetition-minimal-ui-20261029/` để đối chiếu/khôi phục trong phiên.
