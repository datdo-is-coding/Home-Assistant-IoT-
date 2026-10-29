# Cập nhật HomeCompetition qua Firebase

- Làm trực tiếp trên `main`, giữ thay đổi đang có của `discovery_manager.py`.
- App tự kiểm tra catalog `app_releases/android/stable` khi mở/trở lại foreground,
  có giới hạn tần suất; không chặn đăng nhập hoặc giao diện khi mất mạng.
- Tự tải nền khi mạng không tính phí; trên mạng di động người dùng bấm tải.
  File đã tải được tái sử dụng sau khi xác minh, không tải lại mỗi lần mở app.
- Catalog chỉ đọc cho tài khoản đã đăng nhập, chỉ quy trình phát hành Admin SDK
  được ghi. Không thay Rules của devices/commissioning hoặc lệnh điều khiển.
- APK phải có HTTPS, host phát hành được cho phép, size/hash đúng. Android kiểm
  tra lại package name, version code tăng và cùng chứng thư với app đang cài.
- File chỉ nằm trong thư mục cache cập nhật riêng, FileProvider chỉ chia sẻ
  thư mục này. Cài đặt dùng trình cài Android và giữ dữ liệu; không uninstall.
- Cài đặt → Cập nhật ứng dụng có kiểm tra lại, tiến trình tải, lỗi và cài APK.
  Khi tải xong chỉ nhắc gọn; không chặn điều khiển thiết bị bằng hộp thoại bắt buộc.
- Project Spark chặn APK trên Hosting/Storage. Đang chờ người dùng chọn giữ
  Firebase catalog + GitHub Releases, hoặc chuyển Blaze để lưu toàn bộ Firebase.
  Không đổi đuôi file để vượt hạn chế và không tự gắn billing.
- Bản app cũ chưa có updater cần cài bản bootstrap một lần; sau đó các bản mới
  dùng catalog. Chỉ báo hoàn thành đầu-cuối sau kiểm tra trên điện thoại thật.

Nguồn: https://firebase.google.com/docs/hosting/faq-and-troubleshooting?hl=en
và https://developer.android.com/studio/publish (Install unknown apps).
