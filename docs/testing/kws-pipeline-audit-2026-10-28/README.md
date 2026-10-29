# Đối chiếu KWS độc lập và SubBox — 2026-10-28

## Kết luận

Hai bản đang dùng cùng model INT8 và cùng phép tính MFCC C++, nhưng **không tạo
đầu vào audio theo cùng cách**. Firmware KWS độc lập cắt đoạn bằng VAD rồi đệm
hai bên thành 1 giây. SubBox đang phân loại cửa sổ trượt 1 giây, mỗi 250 ms;
VAD ở AudioManager chưa được dùng để tách từng từ/căn giữa. Ngoài khác biệt
này, đã xác minh sai lệch MFCC giữa cả hai runtime với script train lưu trong
repo, cùng lỗi chép lặp đoạn đầu ở VAD cũ.

Đây là audit nguồn và chạy host. Không train, thu âm mới, truy cập USB, nạp bo,
đổi threshold/model hoặc gửi lệnh relay. Nguồn firmware/model không thay đổi.

## 1. Đã so sánh những bản nào

- KWS độc lập: `archive/2026-10-28-cleanup/files/Firmware/firmware_kws/firmware/`.
  `USE_QUANTIZED_MODEL=1`, nên nhánh FLOAT32 không phải model đang được chọn.
- SubBox: `Firmware/firmware_esp/SubBox/src/audio/kws/local_kws.cpp`, dùng
  `Firmware/firmware_esp/common/kws/` theo CMake hiện hành.
- ActionBox_V2 được đọc để kiểm tra nguồn PCM trước khi gửi tới SubBox.
  WakeNet “Hi ESP” trên ActionBox là model đánh thức, không phải bộ phân loại
  mười từ bật/tắt/đèn/quạt/phòng/khách/ngủ/bếp/noise/unknown.

Hash từng nguồn đã đọc nằm trong `source-sha256.json`. So sánh này không xác
minh lại binary đang chạy trên từng bo.

## 2. Model và phép tính C++ khớp nhau

- 18 mảng tensor giống nhau: 3.776 trọng số INT8, 340 giá trị float cho scale
  và bias. Không phát hiện đổi thứ tự lớp. Tensor digest:
  `478996e4ac80e70f452bd1d5fb2aa1dfe00ef88dc079b237ed9e11c20835a869`.
- Cấu hình chung khớp: 16 kHz; 16.000 mẫu; frame 320/hop 160; FFT 512;
  32 Mel; 13 MFCC; 99 frame; pre-emphasis 0,97; cùng normalization.
- Đã biên dịch riêng MFCC và model thật của cả hai bản trên host, cho cùng PCM
  im lặng và bốn WAV regression bật/đèn/phòng/ngủ. Chênh lệch lớn nhất của cả
  MFCC và xác suất đầu ra đều **0,0** trong năm ca này.
- Những thay đổi ở shared MFCC/model chủ yếu chuyển bộ đệm static sang bộ nhớ
  được cấp phát/PSRAM; không tìm thấy thay đổi trọng số hoặc công thức CNN.

Chi tiết: `model-and-window-results.json`. Parity này không phải kiểm chứng
nhận câu nói thật, cũng không phải bảo đảm mọi compiler/bo cho kết quả bitwise.

## 3. Khác biệt ở tách từ và padding

| Bước | KWS độc lập | SubBox hiện tại |
| --- | --- | --- |
| Thu âm | Đọc trực tiếp I2S theo lát 50 ms | Nhận PCM sau wake word từ ActionBox |
| Ngắt đoạn | 2 lát im lặng = 100 ms, hoặc chạm trần 800 ms recorded | Kết thúc cả stream từ ActionBox/timeout; không cắt từng từ ở đây |
| Đệm | `pad_front=(16000-recorded_samples)/2`, zero cả trước/sau | Ring 16.000 mẫu, khởi tạo zero, chép cửa sổ theo head |
| Chạy model | Một lần sau khi kết thúc đoạn VAD | Mỗi 4.000 mẫu = 250 ms, thêm lượt cuối nếu còn dư |
| Ngưỡng nhận từ | 0,40 | 0,75 thực tế ở LocalKws và KwsCommand |

Nguồn cũ: `src/main.cpp:70`, `:241`, `:277`, `:286`. Nguồn mới:
`local_kws.cpp:86`, `:117`, `:162`, `:186`.

`AudioManager::process()` có gọi `m_vad->process()`, nhưng bỏ qua giá trị trả
về và không dùng onset/end của VAD để cắt/pad. Các frame PCM vẫn đi thẳng vào
`feedAudio()`. Xem `audio_manager.cpp:249`.

Probe biên MFCC đã biên dịch nguyên LocalKws, chỉ thay MFCC/model bằng bộ quan
sát. Khi feed một stream ngắn rồi stop ngay:

| Độ dài tín hiệu | Vị trí nonzero SubBox trong cửa sổ 1 s | Nếu căn giữa đúng tín hiệu này |
| --- | --- | --- |
| 100 ms | 900–1000 ms | 450–550 ms |
| 200 ms | 800–1000 ms | 400–600 ms |
| 250 ms | 750–1000 ms | 375–625 ms |

