# Điều khiển bằng KWS tại SubBox, phản hồi tại Pi4

**Đã thay thế theo yêu cầu ngày 28/10/2026:** chuyển nhận dạng và xử lý lệnh
về Pi4. ActionBox giữ WakeNet/thu âm và relay, SubBox chuyển PCM/phát loa;
không chạy model KWS cục bộ hoặc train thêm. Xem
[kế hoạch rollback](../plans/2026-10-28-pi4-voice-rollback.md) và
[bằng chứng triển khai](../../testing/pi4-voice-rollback-2026-10-28/README.md).
Thiết kế KWS bên dưới được giữ làm lịch sử, không phải kiến trúc đang chạy.

Ngày thiết kế: 25/10/2026. Cập nhật 26/10: đã triển khai pilot Pi/SubBox/DDF8; timing đạt sau tối ưu, nhận dạng âm thanh thật chưa đạt. Xem báo cáo triển khai.
Bằng chứng và giới hạn: `docs/implementation/2026-10-25-local-kws.md`.

Cập nhật 28/10: theo yêu cầu người dùng, thay cửa sổ trượt bằng VAD từng từ
và đệm giữa 1 giây như firmware KWS cũ, sửa lỗi lặp onset và đếm im lặng thành
thời gian nói. Chi tiết: [kế hoạch VAD](../plans/2026-10-28-subbox-word-vad.md).
Model/MFCC giữ nguyên; build và kiểm tra trên máy chưa thay thế nghiệm thu bo thật.

## Yêu cầu đã được người dùng chốt

- Giữ ActionBox → SubBox → Pi4; bắt buộc kích hoạt bằng “Hi ESP”.
- SubBox chạy bộ KWS đã có, tự xác định và thực hiện lệnh qua ActionBox.
- Chỉ dùng từ model đã biết; không cần gọi tên tự do hay hỏi đáp giọng nói tự do.
- Pi4 tạo câu trả lời từ kết quả SubBox và xử lý dữ liệu đo; không nhận dạng hoặc suy luận lại lệnh nói.
- SubBox điều khiển xuống ActionBox; phần relay phải tuân theo ActionBox_V2.
- Giữ đăng ký, cấu hình, reset, điều khiển app, số liệu dòng và các sửa chữa hiện có.

## Hướng thực hiện

Chọn đưa model/MFCC KWS hiện có vào SubBox; giữ WakeNet và thu âm tại ActionBox. Dùng ESP-NOW cho âm thanh và lệnh nội bộ; MQTT hiện có cho kết quả và chuyển tiếp giữa các SubBox; WebSocket hiện có chỉ phục vụ âm thanh phản hồi từ Pi. Đây là đề xuất kỹ thuật theo lựa chọn của người dùng, chưa phải bản đã nạp.

Không chọn chạy KWS trên ActionBox vì người dùng yêu cầu SubBox xử lý, và code thu âm hiện ghi nhận suy luận đồng bộ có thể tràn DMA. Không chọn tiếp tục ASR trên Pi hoặc thay model nhận dạng mở vì người dùng đã loại hai nhu cầu này. Không thêm nền tảng IoT hoặc broker mới.

## Bằng chứng từ code hiện tại

- `ActionBox_V2/src/audio/kws/kws_config.h`: 10 lớp, gồm bật/tắt/đèn/quạt/phòng/khách/ngủ/bếp và noise/unknown; cửa sổ 1 s, bước 250 ms. Ngưỡng hiện có 0,40 chưa phải bằng chứng đủ tin cậy để đóng relay.
- `firmware_kws/firmware/src/main.cpp`: demo ghép hành động và thiết bị rồi điều khiển hai relay; từ chỉ phòng mới được in log. Chỉ tái sử dụng model và xử lý đặc trưng, không sao chép cách thực thi demo.
- `SubBox/src/main.cpp` tạo `WsASR`; `AudioManager` đưa PCM lên Pi. Có interface `ASREngine` và callback utterance để dùng lại, nhưng phải nối hoàn chỉnh kết quả KWS.
- `SubBox/src/system/task_manager.cpp`: có `nluTask` nhưng hiện không khởi tạo task đó; mặc định kênh 1 LIGHT, kênh 2 FAN khi tạo registry. Không được dùng mặc định này để điều khiển thực tế.
- `CommandRouter` có thực thi nội bộ, chờ ACK và kiểm tra ON/OFF; nhánh khác phòng và nhánh phức tạp chỉ trả thông tin, sau đó đường voice request đưa xử lý về Pi. Đường mới phải thay luồng đó.
- `ActionBox_V2/src/config/board_pins.h`: ba relay chốt hai cuộn, xung 50 ms; CH1 SET16/RESET15, CH2 SET7/RESET6, CH3 SET5/RESET4. Driver relay của ActionBox là nguồn chuẩn duy nhất cho phần điện.
- `ActionBox_V2` kiểm tra đăng ký/peer, danh tính, phiên bản cấu hình, lệnh trùng; thực thi qua device manager, gửi ACK và load report. Giữ các kiểm tra này.
- Pi hiện có khóa ASR/phát âm chung; đường phản hồi nhiều SubBox cần giới hạn công việc và tách khóa theo loa.

