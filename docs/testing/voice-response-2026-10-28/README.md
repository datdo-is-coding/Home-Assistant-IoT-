# Pi4 — kiểm thử phản hồi giọng nói, 2026-10-28

**Đã sửa và triển khai đường Pi4 → loa SubBox. Người dùng xác nhận nghe rõ đủ
câu; bản cuối 2.0.2-b2 đã OTA thành công và xác nhận phát hoàn tất đúng. Các số
đo tổng hợp câu mới bên dưới vẫn còn chậm, chưa được tối ưu trong bản sửa này.**

## Phép đo trên dịch vụ thật

Gọi API đã xác thực của Gateway đang chạy, PID 3308, ngay trên Pi qua loopback.
Engine `v3nano`, giọng Trúc Ly; model đã nằm trong RAM trước phép đo. Không restart
dịch vụ, không chạy training, không gửi lệnh điều khiển thiết bị.

Mỗi câu được gọi lần đầu rồi lặp hai lần. Thời gian tính từ gửi HTTP request tới
nhận đủ audio. Đây là độ trễ tạo phản hồi từ văn bản, chưa gồm nhận giọng nói,
thời gian truyền tới loa và thời điểm âm thanh thực sự nghe được. Ba lần đầu
được log xác nhận dùng VieNeu local; không phải kết quả fallback EdgeTTS.

| Câu | Tạo audio lần đầu | Độ dài audio | Hai lần lặp có cache |
| --- | ---: | ---: | ---: |
| “Đây là kiểm tra giọng nói của Gateway.” | 4,610 s | 2,210 s | 6,58 / 4,47 ms |
| “Tôi chưa nhận được trạng thái thiết bị. Bạn vui lòng kiểm tra kết nối.” | 6,860 s | 4,070 s | 4,90 / 4,90 ms |
| “Bạn có thể gán từng kênh cho đèn hoặc quạt trong ứng dụng, sau đó chọn phòng khách, phòng ngủ hoặc phòng bếp.” | 10,683 s | 6,710 s | 5,21 / 5,28 ms |

RTF lần đầu lần lượt 2,09 / 1,69 / 1,59: tốc độ tạo audio chậm hơn thời lượng
phát. API này đợi tạo xong cả audio rồi mới trả dữ liệu; không có lợi thế phát
ngay phần đầu câu trong phép đo hiện tại.

File WAV mono PCM16, 24 kHz, có tín hiệu khác zero và hash khớp số liệu đo:
[`short.wav`](short.wav), [`medium.wav`](medium.wav), [`long.wav`](long.wav).
Đây là âm thanh tổng hợp lưu từ API, không phải bản thu tiếng loa SubBox.

## Khả năng đáp ứng trong lúc tạo giọng

Trong 28,103 s đo, 90 request health đều HTTP 200:

- Trung vị 3,22 ms; p95 5,30 ms; chậm nhất 909,74 ms.
- Gateway dùng thêm 51,75 CPU-seconds; RSS cao nhất được lấy mẫu 716,53 MiB.
- Có một lần trễ gần 0,91 s; không thể khẳng định mọi thao tác đều mượt chỉ từ
  trung vị thấp. Bộ test ngắn này chưa chứng minh khả năng nhiều phòng đồng thời.

## Lượt thử loa thực trước khi sửa

API `/api/proactive/test_speak` được gọi với câu “Hệ thống nhà thông minh đang
hoạt động ổn định”. Lần đầu mất 5,537 s, trả `success: true`; lượt cuối dùng
PCM cache mất 41,88 ms và cũng trả `success: true`.

Tuy nhiên:

- Một TCP/WebSocket tới cổng 8765 còn tồn tại; kết nối TCP chưa chứng minh đã
  đăng ký thành công làm speaker target.
- Không có log `Streaming ... PCM` hoặc `Streamed ... chunks` cho các lượt thử.
- Người dùng xác nhận **“Không nghe thấy”** từ loa SubBox.
- Source `web_server.py` khi đó chuyển `ok=True` khi tạo được PCM, kể cả khi
  `speak_proactive` không tìm được loa. Vì vậy `success` lúc đó có thể chỉ là
  tổng hợp được giọng, không phải gửi/phát thành công.

Kết quả toàn tuyến Pi → SubBox → loa trước sửa: **chưa đạt**. Chưa có số đo thời gian từ
kết thúc câu nói của người dùng đến âm thanh phát ra loa.

## Điểm cần kiểm tra khi sửa đường phát

Source SubBox khởi tạo `WsASR` trước `hc_runtime_init`; callback khi WebSocket
kết nối chỉ gửi hello đăng ký speaker nếu Core chưa bật. Đó là một khả năng gây
socket vẫn mở nhưng không có speaker được đăng ký khi Core đã được bật. Cần
test thứ tự init/reconnect và log boot để khẳng định đường cụ thể trên bo.

Ngoài ra, dịch vụ Core voice riêng chưa chạy, không có listener trên 8081/8443;
không được coi endpoint voice Core đã hoạt động chỉ vì Core radio có heartbeat.
Không bỏ xác thực hoặc trộn hai đường voice để né bước đăng ký.

Bước sửa cần làm rõ ba trạng thái: tạo audio, gửi tới đúng loa, và xác nhận phát
xong. Sau khi đường loa hoạt động, cần đo lại độ trễ toàn tuyến và chất lượng
nghe. Cache các câu trả lời thường dùng giúp phần tổng hợp nhanh; số đo này chưa
chứng minh tốc độ tương tự cho câu mới.

