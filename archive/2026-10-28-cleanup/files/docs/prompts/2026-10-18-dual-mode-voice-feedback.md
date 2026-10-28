# Prompt đã chọn lọc: điều khiển giọng nói hai chế độ và phản hồi người dùng

Ngày đối chiếu: 18/10/2026. Nguồn: bản đang sửa trong `/home/tuan/Home-Assistant-IoT-`, cùng log phần cứng/Pi4. Đây là yêu cầu triển khai cho bước tiếp theo, không phải tuyên bố các tính năng dưới đây đã hoàn thành.

## Những điều chỉnh so với prompt gốc

| Nội dung | Điều chỉnh theo hệ thống hiện tại |
|---|---|
| Kiến trúc ba tầng | Giữ: ActionBox V2 thu âm và điều khiển 3 relay; SubBox điều phối phòng/phát loa; Pi4 chạy ASR và quản lý cấu hình. |
| “Model nhận dạng 7 từ” | Sửa thành 10 lớp theo `labels.json`: 8 từ, gồm cả `bếp`, cộng `noise` và `unknown`. Giữ nguyên thứ tự đầu ra model. |
| Tích hợp KWS | Chỉ chuyển phần DSP/inference từ firmware thử nghiệm sang ESP-IDF. GPIO của bản thử nghiệm xung đột relay V2; không nạp nguyên bản đó lên PCB hiện tại. |
| Wake word “Ori” | Chưa coi là có sẵn. Bản production đang dùng WakeNet `wn9_hiesp`; thay wake word là công việc riêng cần model và kiểm thử. |
| Phản hồi người dùng | Đưa thành hạng mục chính: lời nói online, clip offline, chime/LED, trạng thái trên app; nội dung dựa trên kết quả thực thi. |
| Luồng loa hiện có | `voice_reply` đang được ghi log; SubBox chủ yếu phát chime. Không đồng nhất việc có TTS trên Pi với việc SubBox đã đọc được câu trả lời. |
| Core V1 | Có mã nguồn nhưng Pi đang chạy gateway legacy; unit `home-competition-core.service` chưa được cài ở lần kiểm tra. Chốt đường triển khai và provisioning trước khi mở rộng giao thức. |
| IR, liên phòng offline, AEC | Đưa ra ngoài bản đầu khi chưa có driver/route/playback reference được kiểm chứng. |
| Thứ tự thực hiện | Hoàn thiện NORMAL + phản hồi trước; KWS chạy quan sát không điều khiển; sau đó LOCAL và failover; EMERGENCY_LOCAL cuối cùng, mặc định tắt. |

## Prompt dùng để triển khai

Hãy phát triển tính năng điều khiển giọng nói tiếng Việt trên repository Home Competition hiện tại. Tái sử dụng code đang chạy, triển khai từng phần có thể build và kiểm thử độc lập. Mục tiêu là điều khiển được thiết bị khi Pi4 hoạt động, có điều khiển cơ bản khi Pi4/ASR mất kết nối, và luôn phản hồi cho người dùng đúng với điều hệ thống đã xác nhận.

### 1. Audit đúng nguồn và đúng phần cứng