## Luồng mới

1. ActionBox phát hiện Hi ESP, phát tín hiệu bắt đầu, gửi PCM16 mono 16 kHz tới SubBox đã ghép.
2. SubBox nhận và đệm âm thanh; task suy luận riêng chạy KWS. Không suy luận trong callback ESP-NOW hoặc giữ mutex bộ đệm trong lúc suy luận.
3. Bộ ghép từ chỉ nhận một phiên có nguồn xác định. Thu đủ câu trước khi thực thi để “bật đèn phòng ngủ” không bật đèn tại phòng hiện tại ngay sau hai từ đầu.
4. Kết thúc câu, SubBox giải quyết hành động, loại thiết bị và phòng; chọn đúng bo/kênh từ cấu hình, gửi TURN_ON hoặc TURN_OFF theo giao thức ActionBox_V2 hiện hành.
5. ActionBox tự kiểm tra và điều khiển driver relay; gửi ACK. SubBox chỉ báo thành công khi ACK hợp lệ, đúng nguồn, request/session/channel và trạng thái yêu cầu.
6. SubBox gửi sự kiện kết quả có cấu trúc tới Pi. Pi đọc tên thiết bị hiện có, tạo câu ngắn từ mẫu, tổng hợp giọng đã chọn và phát về đúng SubBox nguồn.
7. Telemetry từ ActionBox tiếp tục đi qua SubBox tới Pi và app, độc lập việc đang nhận dạng hoặc đọc câu trả lời.

## Khẩu lệnh, ánh xạ và phiên nghe

- Ngữ pháp ban đầu: `[bật|tắt] [đèn|quạt] [phòng khách|phòng ngủ|bếp]`; phần phòng có thể bỏ. “phòng bếp” cũng hợp lệ. Không hỗ trợ tên tùy ý, toggle, hủy, bật cả hai hoặc câu hỏi tự do vì model không có các từ tương ứng.
- Không có phòng thì dùng phòng của ActionBox phát lệnh đã cấu hình; phải đồng bộ thông tin này xuống SubBox. Không đoán từ tên hiển thị hoặc lấy phòng của SubBox nếu nguồn đã có phòng riêng.
- App cho gán một thiết bị relay cụ thể cho mỗi cặp phòng + đèn/quạt. Tên hiển thị giữ nguyên; vai trò khẩu lệnh là cấu hình riêng. Có thể gán bất kỳ CH1–CH3, không mặc định theo số kênh. Không tự gán các tải đang có.
- Mỗi cặp phòng/loại chỉ có một đích được gán. Thiếu đích, trùng cấu hình, thiết bị ngoại tuyến, sai phiên bản cấu hình: báo lỗi, không tự bật thiết bị khác hoặc toàn bộ nhóm.
- Cấu hình lưu qua cơ chế cấu hình hiện có và lưu bền tại SubBox; xác nhận đồng bộ trước khi app báo áp dụng. Gắn với danh tính/đời đăng ký, vô hiệu khi xóa, đổi chủ hoặc chuyển bo; không tái sử dụng ánh xạ cũ sang thiết bị mới cùng nhãn.
- Hợp nhất các nhận dạng lặp trong một phiên; noise/unknown không tạo lệnh. Từ mâu thuẫn, câu không hoàn chỉnh hoặc chất lượng âm thanh kém: không thực thi. Ngưỡng và số lần xác nhận dựa trên kiểm thử audio/bo thật, không lấy 0,40 làm ngưỡng thực thi mặc định không kiểm chứng.
- Một phiên KWS hoạt động trên mỗi SubBox. Nguồn thứ hai nhận tín hiệu bận; không trộn PCM hoặc câu giữa các ActionBox. Các SubBox khác có thể nhận dạng độc lập.
- Giữ yêu cầu nghe tiếp sau câu hỏi: khi chỉ thiếu một thành phần trong bộ từ hỗ trợ, Pi đọc câu hỏi có cấu trúc và mở một lượt nghe tiếp tại đúng ActionBox sau khi loa hoàn tất. Không yêu cầu Hi ESP lần nữa. Tối đa một lượt, hết hạn hoặc vẫn không đủ thì kết thúc bằng tín hiệu lỗi; không lặp hỏi vô hạn. Ngữ cảnh do SubBox giữ, Pi không giải quyết câu trả lời. Câu có mâu thuẫn hoặc trùng đích thì kết thúc, không hỏi tên tự do không thể nhận dạng.

