# ActionBox_V2 — ESP-IDF

Firmware cho PCB ESP32-S3 mới, gồm **3 relay latching HKE3-LT-S**, 3 BL0942,
2 nút, 2 LED và microphone INMP441. Build bằng **ESP-IDF 6.0.2**.
Đây là **project độc lập**, nằm cùng cấp với `ActionBox`, có toàn bộ source,
pinout, partition table và cấu hình ESP-IDF riêng. Không tham chiếu source hay
cấu hình từ `ActionBox`. Project `ActionBox` cũ được giữ nguyên.

```text
Firmware/firmware_esp/
├── ActionBox/
└── ActionBox_V2/
    ├── CMakeLists.txt
    ├── sdkconfig.defaults
    ├── partitions.csv
    ├── build.ps1
    ├── flash.ps1
    └── src/
        ├── main.cpp
        ├── config/board_pins.h
        ├── drivers/
        ├── audio/
        ├── protocol/
        ├── network/
        ├── device/
        ├── safety/
        ├── storage/
        ├── system/
        └── common/
```

## Pinout                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     
                                                                                            
Các số dưới đây là **GPIO**, không phải số chân module WROOM.

| Chức năng | GPIO |
|---|---|
| RL1 SET / RESET | 16 / 15 |
| RL2 SET / RESET | 7 / 6 |
| RL3 SET / RESET | 5 / 4 |
| BL_TX dùng chung | 9 |
| BL_RX1 / BL_RX2 / BL_RX3 | 10 / 11 / 12 |
| BUT1 / BUT2 | 13 / 14, nhấn LOW |
| LED1 / LED2 | 3 / 2, sáng HIGH |
| MIC BCLK / WS / DIN | 47 / 48 / 8 |
| Speaker BCLK / LRC / DOUT | 17 / 18 / 21 |
| Speaker SD | 38, giữ LOW để tắt ampli |
| IR RX / TX | 39 / 40, dự trữ |
| I2C SDA / SCL | 41 / 42, dự trữ |
| USB D− / D+ | 19 / 20 |
| Debug UART0 TX / RX | 43 / 44 |

GPIO35–37 không được sử dụng vì dành cho PSRAM theo sơ đồ.
IR và I2C mới được khai báo pin; chưa có chức năng ứng dụng sử dụng hai giao tiếp này.

## Relay và đo điện

- Bật: SET HIGH 3,3 V trong **50 ms**, sau đó LOW. RESET luôn LOW trong xung SET.
- Tắt: RESET HIGH 3,3 V trong **50 ms**, sau đó LOW. SET luôn LOW trong xung RESET.
- Bộ định thời `esp_timer` chạy callback ISR để hạ chân kích độc lập với task gọi lệnh.
  Khoảng kích và arm timer nằm trong critical section ngắn để tránh task bị ngắt giữa hai bước.
- Các thao tác được khóa nối tiếp; không kích hai cuộn SET/RESET đồng thời.
  Lệnh ON/OFF lặp lại ở trạng thái đã biết không phát thêm xung.
- Ngay khi vào ứng dụng: đưa sáu chân về LOW, phát RESET lần lượt cho cả ba relay,
  rồi mới khởi tạo NVS và mạng. Mặc định khởi động OFF; không suy đoán tiếp điểm từ RAM sau mất điện.
- Ngắt khẩn cấp chờ xung hiện tại kết thúc rồi RESET lần lượt cả ba relay; nó hủy
  lệnh ON đã chờ khóa hoặc chờ khoảng giãn đóng tải. Đây là API gọi từ **task**, không phải ISR.
- Trạng thái ON/OFF là trạng thái lệnh đã thực hiện, **không phải phản hồi tiếp điểm**.
  Nếu lỗi kích GPIO/timer, driver báo trạng thái chưa biết và khóa lỗi phần cứng.
- BUT1/BUT2 nhấn ngắn điều khiển kênh 1/2. Kênh 3 điều khiển qua mạng.
  Giữ chức năng nhấn dài cho voice của firmware hiện có. Board chỉ có 2 LED;
  trạng thái/lỗi kênh 3 được báo qua telemetry và fault alert.

UART1 phát truy vấn chung trên GPIO9, chuyển đầu vào RX lần lượt giữa GPIO10/11/12,
chờ và kiểm tra frame của từng BL0942 dưới cùng một khóa. Không chiếm UART0 để đọc kênh 3.
Tốc độ giữ ở 4800 baud như firmware cũ; checksum, timeout và dữ liệu cũ được kiểm tra.
Mỗi vòng đọc ba kênh diễn ra khoảng 200 ms khi cảm biến phản hồi bình thường;
mất phản hồi có thể kéo dài vòng đọc. Quá 2 giây không có mẫu hợp lệ khi relay ON sẽ ngắt và khóa lỗi.

