# Archive toàn repo — 2026-10-28

Đã quét các cây app, Gateway, firmware, công cụ, tài liệu và Hardware, gồm cả
file ignored/local. Không xóa vĩnh viễn. `files/` giữ đường dẫn tương đối gốc;
`manifest.json` ghi từng lần chuyển, lý do, số byte, quyền, symlink và SHA-256
từng file. Mỗi lần chuyển đã so sánh toàn bộ trước/sau. Thư mục private này có
cả cache/dữ liệu local, không dùng làm thư mục public download.

## Đã gom

| Nhóm | Đường dẫn gốc tiêu biểu |
| --- | --- |
| App cũ | `App/iot_dashboard`, phần build còn sót của `App/dtv_energy_flutter` |
| Firmware đời cũ/demo | `ActionBox`, `Esp32S3_Master`, `shared`, `Audio_Hardware_Test`, `firmware_actionbox_sim`, `firmware_bin` |
| Huấn luyện đã dừng | `Firmware/firmware_kws`, `Firmware/tests/test_kws_training.py`, `Gateway/training_data`, `Gateway/benchmark` |
| Công cụ cũ | Script serial COM cố định, demo mesh/visualizer, mock HIL, recorder, test NLU thủ công |
| Bản sao/cấu hình thừa | Header reset SubBox trùng common, profile bo cũ/PlatformIO, partition CSV trùng, `main.py.before-*` |
| Artifact cũ | APK cũ, binary Gateway cũ, graphify, build/cache Python/Flutter/ESP-IDF |
| Lịch sử | Prompt/plan cũ, audit evidence, báo cáo cũ, backup/GUI cache CAD |

`README.md`, README của hai Box và `docs/architecture/current_state.md` cũ cũng
được giữ nguyên tại đây; bản mới ở vị trí gốc mô tả đúng hệ thống hiện tại.

## Giữ trong cây hiện hành

- App HomeCompetition: cả 51 Dart file đều reachable từ điểm vào.
- Gateway: các module runtime, Core, OTA, Firebase, compatibility API và các
  regression test còn caller. ASR/LLM tùy chọn và `ws_asr` không được xem là rác
  chỉ vì một cờ chạy đang tắt; `ws_asr` hiện còn dùng cho TTS playback.
- Hai project ESP-IDF SubBox và ActionBox_V2, component chung, model hiện tại,
  dependency đã khóa và SDK config; bộ kiểm thử driver/protocol/safety/calibration.
- Mẫu model regression được chuyển nguyên byte sang
  `Firmware/tests/fixtures/kws/`, tách khỏi pipeline huấn luyện đã dừng.
- PCB/CAD, thư viện footprint/3D, fabrication output, `sound/`, MQTT/deployment,
  protocol contract và cấu hình/runtime data không được phân loại là rác.
- APK đang cài và image OTA đã ký nằm trong `releases/`, có `SHA256SUMS`.

Kiểm thử driver V1 đọc source V1 trong archive làm baseline, dùng common header
hiện hành một cách tường minh. Không có target sản phẩm đang build V1.

## Kiểm chứng và khôi phục

Từ gốc repo:

```sh
python3 archive/2026-10-28-cleanup/verify.py
```

Lệnh kiểm tra nội dung lưu trữ mà không thực thi code archive. Các symlink được
giữ nguyên target; code cũ có thể cần được trả về vị trí gốc trước khi build.

Để khôi phục một mục, tra `source` và `destination` trong manifest, dừng công
việc đang dùng đường dẫn đó và chuyển `destination` về `source`. Nếu tại source
đã có code mới, đối chiếu trước; không ghi đè. Với cache build, nên tạo lại vì
cache cũ chứa đường dẫn tuyệt đối. Bản vá các thay đổi chưa commit trước dọn được
giữ ở `pre-cleanup-working-tree.patch`; không áp dụng chồng lên working tree hiện
tại. Không commit/reset hoặc đồng bộ thư mục archive lên Pi trong đợt này.

`.gitignore` tại đây giữ nguyên khả năng theo dõi của những file trước đó đã
tracked/unignored, gồm các dependency cũ từng được commit; cache ignored vẫn là
local. Sao lưu cả thư mục trên đĩa nếu cần giữ các artifact local qua máy khác.

Khi xuất bản Git, khóa mẫu riêng, APK/image đã biên dịch và Git history nhúng
của CAD được giữ local trong archive, không đưa các mục này lên remote.

Kết quả kiểm thử và tổng số file/byte nằm trong
[`docs/implementation/2026-10-28-repository-cleanup.md`](../../docs/implementation/2026-10-28-repository-cleanup.md).