## Lệnh khác SubBox và khi mất kết nối

- SubBox nguồn giải quyết lời nói và xác định SubBox sở hữu đích từ danh mục đã đồng bộ. Chuyển ý định đã xác định qua broker MQTT hiện có; SubBox đích xác minh quyền, cấu hình đích và thực thi qua ActionBox của nó. Không chuyển transcript tới hàm xử lý lệnh giọng nói của Pi.
- Pi vẫn chạy broker, quản lý đăng ký/cấu hình, API/app; “không xử lý lệnh nói” không có nghĩa tắt broker hoặc bỏ lệnh từ app.
- Sử dụng topic có ACL/định danh đã được xác minh; thay đổi ACL nếu cần, không mở wildcard cho mọi thiết bị. Chỉ chấp nhận lệnh nguồn hợp lệ thuộc cùng hệ thống và có ánh xạ đúng.
- Request có định danh nguồn + phiên khởi động + số thứ tự, tuổi thọ ngắn, QoS không retained, chống lặp. Không thực thi lệnh chờ cũ sau reconnect. Dùng hạn hiệu lực trên đồng hồ đã đồng bộ và từ chối lệnh từ xa nếu chưa xác lập được thời gian đáng tin; không so sánh uptime giữa hai bo. Chi tiết mã hóa chọn trong triển khai phù hợp MQTT hiện có.
- ACK từ SubBox đích trở lại SubBox nguồn; timeout là chưa xác nhận, không phải thành công. Không retry thành một yêu cầu mới có thể thực thi lại; giữ ID và áp dụng chống lặp. Không tự động thực thi sau khi phiên đã hết hạn.
- Mất Pi/broker: điều khiển ActionBox thuộc chính SubBox vẫn hoạt động với cấu hình đã lưu; lệnh sang SubBox khác không đảm bảo và phải báo không kết nối. Phản hồi tại chỗ bằng âm báo/LED, không chờ Pi mới đóng relay.
- Sau reconnect đồng bộ trạng thái hiện tại; không đọc lại một loạt câu trả lời đã hết hạn. Khởi động lại SubBox khi Pi vắng mặt phải phục hồi peer/cấu hình và điều khiển nội bộ được; không chỉ thử ngắt Pi sau khi mọi thứ đã khởi tạo.

## Pi: phản hồi và dữ liệu

- Không khởi tạo ASR hoặc mô hình hiểu lệnh để xử lý giọng nói trong cấu hình mới; từ chối đường audio uplink/voice request cũ thay vì vô tình thực thi lần hai. Giữ WebSocket xuống loa, xác thực và các chức năng app không liên quan.
- Sự kiện kết quả gồm phiên bản schema, source_subbox/source_actionbox, request/session, target_subbox/target_actionbox/channel nếu có, trạng thái thực thi, mã lỗi, trạng thái relay đã báo và thông tin follow-up có giới hạn. Không dùng cờ success do một nguồn tùy ý gửi làm chứng cứ; kiểm tra quan hệ đăng ký và tương quan với báo cáo đích khi có.
- Pi phản hồi từ dữ liệu có cấu trúc và registry; không gọi lại bộ suy luận hay gửi lại lệnh relay. Phân biệt “relay đã bật” với “tải thực sự đang hoạt động”; ACK relay không chứng minh tải chạy. Loa đích luôn là SubBox nhận câu nói, không chọn loa đầu tiên trong danh sách.
- Hàng đợi tổng hợp giọng có giới hạn, bỏ câu hết hạn; cache câu thường dùng. Chỉ khóa theo loa khi phát, không đặt speaker_busy cho cả nhà. Có thể giới hạn số tác vụ TTS để bảo vệ Pi; đo thực tế trước khi quyết định số worker. Pi bận không chặn điều khiển tại SubBox.
- Ngữ cảnh follow-up và busy theo phiên/nguồn; không để hai phản hồi hoặc ACK cũ mở lại micro sau một phiên mới.
- Lưu số đo theo thiết bị/kênh, thời điểm và chất lượng. Phân tích được lịch sử dòng, khoảng mất số liệu và dòng bất thường theo ngưỡng cấu hình; không kết luận tải chạy chỉ từ relay.
- Phần cứng hiện chưa cung cấp công suất tác dụng/điện áp đáng tin cậy; giữ W/Wh/kWh là chưa có dữ liệu. Không tính tiền điện bằng dòng × 220 V. Phân tích điện năng thực và chi phí là bước tiếp theo khi có đo công suất/điện năng đã hiệu chuẩn.

## Phạm vi thay đổi và thứ tự chuyển đổi