Số liệu gốc: [`results.json`](results.json), [`playback-evidence.json`](playback-evidence.json).

## Bản sửa đường loa

Host test tái hiện được thứ tự `WsASR::init` chạy trước khi Core bật. Chế độ loa
nay lấy từ enrollment đã lưu, nên không đổi theo thời điểm kết nối/reconnect.
SubBox đã enroll dùng WSS tới cùng Gateway của MQTT, kiểm tra CA đã ghim và
xác thực bằng HMAC riêng cho chức năng loa, suy ra từ khóa vận hành của chính bo.
Gateway chỉ chấp nhận SubBox còn đăng ký trong đúng nhà; đường này chỉ phát loa,
không nhận microphone hoặc điều khiển relay qua giao thức cũ.

Mỗi lượt phát có mã ngẫu nhiên gắn với đúng kết nối. Gateway chỉ báo thành công
sau khi bo xác nhận đủ byte PCM và ghi/kết thúc I2S thành công. Gói quá lớn,
sai định dạng, thiếu xác nhận hoặc mất kết nối không được báo thành công; không
chuyển sang MP3 khi SubBox chỉ hỗ trợ PCM. Lỗi tổng hợp được audio nhưng không
có loa cũng không còn bị `/api/proactive/test_speak` báo thành công.

Kiểm thử sau sửa: **462 Gateway tests và 35 firmware host tests đều qua**,
gồm Firebase emulator thật và kết nối WSS loopback thật. Hai project SubBox và
ActionBox_V2 đều build thành công với ESP-IDF 6.0.2. Host test kiểm tra cả ghi
thiếu dữ liệu, lỗi driver, lỗi kết thúc phát và xả hết hàng đợi trước khi tắt
amplifier. Đây chưa phải xác nhận âm thanh nghe được từ loa thật.

Gateway đã được cập nhật và trở lại health HTTP 200; dịch vụ radio/OTA vẫn giữ
PID 864. Bản sao lưu trước cập nhật tại Pi:
`/home/pi4/.local/state/voice-playback-fix/20261028/before-042450/`.
WSS đã kiểm tra CA và tên/IP máy chủ. Gói SubBox 2.0.2-b1 (counter 4) đã ký và
kiểm tra độc lập tại [`releases/firmware/2.0.2-b1`](../../../releases/firmware/2.0.2-b1).

Lượt OTA đầu `OTA-e0a330584bb1da4fd33b9193` dừng ở 4608 byte với
`transfer_timeout` khi mở USB. Log sau đó xác nhận `USB_UART_CHIP_RESET` khi
mở cổng; không mở/đóng USB trong các lượt truyền tiếp theo.
Lượt `OTA-a86525734a2c519b8384808e` đã `SUCCEEDED`, đủ 1191280 byte, firmware
2.0.2-b1, heartbeat mới và config revision 1/1. WSS đăng ký đúng
`SB288485350B54`, tự đăng ký lại sau khi Gateway restart.

Người dùng xác nhận **nghe rõ đủ câu** từ loa thật. Lượt phát nhận đủ 81600
byte PCM nhưng báo `output_ok=False`; API trả lỗi đúng thay vì báo thành công.
Nguyên nhân còn lại là các lệnh `i2s_channel_write` nhận timeout theo millisecond,
trong khi code đưa `pdMS_TO_TICKS`. Bo dùng FreeRTOS 100 Hz nên thời gian chờ bị
ngắn hơn dự định 10 lần. Host test đã chuyển sang mô phỏng đúng 100 Hz, bắt được
lỗi này trước khi sửa cả bốn lệnh ghi I2S trong `SoundPlayer`.

Gói 2.0.2-b2, counter 5 đã ký và OTA **SUCCEEDED** bằng job
`OTA-0453ade21bc890b367fda5a9`, đủ 1191280 byte. Bo online với boot ID mới,
registration `REGISTERED`, config revision 1/1. Không ghi đè enrollment,
calibration hay model.
Kết quả trước bản cuối: [`playback-after-fix-b1.json`](playback-after-fix-b1.json),
[`no-speaker-after-fix.json`](no-speaker-after-fix.json).

Lượt cuối trên 2.0.2-b2 gửi 81600 byte PCM qua 40 chunk, SubBox xác nhận phát
hoàn tất và API trả `success: true`. Tổng thời gian request đến xác nhận là
2726,60 ms, gồm cả 2,55 s âm thanh; câu này dùng cache, không phải số đo tổng hợp
câu mới. Trong lượt phát, 14 request health đều HTTP 200, trung vị 1,93 ms và
chậm nhất 46,11 ms. Dịch vụ radio vẫn PID 864; Gateway PID 2776, source hashes
khớp repo. Lượt restart Gateway trước đó cũng kiểm chứng SubBox tự kết nối lại.

Bằng chứng cuối: [`playback-final-b2.json`](playback-final-b2.json),
[`final-state.json`](final-state.json), [`fix-validation.json`](fix-validation.json).
Chưa kiểm thử toàn chuỗi nhận câu nói → phân tích lệnh → điều khiển tải trong
lượt này; phép thử chỉ phát lời đáp, không đóng relay.
