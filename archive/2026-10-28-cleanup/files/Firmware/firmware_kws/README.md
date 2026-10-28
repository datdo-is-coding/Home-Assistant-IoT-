# Dự Án Nhận Diện Từ Khóa (Keyword Spotting - KWS) Cho ESP32-S3

Dự án phát triển mô hình TinyML Keyword Spotting (KWS) tiếng Việt offline, gọn nhẹ để triển khai trực tiếp trên chip vi điều khiển **ESP32-S3** theo quy trình chuẩn của **Edge Impulse**.

---

## 📁 Cấu Trúc Dự Án

- 📂 [dataset/](file:///d:/KWS/dataset): Chứa toàn bộ **3,543 files WAV** chuẩn hóa (16kHz, 16-bit PCM, Mono, 1.0s) gồm 10 lớp:
  - 8 từ khóa: `bật` (375), `tắt` (355), `đèn` (395), `quạt` (352), `phòng` (344), `khách` (336), `bếp` (355), `ngủ` (343).
  - 2 lớp chống kích hoạt nhầm: `noise` (360), `unknown` (328).
- 📂 [scripts/](file:///d:/KWS/scripts):
  - 📄 [preprocess_dataset.py](file:///d:/KWS/scripts/preprocess_dataset.py): Script làm sạch, loại bỏ file hỏng, resample và căn chỉnh thời lượng 1.0s.
  - 📄 [generate_noise_dataset.py](file:///d:/KWS/scripts/generate_noise_dataset.py): Script tải và tổng hợp dữ liệu tiếng ồn (ESC-50 + tạp âm phòng/phần cứng).
  - 📄 [generate_unknown_dataset.py](file:///d:/KWS/scripts/generate_unknown_dataset.py): Script tổng hợp 328 mẫu giọng nói tiếng Việt đa dạng ngoài 8 từ khóa.
- 📂 [firmware/](file:///d:/KWS/firmware): Dự án PlatformIO hoàn chỉnh cho **ESP32-S3**:
  - 📄 [platformio.ini](file:///d:/KWS/firmware/platformio.ini): Cấu hình board `esp32-s3-devkitc-1`, 240MHz, Flash 80MHz, cờ tối ưu `-O3`.
  - 📂 [include/](file:///d:/KWS/firmware/include):
    - [model_data.h](file:///d:/KWS/firmware/include/model_data.h): Mô hình lượng tử hóa INT8 (28 KB).
    - [kws_config.h](file:///d:/KWS/firmware/include/kws_config.h): Sơ đồ chân I2S (SD: GPIO 4, SCK: GPIO 5, WS: GPIO 6) & ngưỡng nhận diện.
    - [mfcc.h](file:///d:/KWS/firmware/include/mfcc.h): Khối trích xuất MFCC on-device thời gian thực.
  - 📂 [src/](file:///d:/KWS/firmware/src):
    - [main.cpp](file:///d:/KWS/firmware/src/main.cpp): Đọc I2S DMA, cửa sổ trượt 250ms, State Machine nhận diện chuỗi lệnh nhà thông minh.
    - [mfcc.cpp](file:///d:/KWS/firmware/src/mfcc.cpp): Giải thuật FFT 512 + Mel Filterbank + DCT-II tối ưu.

---

## 🚀 Trạng Thái Dự Án Hiện Tại
- ✅ **Giai đoạn 1 (Làm sạch & Chuẩn hóa Dataset)**: Đã hoàn thành 100% (3,543 files).
- ✅ **Giai đoạn 2 (Trích xuất MFCC DSP)**: Hoàn tất trích xuất đặc trưng `(3543, 99, 13)`.
- ✅ **Giai đoạn 3 & 4 (Huấn luyện & Lượng tử hóa INT8)**: Hoàn thành (Test Acc: **80.56%**, Rejection noise/unknown > 91-98%).
- ✅ **Giai đoạn 5 (Dự án Firmware PlatformIO cho ESP32-S3)**: **Đã khởi tạo và biên dịch thành công 100% [SUCCESS]**!
  - RAM sử dụng: **62.3%** Internal SRAM (không cần PSRAM).
  - Flash sử dụng: **9.0%** (301 KB).

## Hiệu chỉnh model từ micro thật

`python scripts/calibrate_model.py --manifest /absolute/path/manifest.json --output /absolute/path/new-candidate`
chạy bằng môi trường có `torch`, `numpy` và `g++`. Script tái dùng `TinyKWS`, MFCC C++
của firmware và checkpoint gốc; ghi ứng viên vào thư mục mới, không thay header
đang dùng hoặc nạp thiết bị. Không chạy script exporter ONNX cũ để tạo scalar-header.

Manifest là JSON array; mỗi file WAV PCM16/mono/16kHz chứa **một từ có thể lặp lại**,
hoặc mẫu `noise`/`unknown` được xác nhận:

```json
[
  {"path": "train/bat-01.wav", "label": "bật", "split": "train"},
  {"path": "validation/bat-02.wav", "label": "bật", "split": "val"},
  {"path": "test/bat-03.wav", "label": "bật", "split": "test"}
]
```

Đường dẫn WAV tương đối với manifest. Chia theo toàn phiên trước khi trích cửa sổ;
script từ chối file có cùng nội dung được dùng lại. Không gán nhãn theo dự đoán
của model đang lỗi. Bản ghi thiếu/không rõ từ phải để ngoài tập học.

Ứng viên gồm `candidate.pt`, `candidate.h`, `report.json`. Checkpoint được chọn bằng
validation, không bằng test. Nếu chưa có mic validation/test, báo cáo chỉ chứng minh
fit dữ liệu train và giữ test gốc; **không đủ điều kiện nạp ứng viên**. Metrics theo
cửa sổ không thay thế tỷ lệ đúng cả câu và kiểm tra không ra lệnh trên âm nhiễu.
Cần đánh giá thêm câu mới, sai hành động/phòng, negative sessions, parity C++ INT8
và timing trên bo trước khi bật binding.

Kiểm tra exporter và chống rò rỉ phiên:
`python -m unittest Firmware.tests.test_kws_training` từ thư mục gốc repo,
trong môi trường huấn luyện. Thiếu Torch thì test được skip, không phải pass parity.

Tập học bổ sung các đoạn từ riêng, dịch vị trí và gain 0,5/1/2 từ cùng phiên train.
Validation/test không lọc bỏ phiên nói nhỏ: mỗi phiên chấm một cửa sổ năng lượng lớn
nhất; báo cáo này vẫn phải đi kèm replay cả phiên để phát hiện lệnh sai/bỏ sót từ.
