# Sửa lag tab Nhà — 2026-10-28

Đã cài APK release 1.3.1+20 lên Xiaomi 23116PN5BC qua USB. Chữ ký khớp bản
cũ; Google/Firebase vẫn đăng nhập, dữ liệu cloud hiển thị và tab Điện năng mở
được. Không gỡ app hoặc xóa dữ liệu.

Nguyên nhân đã tái hiện: `SliverLayoutBuilder` nhận constraints đổi theo từng
nhịp cuộn và dựng lại lưới/thẻ thiết bị. Một lượt cuộn ngắn dựng lại cùng thẻ
29 lần. Đổi sang tính số cột theo viewport, giữ grid khỏi callback layout theo
scroll offset; kiểm tra sau sửa là 0 lượt dựng lại thừa. Đã kiểm tra đổi kích
thước vẫn từ 2 sang 3 cột.

Đồng thời bỏ blur nền thanh điều hướng, giữ phần thẻ cố định trong
RepaintBoundary khi nhấn, và bổ sung Material cho thanh trạng thái để sửa chữ
gạch vàng. Bảy kiểm tra tập trung của màn Home đều qua.

| Cùng bốn lượt vuốt, 450 ms/lượt | FPS trung bình | Khung jank / timeline |
| --- | ---: | ---: |
| Trước: 1.3.0 debug | 17,867 | 30 / 32 |
| Sau: 1.3.1 release, lượt 1 | 62,500 | 0 / 119 |
| Sau: 1.3.1 release, lượt 2 | 61,951 | 1 / 119 |

Số đo lấy từ SurfaceFlinger của đúng SurfaceView HomeCompetition. Đây là các
lượt ngắn trên một điện thoại; cả code và chế độ debug→release đều thay đổi,
không tách tỷ lệ cải thiện riêng của từng thay đổi. Không đo lại relay hay ghép
bo. Chi tiết nằm trong [results.json](results.json).

Đã gọi Antigravity CLI ở chế độ yêu cầu chỉ đọc để rà phụ; CLI trả về phản hồi
dở dang khi hết 120 giây. Kết luận sửa dựa vào tái hiện, regression và đo trên
thiết bị, không dựa vào lời xác nhận dở dang đó. Các kênh đo/forward tạm đã tắt.

APK hiện tại: `releases/android/HomeCompetition.apk`, có checksum trong
`releases/SHA256SUMS`. Build dùng `flutter build apk --release`; metadata plugin
được tạo lại đúng chế độ release, không đổi phiên bản dependency.

## Yêu cầu 120 Hz — bản 1.3.2+21

MainActivity yêu cầu mode cao nhất không quá 120 Hz trong cùng độ phân giải
khi app resume/nhận focus. Điện thoại xác nhận preferredRefreshRate=120.00001,
preferredDisplayMode=2 và active mode=2 (120 Hz). Không sửa tần số toàn máy;
tùy chọn high refresh riêng cho app vốn đã bật.

Các lượt vuốt ADB dao động khoảng 93–120 FPS; ba lượt bắt đầu cùng vị trí Home
đạt 108,581 / 110,638 / 115,546 FPS. Probe tạm đo sau khởi tạo: p95 dựng UI
khoảng 2,0–2,3 ms, raster 3,4–4,0 ms. Không coi việc xin 120 Hz là bảo đảm mọi
khung hình cố định 120 FPS.

Người dùng xác nhận “RỒI MƯỢT RỒI”. Đã dừng đo thêm, bỏ APK probe và trả về
APK release 1.3.2 thường, giữ đăng nhập và yêu cầu 120 Hz. APK local được thay
bằng bản thường; probe tự cuộn không được cài làm bản sử dụng.
