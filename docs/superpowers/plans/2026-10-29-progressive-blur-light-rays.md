# Progressive Blur + Light Rays

Giữ nguyên Firebase, quyền, ghép nối, IR, điều khiển và trạng thái đang chờ.
Giữ WIP hiện tại, APK/source trước sửa trong thư mục riêng /tmp.

- Nền tia sáng chéo có nguồn sáng thống nhất, màu kính bạc/xanh dịu cho cả sáng/tối.
  Vẽ tĩnh bằng CustomPainter, cô lập repaint; không thêm animation loop nền.
- Progressive blur thật ở mép và dock: các dải blur nhỏ tăng dần, không blur
  từng thẻ hoặc cả màn hình. Tôn trọng chế độ giảm hiệu ứng và tương phản cao.
- Dock nổi năm tab, vùng chạm tối thiểu 48, giữ semantics và trạng thái tab.
- Thẻ thiết bị, bộ lọc, số liệu và nhóm cài đặt dùng cùng hệ bề mặt trong nhẹ;
  chữ và số dễ đọc, không thêm dữ liệu mẫu hoặc thay nghĩa trạng thái thiết bị.
- Kiểm tra overflow/semantics/điều hướng, analyze, test và build release.
  Đo cuộn bằng fixture 120 kênh/5Hz trên điện thoại nếu kết nối còn sẵn;
  không dùng fixture để đóng relay và không đánh đổi dữ liệu app khi benchmark.
- Cài bản thật cuối, kiểm tra hình ảnh trên điện thoại, ghi rõ giới hạn đo.

## Kết quả triển khai

Đã thay hệ bề mặt và phân cấp chữ, nền tia sáng tĩnh và dock ba dải blur; mép trên
chỉ dùng fog gradient để giảm chi phí. 187 test app đạt và 12 kiểm tra/render
sau tối ưu đạt; xem [ảnh và kết quả](../../testing/progressive-blur-2026-10-29/README.md).
Bài đo không chứng minh 120 FPS cố định. Sự cố Flutter tự gỡ APK khi gặp bản
trên máy cao hơn đã được thông báo; người dùng không yêu cầu khôi phục app cũ.
Các lượt cài sau kiểm tra version và dùng ADB -r, không tự gỡ.

Bản release 1.6.0+41 đã cài và mở trên điện thoại, không có lỗi khởi động;
người dùng đã đăng nhập Google lại, dữ liệu thật và năm tab đã kiểm tra.
Đã sửa khoảng đệm trên dock bị lặp bởi SafeArea của NavigationBar, test với
inset màn hình thật đạt; cài cập nhật cuối giữ phiên vừa đăng nhập.

Bảng điều khiển và các sheet trong tab đã chuyển lên navigator gốc, giữ đúng
đường đóng/mở Cài đặt; thêm kính mờ và xử lý chữ tràn màn nhỏ.