Đây là ví dụ xác minh cách tạo cửa sổ, không phải kết luận mọi từ nói thật đều
nằm sát cuối: các cửa sổ sau sẽ dịch tín hiệu sang trái và có thể chứa nhiều
từ cùng lúc. Việc zero ring ban đầu không tương đương cắt một từ rồi pad giữa.

## 4. MFCC runtime lệch script train ở đoạn im lặng — cần sửa trước khi đánh giá model

- `scripts/extract_mfcc.py:79` thay năng lượng **bằng zero** bằng
  `np.finfo(float).eps` = khoảng 2,220446e-16; năng lượng dương nhỏ được giữ.
- Cả MFCC runtime cũ và mới ép mọi năng lượng **nhỏ hơn 1e-10** lên 1e-10.
  Shared source: `kws_mfcc.cpp:195`.
- Với frame PCM zero, C0 sau normalization của runtime là **-3,417618**,
  trong khi công thức train cho **-5,498279**; lệch khoảng **2,080660**.
- Tensor X_test lưu sẵn có 8.029/35.145 frame mang C0 gần giá trị im lặng của
  script train. Đây là bằng chứng trên dữ liệu hiện có, không chỉ khác biệt
  hình thức của hai dòng code. Không suy ra mọi frame đó là PCM zero tuyệt đối.
- `Firmware/tests/test_kws_parity.py:66` dùng lại floor 1e-10 của firmware.
  Vì vậy bài có tên “matches training preprocessing” hiện chưa đối chiếu đúng
  nhánh im lặng của script train; test qua đã bỏ sót sai lệch này.

Không chạy script preprocessing/train cũ: chúng có lệnh ghi/xóa dataset và
đường dẫn D:/KWS. Phép tính C0 được đối chiếu bằng công thức cho tín hiệu zero
và output C++ thật; không cần cài/chạy SciPy hay huấn luyện.

Script chuẩn hóa dataset cũng chỉ pad cuối cho file ngắn, không tự căn giữa.
Vì vậy không được mặc định toàn bộ dữ liệu train đã được VAD/căn giữa giống
firmware chỉ dựa vào tên pipeline; cần chốt một quy ước đầu vào khi sửa.

## 5. VAD cũ có lỗi, không nên chép nguyên

Ở trạng thái IDLE, preroll được cập nhật bằng `slice_buf` hiện tại trước khi
kiểm tra onset. Khi có onset, code chép preroll vào audio_buffer, rồi chép thêm
chính `slice_buf` đó. Lát đầu 50 ms bị lặp hai lần (`main.cpp:243–260`).

Đã chạy nguyên `main.cpp::loop()` trên host với micro, Arduino và model giả
lập, quan sát buffer đi vào MFCC:

| Tiếng nói tổng hợp thực | recorded_samples quy đổi | Số mẫu của lát đầu | Có chạy inference |
| --- | --- | --- | --- |
| 50 ms | 250 ms | 1.600 thay vì 800 | Có |
| 100 ms | 300 ms | 1.600 thay vì 800 | Có |
| 200 ms | 400 ms | 1.600 thay vì 800 | Có |

Chi tiết: `legacy-vad-results.json`. Recorded duration gồm preroll, phần lặp
và im lặng đuôi; điều kiện `recorded_samples >= 150 ms` không bảo đảm có 150 ms
tiếng nói thật. Việc VAD có center-pad đúng buffer không có nghĩa tiếng nói
bên trong buffer đã chính xác/không bị nhân đôi.

## 6. PCM trước model cũng khác

- Bản cũ chọn một kênh mic khi khởi tạo, dịch raw I2S `>>16`, lọc và noise gate.
- ActionBox hiện tại chọn kênh có trị tuyệt đối lớn hơn theo từng mẫu, dịch
  `>>14` rồi ép int16, thêm loại DC và lọc; không dùng cùng noise gate cũ.
- Khi chưa tràn, phép đổi mới tạo biên độ khoảng 4 lần phép đổi cũ. Có nguy cơ
  wrap int16 trước limiter: raw32=536.870.912 cho giá trị chuẩn hóa cũ +0,25,
  nhưng phép `int16_t(raw32 >> 14)` thành -1,0. Chưa đo raw mic thật để kết luận
  biên độ thực có đi vào vùng tràn hay không.
- Bỏ đuôi wake word hiện là 40 chunk × 120 mẫu / 16 kHz = **300 ms**, dù comment
  ghi khoảng 200 ms. Nói lệnh ngay sau wake word có thể bị cắt đầu; đây không
  phải bước VAD căn giữa từ.

## Thứ tự xử lý đề xuất

1. Chốt và kiểm tra MFCC runtime với đúng script/tensor train, gồm zero và mức
   tín hiệu rất nhỏ; sửa reference test để không che sai lệch.
2. Tạo đoạn từ bằng VAD trên SubBox, giữ onset/preroll một lần, tính độ dài
   speech riêng và pad hai bên thành 16.000 mẫu; đưa từng kết quả vào assembler.
3. Kiểm tra phép đổi I2S/gain/limiter bằng PCM thật; đối chiếu thời gian bỏ wake
   tail để không mất từ đầu.
4. Giữ model, quyền GPIO ActionBox và điều kiện đầy đủ lệnh. Kiểm tra từ ngắn,
   từ ở biên, câu liên tục và câu ngoài từ vựng trước khi thay đổi ngưỡng nhận.

Chưa áp dụng các đề xuất này, chưa train và chưa kiểm thử lại trên bo thật.
