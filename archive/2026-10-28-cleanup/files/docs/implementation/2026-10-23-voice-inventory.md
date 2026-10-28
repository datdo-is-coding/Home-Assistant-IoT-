# Hỏi danh sách thiết bị bằng giọng nói

Yêu cầu: “Trong nhà có những thiết bị nào?” được trả lời từ registry hiện tại.

- Nhánh chỉ đọc chạy trước persona và hội thoại đang chờ, không gửi lệnh relay.
- Hỗ trợ câu hỏi có dấu/không dấu, “nhà mình có thiết bị gì”, “liệt kê các thiết bị trong nhà”.
- Đếm kênh thiết bị đã đăng ký trên node online/offline; bỏ SubBox trung gian, pending và node cần đăng ký lại.
- Đọc tên đã cấu hình và phòng tiếng Việt; gộp tên/phòng/trạng thái trùng nhau kèm số lượng.
- Tối đa 5 nhóm, ưu tiên online, đọc rõ ngoại tuyến và số thiết bị còn lại.
- Giữ luồng Hi ESP → ActionBox → SubBox → Pi → PCM Trúc Ly → loa SubBox.

Kiểm thử: 279 test Gateway, 272 pass, 7 skip. 5 test mới chạy thành công trên Pi.
Triển khai: chỉ Gateway/gateway/main.py và test mới; sao lưu main.py.before-inventory-20261023 trên Pi. Không nạp firmware hay thay cấu hình thiết bị.

Giới hạn: số lượng là số kênh đã cấu hình, chưa xác minh tải vật lý được cắm. Dữ liệu hiện tại có tên/loại thiết bị chưa khớp trên một ActionBox; tính năng này giữ nguyên tên đã đăng ký. Chưa xác nhận người dùng nghe câu liệt kê qua loa thật.