Ba kênh dùng chung logic bảo vệ: mặc định 10 A kéo dài 300 ms, ngưỡng cứng 16 A
ngắt khi nhận mẫu vượt ngưỡng. Đây là **giá trị kế thừa**, cần hiệu chuẩn BL0942
và đặt giới hạn phù hợp PCB/tải thực tế trước khi sử dụng với tải công suất.
Không có mẫu đo hợp lệ thì lệnh ON bị từ chối.

NVS dùng namespace riêng `actionbox_v2`, không đọc nhầm blob cấu hình hai kênh của V1.
Giao thức vẫn là phiên bản 3. SubBox và Gateway trong thay đổi này đã hỗ trợ
kênh 3, kể cả HTTP `/api/relay`, ACK và cập nhật trạng thái; cần cập nhật chúng
nếu muốn điều khiển kênh 3 từ hệ thống hiện tại.

## Build và nạp bằng ESP-IDF

Mặc định kế thừa module **16 MB flash + 8 MB octal PSRAM** của ActionBox hiện có.
Ảnh chỉ ghi ESP32-S3-WROOM-1, chưa chỉ rõ dung lượng; kiểm tra mã module thực tế.
Nếu khác cấu hình này, chỉnh flash, PSRAM và partition table trong `idf.py menuconfig` trước khi nạp.

Mở terminal đã kích hoạt ESP-IDF 6.0.2, đứng tại thư mục gốc repository:

```sh
idf.py -C Firmware/firmware_esp/ActionBox_V2 build
idf.py -C Firmware/firmware_esp/ActionBox_V2 -p /dev/ttyACM0 flash monitor
```

Trên Windows thay `/dev/ttyACM0` bằng cổng thực tế, ví dụ `COM9`.
Hoặc trong ESP-IDF PowerShell:

```powershell
./Firmware/firmware_esp/ActionBox_V2/build.ps1
./Firmware/firmware_esp/ActionBox_V2/flash.ps1 -Port COM9
```

`flash.ps1 -Port COM9 -NoMonitor` chỉ nạp. Các script dùng môi trường ESP-IDF
đã kích hoạt, không phụ thuộc đường dẫn cài đặt trên một máy cụ thể.

Build tạo `build/ActionBox_V2.bin`. Lần nạp đầu dùng **`idf.py flash`** để nạp đủ
bootloader, partition table, OTA data, ứng dụng và model ESP-SR; không chỉ nạp file app.
Console dùng USB Serial/JTAG. Dùng `Ctrl+]` để thoát monitor.
Chỉnh kênh ESP-NOW trong `menuconfig > ActionBox radio` cho trùng AP của SubBox.

## Kiểm thử

Sau khi build (để tải dependency cJSON), chạy từ thư mục gốc repository:

```sh
python3 -m unittest discover -s Firmware/tests -v
python3 -m unittest discover -s Gateway/tests -p test_hardening_contracts.py -v
python3 -m unittest discover -s Gateway/tests -p test_web_relay.py -v
```

Để chạy toàn bộ kiểm thử Gateway và bộ intent độc lập:

```sh
python3 -m unittest discover -s Gateway/tests -v
python3 Gateway/tests/test_intent_engine_v3.py
```

Kết quả kiểm chứng ngày 2026-10-14: build ESP-IDF thành công; 6 host tests firmware,
49 tests Gateway và 84 kiểm tra intent đều qua. Các test Gateway dùng asyncio
bị treo khi đóng event loop trong sandbox của phiên làm việc; chạy ngoài sandbox thì qua.

Host tests chạy code C++ thực với GPIO/UART/RTOS/NVS giả lập ở ranh giới phần cứng:
RESET ba kênh khi boot, đặt timer 50.000 µs, cuộn LOW sau xung, lỗi timer,
ngắt khẩn cấp khi đang SET và khi ON đang chờ, đọc đúng RX, timeout/checksum,
NVS ba kênh, telemetry/ACK, bảo vệ kênh 3 và tương thích relay V1.
Cần `g++` với C++17 để chạy host tests; firmware vẫn build bằng toolchain ESP-IDF.

Chưa có phép đo trên PCB thật. Khi thử board, kiểm tra bằng oscilloscope/logic analyzer
sáu chân SET/RESET: xung khoảng 50 ms, không chồng xung, LOW sau xung; kiểm tra RESET
sau reboot/mất nguồn, đúng kênh BL0942 và ngắt khi mất cảm biến. Firmware không điều khiển
được GPIO khi chip chưa chạy hoặc mất nguồn; điện trở kéo xuống gate trên PCB phải giữ MOSFET tắt.

Tham khảo API Espressif: [esp_timer](https://docs.espressif.com/projects/esp-idf/en/release-v5.3/esp32s3/api-reference/system/esp_timer.html),
[UART và GPIO routing](https://docs.espressif.com/projects/esp-idf/en/v5.3.3/esp32s3/api-reference/peripherals/uart.html).
