# Kiểm tra thiết bị động trong luồng giọng nói — 28/10/2026

Đây là baseline trước sửa. Mapping loại, lưu alias, hotwords Core và confidence
đã được sửa, triển khai và kiểm tra tiếp trong
[báo cáo 29/10](../device-config-response-2026-10-29/README.md).
Các kết quả bên dưới giữ nguyên để ghi lại lỗi tại thời điểm chẩn đoán.

Kết luận: phần phân giải đích đọc tên/binding Core mới mỗi lần, nhưng luồng
app → đồng bộ → ASR → lệnh chưa hoàn chỉnh cho thiết bị tùy chỉnh. Không thể
khẳng định đổi “Đèn bể cá” thành “Máy pha cà phê” trên app rồi nói là chạy ổn.

## Cách kiểm tra

- Đọc luồng sửa kênh đang được provider GatewaySmartHomeRepository sử dụng,
  Firebase RPC, CoreCommissioning, SpeakerVoice/CoreVoice và ASREngine.
- Chỉ đọc Pi 192.168.11.29; bốn file ASR/Core voice/commissioning có SHA-256
  trùng repo. Core hiện có Relay 1/light, Relay 2/fan và Relay 3/light.
- Chạy probe với Registry/commissioning/voice thật trên SQLite tạm; mọi model
  ASR/TTS và thiết bị/radio là mock. Không sửa thiết bị thật hoặc gửi MQTT.
- Các assert của probe qua khi chạy ngoài môi trường giới hạn. Lượt chạy đầu
  bị treo tại asyncio Runner shutdown; đã dừng riêng probe và chạy lại có timeout.
- results.json ghi kết quả hiện trạng; repro.py là probe chẩn đoán, không phải
  regression yêu cầu giữ các lỗi đã tìm thấy.

## Kết quả

| Trường hợp | Kết quả hiện tại |
| --- | --- |
| “bật đèn bể cá” trước đổi tên | Chọn đúng logical device |
| Gửi loại `den` theo màn sửa kênh app | Core trả invalid_device_type; tên cũ giữ nguyên |
| Đổi riêng tên thành máy pha cà phê, giữ loại light | “bật đèn” vẫn chọn được máy pha cà phê |
| Đổi tên và loại canonical custom/other | “bật/tắt máy pha cà phê” chọn đúng kênh ở mức text |
| Gọi lại “đèn bể cá” sau đổi đúng tên/loại | voice_no_target; không chọn thiết bị mới |
| Gọi “máy cà phê”, thêm đuôi phòng hoặc “giúp mình” | Chưa khớp; voice_no_target |
| Gửi trường ch1_aliases vào Core RPC | invalid_input |
| ActionBox mới chưa gán thiết bị | Không có đích điều khiển |
| ActionBox mới đã gán CH2 cùng phòng/SubBox | Mic cũ chọn đúng CH2 bo mới; tạo command ACCEPTED trong DB thử |
| Mic trên chính ActionBox mới | Phân giải được tên đã gán |
| Hai thiết bị trùng tên | voice_ambiguous; không tự chọn |
| ASR đã trả đúng text cà phê, thời lượng 5 s, RMS 0,025 | Heuristic cho 0,65; Core yêu cầu ≥0,7 nên low_confidence |
| Cùng thông số nhưng text “bật đèn” | Heuristic cho 0,80 |

ACCEPTED trong probe là hàng đợi mô phỏng, không phải APPLIED hoặc kiểm chứng
relay/tải thật. Kết quả confidence là phép tính trong code, không phải xác suất
hiệu chuẩn từ model và không phải kết quả nhận giọng người thật mới.

## Những phần thiếu/sai đã xác định

1. `App/HomeCompetition/lib/repositories/smart_home_repository.dart:updateChannel`
   gửi den/quat/o_cam; loại tùy chỉnh rơi vào den. Core chỉ nhận light/fan/outlet
   hoặc custom/other/switch/pump. `updateDevice` có mapping tương tự.
2. Trường voiceAliases được nhập trong dialog nhưng updateChannel không đưa
   vào request. Core update_device cũng chưa nhận/lưu alias; CoreVoice chỉ
   so khớp tên chính và ba loại light/fan/outlet.
3. Heuristic ASR thưởng danh sách keyword cố định. Tên thiết bị mới đúng vẫn
   có thể bị từ chối vì thiếu keyword thứ hai. Không nên sửa bằng hạ ngưỡng
   chung hoặc suy đoán câu không rõ để bật tải.
4. ASR đọc hotwords từ RegistryManager cũ; chọn đích lại đọc Core SQLite.
   Không có cầu nối cập nhật tên/alias Core sang nguồn hotwords này. Tên
   Relay 1/2/3 đang có trong Core cũng không xuất hiện trong hotwords.txt.
5. Parser hiện là bật/tắt + tên chính khớp sau chuẩn hóa dấu/hoa thường.
   Chưa tách riêng phòng, từ lịch sự hoặc quản lý câu nối tiếp “tắt nó đi”.

## Điều kiện để hoàn thiện

- Sửa mapping loại trên app và giữ loại khác khi thay tải; đừng biến coffee
  maker thành light. Sửa cả caller cập nhật thiết bị lẫn cập nhật kênh.
- Dùng tên/alias và room scope Core làm nguồn chung cho ASR và resolver;
  cập nhật theo phiên bản, bỏ tên/alias cũ sau khi thay tải.
- Chấm độ tin cậy không thiên về loại tải; kiểm tra text đích/ủy quyền riêng.
- Sau cấu hình cần đợi Box xác nhận revision. Khi nhiều thiết bị trùng/giống
  tên phải hỏi lại, không chọn đích ngẫu nhiên.
- Sau sửa cần kiểm tra thật qua Firebase/app, giọng người, ACK và phản hồi;
  probe hiện tại không thay các bước đó.

Chưa chỉnh code sản phẩm, chưa đổi cấu hình thật, chưa train hoặc thay model.