- Dùng bản đang sửa ở repo chính theo lựa chọn của người dùng; ghi commit, diff và hash model/artifact. Giữ nguyên thay đổi đang có của người dùng.
- Đọc `Firmware/firmware_esp/ActionBox_V2`, `Firmware/firmware_esp/SubBox`, `Firmware/firmware_esp/common/hc_core`, `Firmware/firmware_kws`, `Gateway/gateway` và các test liên quan.
- ActionBox hiện tại: ESP32-S3, flash 16 MB, PSRAM 8 MB, INMP441 và 3 relay latching. Tái sử dụng `board_pins.h`, driver relay, BL0942, provisioning và OTA hiện có.
- Microphone production dùng BCLK=47, WS=48, DIN=8. Bản KWS thử nghiệm dùng BCLK=15, WS=16, trùng hai chân coil relay 1; còn GPIO4/5 trùng coil relay 3. Không sao chép GPIO, cách đóng relay active-low hoặc Arduino `main` từ bản KWS thử nghiệm.
- SubBox không có microphone trong thiết kế này. Loa thuộc SubBox; không giả định ActionBox có thể đọc thông báo.
- Phân biệt gateway legacy đang triển khai với Core V1 trong repo. Lập bảng transport, identity, pairing, quyền điều khiển và command dispatcher thực sự được dùng. Không để cả hai đường cùng thực thi một lệnh.
- Việc SubBox khôi phục Wi-Fi/MQTT bằng cấu hình NVS cũ không thay thế enrollment, quyền điều khiển hay khả năng tương thích Core V1. Không hạ yêu cầu xác thực để làm demo chạy.
- Kênh BL0942 số 3 của ActionBox `28:84:85:33:DD:E8` còn lỗi đọc trong log; không dùng dữ liệu lỗi/cũ làm bằng chứng tải hoạt động. Xác minh lại tình trạng khi bắt đầu triển khai.

### 2. Phạm vi phiên bản đầu

**NORMAL:** ActionBox phát hiện wake word, thu PCM → ESP-NOW → SubBox → ASR tiếng Việt trên Pi4 → intent được kiểm tra quyền → dispatcher hiện có → SubBox → đúng relay → kết quả → phản hồi trên loa SubBox và app.

**LOCAL:** Khi dịch vụ Gateway/ASR không khả dụng nhưng SubBox và ActionBox còn kết nối, ActionBox chạy KWS và gửi keyword events; SubBox ghép lệnh, tra cấu hình cục bộ, thực thi và phát clip phản hồi. Mặc định chỉ các thiết bị trong phòng có ánh xạ duy nhất và quyền offline hợp lệ.

**EMERGENCY_LOCAL:** Chỉ triển khai sau LOCAL. ActionBox mất SubBox chỉ được điều khiển relay của chính nó với cấu hình đã xác thực và quyền explicit opt-in. Mặc định tắt, không điều khiển liên phòng hoặc gửi sang ActionBox khác. Chỉ báo bằng LED theo phần cứng thật.

Không thêm IR vào bản đầu nếu chưa xác minh driver, chân phát và mã điều khiển. Không hứa điều khiển liên phòng khi chưa có route và quyền đã kiểm thử. CoreVoice hiện giới hạn nguồn/thiết bị theo parent/phòng; mở rộng phạm vi phải là thay đổi quyền rõ ràng.

### 3. Tái sử dụng pipeline âm thanh và KWS

- Giữ audio capture, WakeNet, VAD, pre-roll và ESP-NOW audio transport hiện có; audit phần thiếu trước khi viết lại. Baseline PCM signed 16-bit mono 16 kHz = 32.000 byte/s, chưa tính overhead.
- Một nguồn micro được chọn cho mỗi phiên trong phòng. SubBox phân xử wake events bằng confidence và chất lượng âm thanh nếu có, không chỉ RSSI. Không cho hai ActionBox cùng phát sinh hai lệnh từ một câu nói.
- Audio packet có session, sequence và thông tin phát hiện thiếu gói; buffer/queue có giới hạn, timeout, hủy phiên và quyền sở hữu bộ nhớ rõ ràng. Relay/heartbeat được ưu tiên hơn audio.
- KWS lấy model và preprocessing từ `Firmware/firmware_kws`. Thứ tự lớp phải là `bật, bếp, khách, ngủ, noise, phòng, quạt, tắt, unknown, đèn`; không tự đổi chỉ số.
- Đối chiếu MFCC với pipeline huấn luyện: 16 kHz, cửa sổ 1 giây, bước 250 ms, frame 320 mẫu, hop 160, FFT 512, 32 mel, 13 MFCC, 99 frames; normalization lấy từ `models/norm_params.json`.
- Backend C++ hiện dùng trọng số INT8 nhưng vẫn có activation/tính toán float. Đo toàn bộ RAM, scratch buffers và CPU; không gọi đây là inference thuần số nguyên hoặc mặc định dùng TFLite.
- Kiểm tra output parity trên cùng bộ mẫu giữa Python và ESP32-S3. Model ONNX có thể kèm external weights; tính đủ kích thước artifact, không chỉ file `.onnx`.
- Ngưỡng confidence 0,40 và cooldown 500 ms trong prototype chỉ là cấu hình thử nghiệm. Chọn ngưỡng từ dữ liệu thật, gồm tiếng quạt/TV/loa, giọng khác nhau và câu ngoài tập từ.
- Đánh giá riêng từ đơn và từ trong câu liên tục. Số liệu trong `quantization_report.json` là kết quả cũ, không phải benchmark trên PCB hiện tại.
- Không thay model custom bằng MultiNet tiếng Anh. Không tạo inference giả để đánh dấu hoàn thành. Chỉ thêm interface/backend khi thực sự cần cho tích hợp hiện tại.

