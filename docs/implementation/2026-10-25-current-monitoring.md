# Theo dõi dòng điện ActionBox V2 và tự hiệu chuẩn

## Phạm vi và trạng thái

Sửa trực tiếp tại `/home/tuan/Home-Assistant-IoT-`.

- Driver BL0942 tách khóa đọc UART khỏi khóa lấy mẫu đã đọc. Telemetry không còn bị timeout chờ UART rồi gửi số 0 với `valid=true`.
- Mẫu chỉ hợp lệ khi đọc thành công, đã có ít nhất một lần lấy mẫu, và tuổi mẫu không quá 5 giây.
- Gateway giữ dòng từng kênh, trạng thái hợp lệ và thời điểm nhận; phát cập nhật qua luồng sự kiện đang có. Số 0 hợp lệ khác mẫu thiếu/lỗi.
- Android đổi mA sang A, hiện trên thẻ thiết bị, màn hình chi tiết và bảng điều khiển nhanh; cập nhật cả khi relay OFF. Sau 15 giây không có mẫu mới, kiểm tra mỗi 5 giây để bỏ số cũ. Khi ngoại tuyến không hiển thị số cũ như số hiện tại.
- Sơ đồ `Hardware/PCB/IoT_Board_V2/IoT_Board_V2.kicad_sch`: chân VP của BL1/BL2/BL3 không kết nối. Telemetry V2 vì thế gửi null cho điện áp, công suất và năng lượng; không lấy dòng nhân 220 để gọi là công suất thực.
- Firmware khởi động áp dụng hệ số đã lưu trong cấu hình factory. Trước sửa, driver luôn dùng hệ số mặc định dù NVS có dữ liệu hiệu chuẩn. Hệ số không hữu hạn, không dương hoặc vượt miền chuyển đổi bị từ chối; không ghi đè NVS.

Đã nạp bản đo dòng lên DDE8/DDF8, cập nhật Gateway và cài APK trên điện thoại ngày 24/10. Thử thực tế DDE8 (ActionBox 2), CH1 “Đèn trần”: nhận dòng khác 0 khi relay OFF; CH2/CH3 bằng 0. Trong một cửa sổ 11 mẫu, CH1 dao động 46–241 mA theo hệ số mặc định. Đây là bằng chứng đường dữ liệu hoạt động, **không phải xác nhận độ chính xác hoặc tải ổn định**. Chưa hiệu chuẩn bằng đồng hồ chuẩn. Bản bổ sung nạp hệ số từ NVS được build ngày 25/10; xem trạng thái nạp cuối báo cáo.

Kiểm thử trước bổ sung đọc hệ số NVS: Flutter 131 đạt; Gateway 327 lượt, 7 bỏ qua; firmware host 20 đạt. Driver có thêm kiểm tra hệ số và hồi quy đọc bộ đệm khi UART bận. Không sửa phần giọng nói trong đợt này.

## Bạn tự lấy số hiệu chuẩn

1. Xác định đúng bo và kênh. Hiện ActionBox 2 là `AB28848533DDE8`, CH1 là “Đèn trần”. Tải của bạn đi qua đường đo riêng, vì vậy không cần bật relay để xem dòng.
2. Dùng ampe kìm True RMS hoặc đồng hồ đo điện cắm ổ có hiển thị A làm số tham chiếu. Với ampe kìm/biến dòng, chỉ một dây dẫn của tải đi qua vòng đo; kẹp cả dây đi và dây về sẽ triệt tiêu tín hiệu. Không tháo/lắp dây điện khi đang cấp điện; nếu chưa quen đấu điện lưới, nhờ người có chuyên môn chuẩn bị đường đo.
3. Khi chưa có tải, kiểm tra dòng gần 0. Không đặt hệ số bằng 0 để che nhiễu. Nếu chỉ số nhảy lớn, xử lý dây đo, đầu nối và nguồn trước.
4. Chọn tải ổn định trong giới hạn định mức phần cứng; tránh thiết bị thay đổi công suất liên tục. Cho tải ổn định rồi ghi số A của đồng hồ và app trong cùng khoảng 30–60 giây, lấy trung bình. Không dùng công suất in trên nhãn chia 220 V làm số chuẩn.
5. Tính:

   `K_mới = K_đang_dùng × I_đồng_hồ / I_app`

   Hai số dòng phải cùng đơn vị. Không tính khi I_app bằng 0, mẫu không hợp lệ, hoặc tải thay đổi mạnh. Nếu dùng số thô trong log:

   `K_mới (mA/count) = 1000 × I_đồng_hồ (A) / raw_i_trung_bình`

   Ví dụ minh họa: K cũ 0.001; app 0.125 A; đồng hồ 0.500 A ⇒ K mới 0.004. **Không áp dụng số ví dụ này cho bo nếu chưa đo.** Log `BL0942_DRIVER` có `raw_i` và `K_I` mỗi 10 giây để đối chiếu.
6. Kiểm tra lại với ít nhất hai mức tải khác. Sai số phần trăm = `100 × |I_app − I_đồng_hồ| / I_đồng_hồ`. Lặp lại độc lập cho từng kênh và từng bo.

Công thức chuyển đổi dựa trên quan hệ tuyến tính I_RMS trong [datasheet BL0942 của Belling](https://www.belling.com.cn/media/file_object/bel_product/BL0942/datasheet/BL0942_V1.1_en.pdf). Hệ số cụ thể còn phụ thuộc biến dòng và điện trở tải của bo; không suy ra từ tên IC.

## Áp dụng hệ số ở bản thử nghiệm

App hiện **chưa có nút nhập/lưu hệ số hiệu chuẩn**. Thay `BL0942_DEFAULT_CAL_CURRENT` không thay được hệ số factory đã lưu của bo cũ. Không erase flash hoặc factory reset để ép hệ số mới.

Nếu tự sửa firmware, có thể thêm đoạn áp dụng dành riêng cho bo sau vòng nạp calibration trong `Firmware/firmware_esp/ActionBox_V2/src/main.cpp`:

```cpp
// Ví dụ: thay 0.004f bằng hệ số THỰC TẾ vừa đo, chỉ cho DDE8/CH1.
if (strcmp(protocol_get_hardware_uid(), "28848533DDE8") == 0) {
    SensorCalibration calibrated = meter_config->calibrations[0];
    calibrated.current_factor = 0.004f;
    ESP_ERROR_CHECK(bl0942_set_calibration(1, &calibrated));
}
```

Đây là override trong firmware thử nghiệm: được áp dụng mỗi lần khởi động bản firmware đó, **không ghi vào NVS**. Giữ đoạn này trong mã nguồn của bản nạp; nếu bỏ override ở bản sau, bo sẽ dùng lại hệ số factory NVS. Không nạp hệ số một bo cho mọi bo.

Build ActionBox_V2 bằng ESP-IDF; chỉ nạp phân vùng ứng dụng theo quy trình dự án, không dùng erase-flash. Sau nạp, xem log `K_I`, đối chiếu app với đồng hồ rồi tắt/bật nguồn kiểm tra lần nữa. Việc nạp/reboot làm relay trở về chính sách khởi động đã cấu hình.

Để thương mại hóa cần thêm luồng hiệu chuẩn có quyền truy cập, ghi hệ số từng bo/từng kênh vào vùng factory với CRC và kiểm tra đọc lại. Luồng đó chưa được triển khai ở đợt sửa hiển thị dòng này.
