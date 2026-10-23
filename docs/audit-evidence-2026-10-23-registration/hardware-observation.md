# Quan sát phần cứng sau nạp

- Đã sao lưu và nạp app tại 0x20000 cho ACM0 / MAC 28848533DDF8, ACM1 / MAC 288485350B54, ACM2 / MAC 28848533DDE8. Cả ba xác minh hash thành công.
- Không ghi bootloader, bảng phân vùng, NVS hoặc model.
- MQTT observer chỉ đọc đã nhận trạng thái ONLINE của SB288485350B54 sau nạp.
- Theo dõi 90 giây chưa thấy sự kiện SETUP hoặc CLAIM_APPLIED. Chưa có xác nhận thao tác CONFIG/BUT1 từ người dùng.
- ADB không có điện thoại; chưa cài APK lên máy thật.
- Không gửi lệnh relay hoặc giả lập nút vật lý trên bo thật.

## Kiểm chứng tiếp theo

- SQLite trên Pi xác nhận hai operation claim thành công: `op_claim_cd4bd52a5580` (AB28848533DDF8) và `op_claim_a264408ea95d` (AB28848533DDE8); desired/reported revision đều 1.
- Cả hai ActionBox online, SYNCED, liên kết SB288485350B54; MQTT nhận telemetry từ cả hai.
- Người dùng xác nhận đăng ký đã được (2026-10-23). Chưa thử cắt nguồn giữa commit.