### 4. Parser cục bộ và quyền thực thi

- SubBox nhận keyword event có source, session, sequence, keyword ID, confidence, thời gian tương đối, model version và mode epoch, theo schema tương thích giao thức đang dùng.
- FSM chờ hết câu/VAD hoặc cửa sổ hoàn tất có kiểm chứng rồi mới dispatch. Không bật “đèn” ngay khi nhận `bật đèn` nếu người dùng còn đang nói `phòng ngủ`.
- Hỗ trợ các thứ tự từ đã có test, ví dụ `bật đèn phòng khách` và `phòng khách bật đèn`. Có thể dùng phòng hiện tại khi tên thiết bị ánh xạ duy nhất.
- Lọc lặp keyword do cửa sổ chồng nhau; từ thiếu, lệnh bật/tắt mâu thuẫn, confidence thấp hoặc nhiều đích phù hợp phải từ chối/hỏi lại. Không ghép keyword từ hai người hoặc hai session.
- `noise` và `unknown` không phải intent. Alias/tên tùy ý chỉ được dùng offline nếu model/grammar thực sự nhận dạng được. Không hỏi người dùng nói một tên mà LOCAL không thể hiểu.
- Câu phủ định như “đừng bật đèn”, “không bật quạt” có thể bị KWS rút thành lệnh khẳng định. Bắt buộc có bộ kiểm thử phủ định/ngoài tập từ và cơ chế từ chối phù hợp. Nếu model không phân biệt được thì chưa mở điều khiển tự động bằng câu tự nhiên; phải giới hạn cách nhập hoặc bổ sung nhận dạng phù hợp.
- Đặt trạng thái `SET_ON/SET_OFF`, giữ giới hạn/safety của driver latching. Không dùng `TOGGLE` cho retry bằng giọng nói.
- Cấu hình offline gồm identity ổn định, room, device, channel, quyền, version và chính sách hết hạn. Đồng bộ có xác thực, kiểm tra đầy đủ rồi commit nguyên tử. Không ghi NVS theo từng keyword/heartbeat.
- Khi offline không thể nhận quyền vừa bị thu hồi trên Gateway; phải thiết kế chính sách độ cũ tối đa/thu hồi và công bố giới hạn. Thiếu cấu hình hoặc quyền hợp lệ thì không thực thi.

### 5. Phản hồi người dùng — yêu cầu bắt buộc

Một phiên có trạng thái xuyên suốt: **đang nghe → đang xử lý → chờ thiết bị → kết quả → phản hồi đã phát hoặc lỗi phát**. Kết quả điều khiển và kết quả phát âm thanh là hai trạng thái riêng.