1. Firmware SubBox: tái dùng model/MFCC, adapter nhận PCM, task KWS có giới hạn bộ đệm, ghép từ theo phiên và nối kết quả tới command queue; sửa phụ thuộc DevConsole/WsASR để giữ kênh phát TTS riêng. Đồng bộ thư viện/build cần thiết đang có, không thêm framework nhận dạng mới.
2. Cấu hình/app/Gateway/SubBox: ánh xạ phòng + vai trò khẩu lệnh tới ActionBox/kênh, lưu bền và báo trạng thái đã áp dụng. Giữ nguyên tên và cấu hình đang có; chưa gán thì không có quyền chọn tự động.
3. Router/transport: local thực thi đúng ActionBox_V2, bỏ fallback chọn phòng khác; hoàn thiện lệnh liên SubBox có ACK, thời hạn, xác thực và chống lặp. Tôn trọng chế độ transport đang dùng; không bật hc_core hay đổi giao thức đăng ký trong lần chuyển này.
4. Gateway: nhận kết quả, xác thực, phản hồi đúng loa và theo phiên; bỏ ASR khỏi đường chạy mới. Không xóa hàng loạt mã cũ trước khi bản thay thế được kiểm chứng, nhưng đường cũ không còn hoạt động song song.
5. Dữ liệu đo: giữ việc nhận/live app, bổ sung lưu lịch sử dòng và chất lượng theo cơ chế lưu trữ sẵn có; hiển thị rõ giới hạn điện năng. Phân tích năng lượng nâng cao không gộp vào điều kiện hoàn thành điều khiển KWS.
6. Kiểm thử và chuyển thử một SubBox cùng một ActionBox đã ghép trước; sao lưu firmware/NVS và cấu hình dịch vụ. Sau khi đạt mới mở rộng, không reset thiết bị để triển khai. Khôi phục được bản Pi/SubBox trước thay đổi; ActionBox chỉ thay nếu thật sự cần phần giao thức nghe tiếp, không đổi pin/driver relay.

## Các kiểm tra phải đạt

- Host test model/MFCC parity, ghép từ/timeout/từ mâu thuẫn/nhận dạng lặp, không có wake word thì không thực thi, thêm phòng ở cuối câu không bật sớm.
- Kiểm tra ánh xạ CH1–CH3, thiếu/trùng mapping, config stale, đổi chủ, nguồn giả, ACK sai/đến trễ, request trùng, packet loss, bộ đệm đầy; không đóng sai relay.
- ActionBox_V2 regression: driver xung chốt, chống lặp, fault, đăng ký/reset, telemetry dòng độc lập trạng thái relay vẫn đúng. Không đổi sơ đồ pin hoặc bỏ bảo vệ.
- Gateway: sự kiện kết quả không gọi ASR/NLU/dispatch lệnh; đúng loa, dedup, queue đầy, timeout TTS, follow-up hết hạn và hai phòng độc lập.
- App: mapping lưu/đồng bộ, lỗi có thể hiểu được; không tự đổi cấu hình thiết bị; điều khiển tay và theo dõi dòng không hồi quy.
- Bo thật: đo thời gian suy luận so với bước 250 ms, mức dùng CPU/PSRAM, packet loss; nếu vượt ngân sách thì tối ưu hoặc giảm nhịp có kiểm chứng, không tuyên bố realtime chỉ vì biên dịch được.
- Nói đủ lệnh được hỗ trợ; kiểm tra cả ba kênh trên tải thử được người dùng xác nhận. Test không Pi từ lúc khởi động; reconnect không lặp lệnh; follow-up một lượt rồi kết thúc.
- Mô phỏng 5 SubBox gửi kết quả/telemetry/TTS đồng thời; ghi độ trễ p50/p95, queue/drop và RAM/CPU, không đặt con số năng lực giả định. Kiểm thử 5 radio thật ghi riêng nếu chưa có phần cứng.

## Quyết định giao cho triển khai và giới hạn

Tái dùng helper lưu cấu hình, transport, ACK và xác thực hiện có trước khi thêm lớp mới. Số worker, dung lượng queue, ngưỡng KWS và timeout được chọn theo phép đo và bao phủ bằng test. Ban đầu không huấn luyện model mới; ngày 26/10 người dùng đã cho phép hiệu chỉnh/huấn luyện lại 10 lớp hiện có sau khi pilot nhận sai. Phần mở rộng theo `../plans/2026-10-26-kws-model-calibration.md`. Không tự nhận model hiện có đã đủ chính xác để thương mại hóa; chưa có kết quả kiểm thử âm thanh/đa SubBox của kiến trúc mới.

## Cập nhật phạm vi 26/10/2026

Người dùng đã yêu cầu dừng huấn luyện (“tiếp tục, ko train nữa”). Giữ model gốc,
không nạp các ứng viên hiệu chỉnh và không thu thêm dữ liệu huấn luyện. Tiếp tục
hoàn thiện phần triển khai; độ chính xác giọng thật vẫn chưa đạt nghiệm thu.
