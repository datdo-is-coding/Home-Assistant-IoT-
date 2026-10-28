# Nối KWS, ba relay chốt và phản hồi — 2026-10-28

## Quyết định đã xác nhận

- Dùng ActionBox đang cắm (DDE8), sao lưu đầy đủ trước khi chuyển firmware.
- Phòng thuộc SubBox; ActionBox kế thừa phòng và chỉ gán thiết bị cho CH1–CH3.
- Ba relay chốt hai cuộn: SET 30 ms để bật, RESET 30 ms để tắt, sau đó nhả chân.
- Giữ KWS/model trên SubBox, không huấn luyện và không bật ASR trên Pi.
- Giữ enrollment/Core/OTA và kiểm tra quyền hiện có. ActionBox giữ quyền GPIO,
  bảo vệ tải, chống lặp và báo trạng thái.

## Thực hiện

1. Đổi thời gian xung 30 ms, kiểm tra driver thực với cả ba kênh, SET/RESET,
   trạng thái nghỉ, lệnh lặp và bảo vệ. Sao lưu/kiểm tra định danh DDE8.
2. Nối cấu hình phòng SubBox, thiết bị từng kênh và đích khẩu lệnh qua Firebase
   tới registry Core. Trạng thái app lấy từ báo cáo bo; ghi cloud không phải ACK.
3. Đồng bộ đích KWS có phiên bản xuống SubBox qua Core đã xác thực. SubBox ghép
   đủ câu rồi chọn đích; chỉ dùng đèn/quạt và khách/ngủ/bếp đang có. Không tự
   chọn kênh khi chưa gán hoặc có nhiều đích cùng khẩu lệnh.
4. Ý định có đích xác định đi qua hàng đợi lệnh Core đang chạy trên Pi (Core
   hiện chỉ chấp nhận lệnh đã xác thực của Gateway). Pi không nhận dạng tiếng
   nói hoặc phân tích lại transcript. Chờ ACK đúng bo/kênh/phiên rồi phản hồi
   qua đúng loa SubBox; mất Pi thì đường lệnh Core này không thực thi.
5. Kiểm thử từ cấu hình đến lệnh/ACK/phản hồi, nạp các thay đổi cần thiết và thử
   từng kênh trên bo thật. Kiểm thử nói thật ghi riêng với kiểm thử gửi ý định;
   không coi model hiện tại đã nhận đúng chỉ vì relay/loa hoạt động.