| Tình huống / bằng chứng | Phản hồi đề xuất | Điều kiện |
|---|---|---|
| Wake được chấp nhận | Chime ngắn + LED nghe | Không đọc câu dài che mất đầu câu người dùng. |
| Chưa có kết quả, xử lý lâu | “Mình đang xử lý.” hoặc “Đang chờ thiết bị xác nhận.” | Chỉ phát khi vượt ngưỡng UX có cấu hình; tối đa một lần mỗi giai đoạn. |
| Chỉ nhận ACK / ACCEPTED | Giữ trạng thái chờ | Không phát thông báo thành công. |
| Relay báo APPLIED, trạng thái đúng | “Đã đặt đèn phòng khách sang bật.” | Xác nhận ở cấp relay; không suy ra bóng đèn/tải vật lý đang chạy. |
| Có telemetry hợp lệ, mới và tiêu chí xác minh tải đạt | “Đèn phòng khách đã bật.” | Chỉ dùng mức xác nhận tải khi cảm biến và tiêu chí đủ tin cậy. |
| Relay đã đổi nhưng không xác minh được tải | “Relay đã bật; chưa xác nhận được tải.” | App hiển thị trạng thái relay và trạng thái tải riêng. |
| Trạng thái đã đúng trước lệnh | “Đèn đang ở trạng thái bật.” | Nêu đúng cấp bằng chứng; tránh tạo xung relay thừa. |
| Thiếu tên / nhiều thiết bị phù hợp | “Bạn muốn điều khiển đèn nào?” | NORMAL có thể mở lượt làm rõ có timeout; LOCAL chỉ hỏi trong vốn từ hỗ trợ, nếu không thì từ chối rõ ràng. |
| Không hiểu / confidence thấp | “Mình chưa nghe rõ. Bạn nói lại giúp nhé.” | Không thực thi. |
| Thiết bị chưa đăng ký / không có quyền | “Thiết bị này chưa được phép điều khiển.” | Không thử đường legacy để vượt qua từ chối. |
| Thiết bị mất kết nối, chưa gửi lệnh | “Thiết bị đang mất kết nối.” | Nêu rằng lệnh chưa được gửi nếu biết chắc. |
| Đã gửi nhưng timeout / mất kết quả | “Chưa xác nhận được trạng thái thiết bị.” | Không nói “chưa thực hiện” khi có thể đã thực hiện; không tự gửi lại thành lệnh mới. |
| Thực thi thất bại có kết quả rõ ràng | “Thiết bị chưa thực hiện được lệnh.” | App giữ mã lỗi chi tiết để chẩn đoán. |
| Chuyển LOCAL | “Đang dùng điều khiển cục bộ trong phòng.” | Một lần khi đổi trạng thái, có debounce/rate limit. |
| Gateway phục hồi | “Đã kết nối lại hệ thống trung tâm.” | Chỉ sau khi health ổn định; không phát lại lệnh cũ. |
| IR, nếu triển khai sau | “Đã gửi tín hiệu đến điều hòa.” | Không xác nhận điều hòa đã bật nếu không có phản hồi từ thiết bị. |

**Online:** Tái sử dụng `Gateway/gateway/tts_engine.py`, đặc biệt `synthesize_pcm(..., sample_rate=16000)` và cache hiện có. Chuẩn hóa đầu ra 16 kHz mono signed 16-bit; không chuyển thẳng âm thanh 24 kHz vào playback 16 kHz. Gateway gửi kết quả có cấu trúc và text trước; âm thanh đi theo kênh được xác thực/có thương lượng capability. Chỉ báo `speaker=true` sau khi đường nhận/phát PCM thực sự hoạt động.

**Offline:** SubBox dùng tập clip tiếng Việt cố định cho thành công, không hiểu, thiếu quyền, thiết bị offline và timeout. Chỉ hỗ trợ tên phòng/thiết bị có clip phù hợp; nếu chưa có thì dùng câu chung trung thực. Có manifest version/hash, giới hạn dung lượng, cập nhật nguyên tử; không buộc ESP32 chạy TTS tiếng Việt. Không ghi audio cache đè phân vùng OTA/model/NVS. Nếu chưa có clip hoặc loa lỗi, dùng chime/LED và trạng thái app khi còn kết nối.

