# Tên thiết bị đăng ký và nghe tiếp sau câu hỏi

## Yêu cầu và hành vi
- Dùng tên kênh và aliases hiện tại trong registry để nhận diện thiết bị. Tên cụ thể được ưu tiên trước nhóm chung như đèn/quạt. Đổi tên có hiệu lực ở lượt nói tiếp theo, không cần huấn luyện lại bộ phân tích lệnh.
- ASR đưa danh sách tên hiện tại vào hotwords ở mỗi lượt nhận dạng; hotwords hỗ trợ nhận dạng âm thanh, không bảo đảm nghe chính xác mọi tên trong mọi môi trường.
- Cùng tên, cùng phòng trên nhiều thiết bị: hỏi lại bằng tên đăng ký, phòng, kênh và đuôi ID; hỗ trợ chọn tên duy nhất hoặc thứ tự. Không đoán kênh dựa vào độ mới telemetry.
- Bỏ SubBox và thiết bị đang chờ đăng ký khỏi danh sách điều khiển. Thiết bị ngoại tuyến không được chọn thực thi.
- Sau câu hỏi cần bổ sung, phát xong PCM rồi gửi LISTEN_FOLLOWUP tới đúng ActionBox qua hàng đợi lệnh hiện có. Chỉ chấp nhận trong phiên đã đánh thức; mỗi lượt nghe tiếp tối đa 6 giây, phiên wake tối đa 60 giây. Im lặng kết thúc nghe tiếp. Phiên mới vẫn cần Hi ESP.
- SubBox bỏ âm thanh từ ActionBox không được chọn để tránh hai bo cùng đánh thức tạo lượt nói thừa.

## Phạm vi triển khai
Gateway: asr_engine.py, audio_server.py, dialog_manager.py, intent_engine.py, main.py, registry_manager.py.
Firmware: ActionBox_V2 voice_capture/device_manager/protocol; SubBox WsASR/TaskManager/main/AudioManager.
Không đổi tên, loại hay ánh xạ relay đang lưu. Không xóa NVS.

## Xác minh
- Bộ Gateway: 288 tests, 281 pass, 7 skip (log kèm theo).
- Các bài riêng cho tên/đổi tên/ambiguity/đúng kênh: 7 pass; chạy lại sau triển khai cũng pass.
- Pi: 26 tests gồm audio relay và voice dialog targets pass trước khởi động lại.
- Host firmware: kiểm tra capture follow-up, khóa WsASR và thứ tự finish PCM trước callback, nguồn audio relay, parser lệnh. Build cả ActionBox_V2 và SubBox thành công.
- Nạp app-only tại 0x20000 lên DDE8, DDF8, SubBox 0B54; cả ba xác minh hash thành công.
- Sáu module Gateway trên Pi trùng SHA256 với máy phát triển. Service active; ASR/TTS khởi động, WebSocket nhận lại loa SubBox.
- Backup Gateway trước cập nhật: /home/pi4/Home-Assistant-IoT-/Gateway/backups/voice-followup-20261024/.

## Chưa xác nhận trên phần cứng
Đang chờ người dùng thử Hi ESP → bật đèn chính → sau câu hỏi nói hủy mà không đánh thức lại. Chưa xác nhận mic thực tế nhận tên tự đặt sau đổi tên trong app.
Hai ActionBox hiện cùng có các tên Đèn chính, Quạt trần, Bình nóng lạnh trong cùng phòng; cần chọn rõ khi trùng. Đèn trần chưa là tên đăng ký hiện tại, không tự đổi ánh xạ để tránh bật nhầm.
Luồng nghe tiếp triển khai cho PCM SubBox đang dùng; chưa mở rộng fallback MP3. Nhật ký khởi động còn báo config_version SubBox 1 so với registry 2; speaker đã kết nối, chưa xác nhận đây có ảnh hưởng ở kiểm thử phần cứng mới.

Bằng chứng: ../audit-evidence-2026-10-24-voice-followup/ (log và SHA256). Mốc ngày báo cáo theo máy phát triển; đồng hồ Pi có thể khác.

## HIL và sửa tiếp: trả lời “bật cả hai” bị hỏi lặp
Người dùng báo loa hỏi liên tục, không nhận câu trả lời. Log Pi PID 6513 chứng minh mic đã mở lại và ASR nhận đúng “bật cả hai” bốn lượt; main.py lại coi động từ “bật” là lệnh mới, xóa phiên rồi phân giải thành tên trùng, hỏi lại từ đầu. Đây là lỗi ngữ cảnh, không phải mất âm thanh ở các lượt ghi nhận.

Đã sửa main.py/dialog_manager.py để thử điền lựa chọn trước khi xét lệnh mới; hỗ trợ động từ + số thứ tự hoặc “cả hai”, chỉ áp dụng cho danh sách vừa đọc của cùng phiên. Nhóm được kiểm tra lại với registry trước khi gửi, không mở rộng sang thiết bị khác; nếu một lựa chọn biến mất thì không gửi một phần. Sao chép intent khi điền để không sửa ngầm phiên gốc. Giới hạn một lần hỏi lại sau câu trả lời không rõ, lần tiếp theo dừng. Lệnh mới có tên thiết bị khác vẫn thay thế phiên cũ.

Kiểm thử tái hiện trước sửa thất bại 6 trường hợp; sau sửa 15 bài chuyên biệt pass trên máy phát triển và Pi (không tác động relay thật). Toàn bộ Gateway chạy 294 bài, 287 pass, 7 skip; sau đó bổ sung hai bài kiểm tra targets không đáng tin và lỗi một thiết bị trong nhóm, cả hai pass trong bộ 15 bài. Hai module đã triển khai, backup tại Gateway/backups/voice-selection-20261024 trên Pi. Không cần đổi firmware ở bước sửa này. Chờ xác nhận người dùng trên phần cứng.

Sau khởi động lại, PID 6949: ASR initialized, VieNeu loaded, loa SubBox đăng ký lại; SHA256 hai module khớp máy phát triển. Đã mời người dùng thử lại bật cả hai hoặc hủy.

Người dùng đã xác nhận “ok rồi” sau lượt thử: nghe tiếp không cần Hi ESP, xử lý lựa chọn và không hỏi lặp. Việc đổi tên trong app rồi gọi tên mới vẫn chưa được xác nhận bằng mic thật.
