# Mẫu regression của model đang dùng

Giữ nguyên byte các mẫu từ pipeline KWS trước dọn: `labels.json`, `X_test.npy`,
`y_test.npy` và bốn WAV `100.wav` của bật/đèn/phòng/ngủ. Các bài parity MFCC,
INT8 inference và ghép câu dùng chúng; không chạy tối ưu hay huấn luyện model.

Pipeline, dữ liệu train/validation và checkpoint cũ được giữ nguyên ở
`archive/2026-10-28-cleanup/files/Firmware/firmware_kws/`. Manifest archive ghi
vị trí gốc và hash của cả phần lưu trữ lẫn các mẫu được chuyển về đây.
