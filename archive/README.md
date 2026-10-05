# Code lưu trữ

Đợt dọn ngày 2026-09-29 chuyển nguyên thư mục, bao gồm thay đổi chưa commit và
file local. Không xóa nội dung. Các đường dẫn dưới đây tính từ gốc repository.

| Đường dẫn trước | Đường dẫn lưu trữ | Lý do |
| --- | --- | --- |
| `App/` | `archive/App/` | App Flutter ngoài ba thành phần đang phát triển |
| `Firmware/firmware_esp/Esp32S3_Master/` | `archive/Firmware/firmware_esp/Esp32S3_Master/` | Firmware thế hệ cũ |
| `Firmware/firmware_esp/shared/` | `archive/Firmware/firmware_esp/shared/` | Component dùng cho kiến trúc cũ, không được build bởi ActionBox/SubBox hiện tại |
| `Firmware/firmware_esp/components/` | `archive/Firmware/firmware_esp/components/` | Component `dtv_audio` cũ, không được build bởi ActionBox/SubBox hiện tại |
| `Firmware/firmware_esp/ActionBox/_legacy_code/` | `archive/Firmware/firmware_esp/ActionBox/_legacy_code/` | Bản triển khai cũ, nằm ngoài `src` đang build |
| `Firmware/firmware_esp/SubBox/_legacy_code/` | `archive/Firmware/firmware_esp/SubBox/_legacy_code/` | Bản triển khai cũ, nằm ngoài `src` đang build |

`manifest.json` ghi số file và SHA-256 của bảng hash từng file, đã đối chiếu
trước/sau di chuyển. 8.459 file trong sáu thư mục giữ nguyên nội dung. Hardware
(3.692 file), sound (10 file), apk (2 file) cũng được đối chiếu nguyên vẹn.
Archive làm gọn cây code hiện hành, không nhằm giảm dung lượng đĩa.

## Phụ thuộc được giữ

`Audio_Hardware_Test` vẫn cần đúng bản ESP-SR/ESP-DSP trong
`archive/Firmware/firmware_esp/Esp32S3_Master/managed_components/`.
CMake của bài test đã trỏ tới vị trí này; không xóa toàn bộ archive nếu còn dùng
bài test phần cứng. ActionBox có các component ESP-SR/ESP-DSP riêng trong
`ActionBox/components/`, được giữ nguyên.

`MQTT_Server` được giữ tại vị trí cũ vì cung cấp broker; không tách subscriber/
database khỏi compose trong đợt này. `Audio_Hardware_Test`, tool kiểm tra,
binary firmware, PCB, âm thanh, APK và tài liệu thiết kế vẫn nằm tại vị trí cũ.

## Khôi phục

1. Dừng build hoặc ứng dụng đang dùng thư mục tương ứng.
2. Di chuyển thư mục trong cột lưu trữ về đúng cột đường dẫn trước; không ghi đè
   nếu tại đích đã có code mới.
3. Nếu khôi phục `Esp32S3_Master`, đổi hai đường dẫn ESP-SR/ESP-DSP trong
   `Firmware/firmware_esp/Audio_Hardware_Test/CMakeLists.txt` về
   `../Esp32S3_Master/managed_components/...`.
4. Tạo lại build/cache khi dùng code đã di chuyển vì chúng có thể lưu đường dẫn
   tuyệt đối cũ. Cache và các file bị `.gitignore` loại trừ chỉ được giữ local.

## Tối ưu code hiện hành

- Gateway tạo bảng chuyển dấu một lần khi import, thay vì mỗi lần gọi `slug`.
- EdgeTTS ghép chunk bằng `bytearray`, trả về `bytes` như trước, tránh chép lại
  toàn bộ audio mỗi khi nhận thêm chunk.
- SubBox chuyển quyền sở hữu chuỗi qua các bước chuẩn hóa, tránh sao chép cả
  câu cho từng ký tự tiếng Việt trong bảng chuyển đổi.
- ActionBox dùng chung nhánh xử lý LED nhấp nháy; giữ chu kỳ 500/100 ms.
- Script build/flash chọn project bằng đường dẫn của chính script và trả lỗi
  khi lệnh ESP-IDF thất bại.

Giao thức mạng, GPIO, ngưỡng bảo vệ relay, model và dữ liệu runtime không đổi.

## Kết quả kiểm tra

- ActionBox và SubBox: build thành công bằng ESP-IDF 6.0.2 từ thư mục gốc repo.
- Gateway Intent Engine: 84/84 kiểm tra đạt.
- `test_runtime_utils.py`: 5/5 test đạt, gồm thứ tự chunk, kiểu `bytes`, retry
  sau stream lỗi và chuẩn hóa tên; test cũng đạt trên logic trước tối ưu.
- `slug`: 1.002 đầu vào đối chiếu có cùng kết quả. Microbenchmark cục bộ, trung
  vị 5 lượt (mỗi lượt 10 lần duyệt bộ đầu vào), giảm từ khoảng 0,1122 s xuống
  0,0768 s, tương đương 1,46 lần. Đây không phải số đo tốc độ toàn hệ thống.
- Python compile và cú pháp bốn script PowerShell hợp lệ.
- Các đường dẫn component của `Audio_Hardware_Test` tồn tại sau di chuyển;
  chưa build lại bài test phần cứng này.
- Chưa flash firmware hoặc kiểm thử trên thiết bị thật.
