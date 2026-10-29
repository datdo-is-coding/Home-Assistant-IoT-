# Bộ câu phản hồi giọng nói đề xuất

Ngày 28/10/2026. Đây là danh sách để thiết kế/duyệt, chưa thay các câu đang chạy
trên Pi. Những tình huống hỏi lại, nhớ thiết bị và trả lời điện năng chưa được
luồng CoreVoice hiện tại hỗ trợ đầy đủ.

Giọng xưng “mình”, gọi người dùng là “bạn”; câu ngắn, không dùng mã lỗi hoặc
đọc tên bo/MAC. Tên thiết bị/phòng phải lấy từ cấu hình được phép truy cập.
Các câu thành công chỉ phát khi có ACK APPLIED phù hợp, không dựa vào việc
ghi Firebase hoặc gửi lệnh thành công.

| Tình huống | Câu đáp đề xuất | Điều kiện |
| --- | --- | --- |
| Nhận Hi ESP | Tiếng “ting” ngắn | Phát tại SubBox ngay khi nhận wake; không chờ ASR/TTS |
| Bật thành công | “{thiết bị} đã bật rồi nhé.” | ACK APPLIED xác nhận ON |
| Tắt thành công | “Mình tắt {thiết bị} rồi nhé.” | ACK APPLIED xác nhận OFF |
| Đã bật sẵn | “{thiết bị} đang bật sẵn rồi nhé.” | Trạng thái báo về còn mới, đúng boot/config |
| Đã tắt sẵn | “{thiết bị} đang tắt rồi nhé.” | Trạng thái báo về còn mới, đúng boot/config |
| Đang xử lý | “Mình đang chờ {thiết bị} xác nhận.” | Có yêu cầu hợp lệ; chưa đủ điều kiện báo thành công |
| Hết thời gian chờ ACK | “Mình chưa nhận được xác nhận từ {thiết bị}. Bạn kiểm tra giúp mình nhé.” | Không phỏng đoán ON/OFF và không tự gửi lại lệnh mới |
| Thiết bị offline | “{thiết bị} đang mất kết nối. Bạn kiểm tra nguồn giúp mình nhé.” | Có trạng thái offline/stale được xác thực |
| Chưa nghe rõ | “Mình chưa nghe rõ. Bạn nói lại tên thiết bị nhé.” | ASR thiếu tin cậy; chưa gửi lệnh |
| Không tìm thấy tên | “Mình chưa tìm thấy {tên được nói} trong phòng này. Bạn kiểm tra tên trên app nhé.” | Chỉ tra thiết bị được phép trong phạm vi hiện tại |
| Nhiều đích phù hợp | “Bạn muốn bật đèn bàn hay đèn bể cá?” | Liệt kê các đích hợp lệ; chờ câu trả lời, không tự chọn |
| Nói “tắt nó đi” khi chưa có ngữ cảnh | “Bạn muốn tắt thiết bị nào?” | Không suy đoán đích từ hội thoại phòng/nhà khác |
| Nói “tắt nó đi” khi có ngữ cảnh hợp lệ | “Mình tắt {thiết bị vừa nhắc} rồi nhé.” | Cần bộ nhớ hội thoại còn hạn, kiểm tra quyền và ACK mới |
| Kênh chưa gán tải | “Kênh này chưa có thiết bị. Bạn gán thiết bị trên app trước nhé.” | Chưa có device binding hợp lệ |
| Cấu hình đang đồng bộ | “Mình đang đồng bộ cấu hình mới. Bạn chờ một chút rồi thử lại nhé.” | config_pending; chưa gửi lệnh với cấu hình cũ |
| Đang cập nhật firmware | “Thiết bị đang cập nhật. Xong mình mới điều khiển được nhé.” | OTA đang ở giai đoạn chặn lệnh |
| Thiết bị báo lỗi | “{thiết bị} đang báo lỗi. Mình chưa xác nhận thực hiện được lệnh.” | Không nói đã bật/tắt nếu trạng thái chưa được xác nhận |
| Chưa có số liệu đo mới | “Mình chưa có số liệu mới của {thiết bị}, nên chưa báo chính xác được.” | Không thay dữ liệu thiếu bằng số 0 |

Ví dụ sau khi đổi đúng kênh từ “Đèn bể cá” sang loại khác và tên “Máy pha cà phê”:

- “Bật máy pha cà phê” → sau ACK: “Máy pha cà phê đã bật rồi nhé.”
- “Tắt máy pha cà phê” → sau ACK: “Mình tắt máy pha cà phê rồi nhé.”
- “Bật đèn bể cá” → nếu đã xóa tên/alias cũ: báo không tìm thấy, không bật máy mới.
- Tên gọi khác “máy cà phê” chỉ có hiệu lực khi đã được người dùng gán alias;
  không tự suy đoán hai tên trỏ cùng một kênh.

## Cấu hình thay tải cần đạt

Thêm ActionBox chỉ tạo ba kênh; bo không tự biết tải đang cắm là gì. Người dùng
gán tên/loại/alias trên app. Đổi tải phải cập nhật cả tên và loại, bỏ alias/role
cũ không còn phù hợp, đồng bộ tới Core và xác nhận cấu hình trước khi điều khiển.
ASR phải lấy tên/alias từ cùng nguồn Core được cập nhật đó. Không cần train
lại model cho từng tên nếu ASR tổng quát nhận được tên người dùng nói.

Kết quả kiểm tra hiện trạng:
[thêm bo và đổi tên thiết bị](../testing/voice-dynamic-devices-2026-10-28/README.md).