**Tích hợp code hiện tại:**

- `SubBox/src/audio/asr/ws_asr.cpp` đang log `voice_reply` rồi chọn SUCCESS/ERROR chime; `pending` hiện rơi vào nhánh ERROR. Sửa phân loại kết quả trước khi thêm lời nói.
- Tái sử dụng `SoundPlayer`, `playPcm`, `isPlaying`; audit ownership/lifetime và giới hạn queue. Playback có chunk/buffer hữu hạn và không chặn relay/network task.
- `Gateway/gateway/core_v1/voice.py` đã phân biệt APPLIED, pending, timeout; giữ semantics này. `core_v1/__main__.py` hiện truyền `tts=None`; không coi Core đã có TTS end-to-end chỉ vì còn module TTS legacy.
- Mỗi phản hồi gắn với session/command, response ID, mode epoch, target, kết quả và mức bằng chứng. Dùng lại correlation ID có sẵn; chỉ thêm trường thiếu. Dedup phản hồi độc lập với dedup thực thi.
- Có trạng thái phát `queued/playing/completed/failed/cancelled` hoặc tương đương. ACK nhận dữ liệu không có nghĩa người dùng đã nghe xong. Lỗi loa/TTS không được gây thực thi lại relay.
- Kết quả muộn sau timeout: cập nhật trạng thái app với thời điểm/correlation phù hợp; không phát lời thành công cũ xen vào phiên mới. Không thay kết quả cuối cùng bằng một ACK cũ.
- Ưu tiên thông báo lỗi cần thiết, giới hạn độ dài/âm lượng/tần suất; không đọc tên thiết bị/SSML hoặc URL tùy ý thành nội dung điều khiển không kiểm tra.
- Khi loa SubBox phát, thông báo trạng thái playback cho các ActionBox trong phòng và tạm khóa wake/KWS thực thi, có thời gian đuôi và timeout tự gỡ khóa. Không coi đây là AEC; không hứa vừa nói vừa ngắt lời nếu chưa kiểm thử.
- Không để clip “đã bật đèn” tự kích hoạt lệnh mới. Kiểm thử cả thông báo playback bị mất và loa dừng đột ngột; mọi khóa nghe phải tự hết hạn.
- App hiển thị cùng kết quả/cấp xác minh với loa. Khi mất Pi, không tuyên bố app từ xa cập nhật realtime nếu chưa có đường kết nối thực tế.

### 6. Mode manager, giao thức và phục hồi

- SubBox quyết định NORMAL/LOCAL/RECOVERING của phòng; ActionBox chỉ tự vào EMERGENCY_LOCAL khi mất SubBox và được cấp quyền.
- Health gồm Gateway reachable, ASR ready, queue có khả năng tiếp nhận và audio-session acceptance; ping/HTTP 200 đơn lẻ không chứng minh ASR dùng được.
- Giá trị khởi đầu để thử: heartbeat 2 giây, mất 3 lần mới xét LOCAL, health ổn định 10 giây mới trở lại NORMAL. Đây là cấu hình đề xuất, không phải số đo hay bảo đảm thời gian failover.
- Mỗi session có đúng một execution authority và epoch. Gateway hồi phục không giành quyền phiên LOCAL đang chạy. Kết thúc/hủy phiên rõ ràng trước khi đổi chủ.
- Không tự fallback một lệnh đang ở trạng thái “không biết đã thực thi hay chưa”. Muốn tiếp tục cùng phiên phải có bằng chứng chưa thực thi hoặc dedup dùng chung bảo đảm không lặp; nếu thiếu thì báo chưa xác nhận.
- Tái sử dụng `hc_protocol`, `hc_runtime`, protocol/dispatcher hiện có. Phân biệt protocol legacy và Core bằng version/capability thật; không copy ví dụ JSON `protocol_version:3` thành một giao thức thứ ba.
- Bổ sung tối thiểu schema cho KWS, mode, health và feedback còn thiếu. Có packet length validation, auth/trusted peer, replay protection, seq, deadline, retry hữu hạn và command dedup. Không dùng đồng hồ wall-clock của các ESP làm thời gian đã đồng bộ; dùng thời gian đơn điệu/tương đối và epoch khởi động phù hợp.
- Kiểm tra kênh Wi-Fi/ESP-NOW khi router tắt/khởi động lại. LOCAL phải hoạt động trên kênh đã thống nhất; không đổi kênh tùy tiện hoặc giả định ESP-NOW luôn còn kết nối.
- Giữ safety, nút vật lý, OTA rollback và trạng thái boot an toàn. Tác vụ KWS/TTS không chặn relay, không tắt watchdog để che lỗi.

