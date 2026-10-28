# SubBox

Project điều phối các ActionBox, âm thanh và nhận diện từ khóa. Điểm vào là
`src/main.cpp`; dùng chung `../common/hc_core/` và `../common/kws/`.

- `src/actionbox/`, `src/network/`: định tuyến và ESP-NOW.
- `src/audio/kws/`: model hiện có và bảng gán phòng/loại thiết bị sang kênh.
- `src/audio/asr/ws_asr.*`: hiện vẫn cần cho đường phát TTS xuống loa; tên file
  không có nghĩa Pi đang nhận diện microphone.
- `src/nlu/`, `src/room/`, `src/system/`: xử lý câu, ngữ cảnh và vòng tác vụ.
- `src/mqtt/`, `src/storage/`: cấu hình, đồng bộ và lưu trạng thái.

Build từ gốc repo trong ESP-IDF 6.0.2:

```sh
idf.py -C Firmware/firmware_esp/SubBox build
```

Project CMake này là mục tiêu duy trì. Các profile PlatformIO/bo khác và bản sao
header reset đã được lưu trong archive. Header reset chung vẫn ở
`../common/device_reset.h`. Giữ các component đã khóa phiên bản và các file
`sdkconfig*` hiện hành.

Không huấn luyện lại model trong đợt này. Mẫu regression được giữ ở
`Firmware/tests/fixtures/kws/`. Đăng ký/OTA thành công chưa xác nhận toàn tuyến
nhận giọng nói và đóng relay. Xem
[trạng thái hiện tại](../../../docs/architecture/current_state.md).
