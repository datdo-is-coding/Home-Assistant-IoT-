# Progressive Blur + Light Rays — 2026-10-29

Giao diện 1.6.0+41 dùng nền bạc/xanh dịu ở chế độ sáng và kính xanh đậm ở chế
độ tối. Ánh sáng chéo có nguồn sáng thống nhất, mép mềm và tắt dần xuống dưới.
Các ảnh là render bằng dữ liệu kiểm thử có sẵn, không phải dữ liệu nhà thật.

## Thay đổi

- Dock nổi năm tab, kính mờ tăng dần qua ba dải nhỏ. Không blur từng thẻ hoặc
  toàn màn hình; vùng fog ở thanh trạng thái chỉ dùng gradient nhẹ.
- Nền tia sáng vẽ tĩnh, RepaintBoundary và gợi ý raster cache; không có ticker
  ánh sáng chạy liên tục. Chạm thẻ vẫn có phản hồi nhấn và nghiêng nhẹ.
- Thẻ, nhóm cài đặt, ô tìm kiếm và bảng điều khiển dùng bề mặt xuyên sáng nhẹ,
  giảm viền/bóng đậm; thống nhất chữ, khoảng cách, màu công tắc và số liệu.
- Giữ tên nhà xanh/cam báo kết nối, chấm online riêng và trạng thái lệnh đang
  chờ. Quyền quản trị, ghép nối, IR, Firebase và trạng thái thực không bị đổi.
- Blur không bắt chạm; giảm hiệu ứng/tương phản cao dùng nền gần đặc để đọc
  rõ. Không thêm thư viện hay tải font từ mạng. Giữ yêu cầu 120Hz và bổ sung
  yêu cầu cùng tốc độ cho Surface Android khi sẵn sàng.

## Kiểm tra

189 test app cuối đã qua, gồm inset thanh trạng thái thật, lớp modal và đi từ
bảng điều khiển sang cài đặt; có thêm ảnh render năm tab sáng/tối.
Analyze sạch. Đã xem đủ năm tab ở cả sáng/tối, dùng font Roboto thật; các kiểm
tra hiện có giữ phủ phone/tablet, chữ lớn, quyền và thao tác điều khiển.

Bài đo profile dùng 120 kênh, cập nhật 5Hz, không gửi lệnh relay. Lượt ba dải
blur ghi 571 frame: UI p50 0,416 ms / p95 14,175 ms; raster p50 7,800 ms /
p95 18,869 ms. Chưa đạt tiêu chí mọi frame trong 8,33 ms của 120Hz. Đây là
stress test, không phải số FPS app nhà thật. Gợi ý cache nền tĩnh và sửa inset dock được thêm sau lượt đo; chưa đo lại tác
động riêng của chúng. Không dùng kết quả này để hứa
120 FPS cố định. Chi tiết ở [evidence.json](evidence.json).

## Cài đặt

Đã cài và mở bản release **1.6.0 / code 41**, chứng thư khớp, không có lỗi
Flutter lúc khởi động. Lượt cài cuối dùng cập nhật trực tiếp, không gỡ app.
APK: `releases/android/HomeCompetition.apk`; tất cả checksum trong releases
đều khớp. Người dùng đã đăng nhập Google lại; dữ liệu nhà thật đã tải 12 thiết bị. Đã
xem cả năm tab trên điện thoại, không gửi lệnh relay. Ảnh điện thoại giữ riêng
trong build/ui-review, ảnh chia sẻ trong tài liệu chỉ dùng fixture. Khoảng đệm
status bar bị lặp ở dock trên máy thật đã sửa. Bảng điều khiển nhanh/thông báo/
tài khoản/tạo lịch dùng navigator gốc, nổi trên dock; Cài đặt đóng đúng bảng
trước khi chuyển trang. Bảng điều khiển có kính mờ riêng và chữ thích nghi
chiều rộng, không để dock che công tắc.

Lượt đo đầu phát hiện trên điện thoại có APK code 38 từ worktree khác, cao
hơn bản nguồn lúc bắt đầu. Flutter drive tự gỡ bản đó khi gặp downgrade rồi
cài profile code 27: phiên Google/tùy chọn lưu trên máy có thể mất. Người dùng
đã được thông báo và yêu cầu không khôi phục app cũ. Bài đo không ghi dữ liệu
thiết bị lên Firebase. Các lượt sau kiểm tra version trước, cài trực tiếp bằng
ADB -r, rồi chỉ nối driver vào VM có sẵn; không dùng đường tự gỡ của Flutter.
Bản dùng thật tăng lên code 41 để cài cập nhật bình thường. Cần đăng nhập
Google lại nếu phiên cũ đã mất; quyền nhà và thiết bị cloud vẫn thuộc tài khoản.

Ảnh xem trước: [Nhà tối](previews/home-dark.png), [Nhà sáng](previews/home-light.png),
[Thiết bị](previews/devices-dark.png), [Điện năng](previews/energy-dark.png),
[Kịch bản](previews/automation-light.png), [Cài đặt](previews/settings-light.png).

Lượt cập nhật cuối code 41 giữ phiên Google vừa đăng nhập và theme người dùng
đã chọn. Đã nhìn thấy Home tối, đủ 12 thiết bị và dock gọn trên máy thật;
không còn khoảng đệm status bar bị lặp. Không có lỗi Flutter khi mở bản cuối.