### 7. Thứ tự thực hiện và nghiệm thu

1. **Chốt baseline:** đối chiếu code/deployment/config/quyền, kiểm tra stack và telemetry; lập danh sách đã có/thiếu. Chuẩn bị rollback, giữ dữ liệu NVS và registry.
2. **NORMAL + phản hồi hoàn chỉnh:** một micro → ASR → đúng đích → kết quả thực thi → tiếng nói SubBox + app. Test riêng pending, timeout, không quyền, TTS/loa hỏng và phản hồi muộn.
3. **KWS quan sát:** port DSP/inference vào ActionBox production, chưa cho điều khiển tải. Đo parity, false accept, câu phủ định, stack/heap/CPU và độ chính xác câu liên tục.
4. **LOCAL trong một phòng:** parser, mapping có quyền, clip offline, arbitration hai ActionBox và dedup. Chỉ bật điều khiển sau khi đạt tiêu chí đã định.
5. **Failover/recovery:** lỗi ASR khi mạng vẫn còn, mất Pi/router, đổi kênh, mất gói/ACK, reboot giữa lệnh, phục hồi giữa phiên; không thực thi trùng hoặc báo thành công sai.
6. **EMERGENCY_LOCAL opt-in:** chỉ relay nội bộ được cấp quyền, cấu hình không cũ/lỗi, LED đúng trạng thái. IR/liên phòng offline/AEC/codec mới là hạng mục tiếp theo nếu có nhu cầu và bằng chứng.

Mỗi bước có thay đổi nhỏ, test logic và build tương ứng. Mock chỉ kiểm tra logic; nghiệm thu âm thanh, relay, failover và hiệu năng cần số đo trên phần cứng thật. Không đánh đồng kết quả build với hệ thống đã chạy end-to-end.

Ghi benchmark tái lập: phiên bản model/config, số mẫu, môi trường, p50/p95 thời gian từ kết thúc câu đến kết quả và đến lúc bắt đầu phản hồi; KWS inference/false accept/false reject, mất gói, failover/recovery, stack high-water mark, heap/PSRAM, CPU và thời gian chạy liên tục. Chỉ đặt ngưỡng nghiệm thu sau baseline, không điền số đẹp chưa đo.

Bộ nghiệm thu phải có hai micro cùng nghe, hai người nói đồng thời, câu thiếu đích, nhiều đèn, câu phủ định, clip phát tự kích hoạt, loa lỗi, ACK trùng/muộn, config lệch version, thiết bị chưa đăng ký, cảm biến stale/invalid và reboot/OTA gián đoạn. Không tự bật tải điện thật để thử nếu chưa xác định tải và điều kiện thử phù hợp.

Kết quả bàn giao: file thay đổi; architecture/schema thực sự dùng; cách build/flash/provision và rollback; cách cấu hình quyền LOCAL/EMERGENCY_LOCAL; bảng câu phản hồi theo kết quả; log/test/benchmark thật; các giới hạn và hạng mục chưa hoàn thành. Tuyệt đối không báo “hoàn thành toàn diện” khi mới có firmware boot, ASR text hoặc ACK relay.
