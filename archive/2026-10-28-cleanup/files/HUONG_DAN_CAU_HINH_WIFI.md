# 📖 HƯỚNG DẪN CẤU HÌNH HỆ THỐNG KHI ĐỔI MẠNG WI-FI MỚI
> **Hệ thống Nhà Thông Minh AETHERIA (Gateway Pi 4 + SubBox + ActionBox)**

Tài liệu này hướng dẫn chi tiết cách thiết lập lại kết nối khi mang toàn bộ hệ thống sang địa điểm mới (nhà mới, văn phòng, phòng lab, hội chợ...) có mạng Wi-Fi khác.

---

## ⚡ TÓM TẮT NHANH (QUICK REFERENCE)

| Thiết bị | Cần làm gì? | Tên Wi-Fi phát ra | Mật khẩu Wi-Fi | Địa chỉ Web cấu hình |
| :--- | :--- | :--- | :--- | :--- |
| **1. Gateway (Pi 4)** | Cắm LAN hoặc kết nối Wi-Fi mới | `Aetheria-Hotspot` *(nếu không có mạng)* | Không mật khẩu / `12345678` | `http://10.42.0.1:8000` hoặc `http://<IP_LAN>:8000` |
| **2. SubBox (Loa)** | Kết nối Captive Portal cấp Wi-Fi | `SubBox-Setup-XXXX` | **Không có (Mạng mở)** | `http://192.168.4.1` |
| **3. ActionBox (Công tắc/Mic)** | **Không cần làm gì** | *Chạy ESP-NOW nội bộ* | *Tự động dò kênh* | *Không cần cấu hình* |

---

## ⚠️ ĐIỀU KIỆN TIÊN QUYẾT
* Mạng Wi-Fi tại địa điểm mới **bắt buộc phải hỗ trợ băng tần 2.4 GHz** (ESP32-S3 không hỗ trợ Wi-Fi 5 GHz).
* Nếu router Wi-Fi gộp chung cả 2.4 GHz và 5 GHz cùng một tên (Band Steering), hãy đảm bảo tính năng 2.4 GHz đang bật bình thường.

---

## 🚀 QUY TRÌNH THỰC HIỆN (3 BƯỚC)

```
[ BƯỚC 1: Cấp mạng cho Gateway Pi 4 ]
               │
               ▼
[ BƯỚC 2: Cấp mạng cho SubBox & trỏ IP về Pi 4 ]
               │
               ▼
[ BƯỚC 3: ActionBox tự động kết nối lại ]
```

---

### BƯỚC 1: CẤU HÌNH GATEWAY (RASPBERRY PI 4)
Cần cấp mạng cho Gateway Pi 4 trước để lấy địa chỉ IP của Pi tại mạng mới.

#### 👉 Cách 1 (Khuyên dùng - Nhanh và ổn định nhất):
* Cắm dây mạng LAN từ cổng Ethernet của Pi 4 trực tiếp vào Router Wi-Fi mới.
* Pi 4 sẽ tự nhận IP qua DHCP ngay lập tức.
* Kiểm tra địa chỉ IP của Pi:
  * Cách A: Mở Terminal trên Pi (hoặc màn hình cắm vào Pi) gõ:
    ```bash
    hostname -I
    ```
    *(Ví dụ kết quả hiển thị: `192.168.1.50`)*
  * Cách B: Xem danh sách thiết bị kết nối trong trang quản trị Router hoặc dùng app Fing trên điện thoại.

---

#### 👉 Cách 2 (Kết nối Wi-Fi bằng Hotspot tự động của Pi):
Khi không có dây LAN và không thấy mạng Wi-Fi cũ, dịch vụ `autohotspot.sh` trên Pi 4 sẽ tự động phát sóng:
1. Dùng điện thoại/laptop dò Wi-Fi và kết nối vào:
   * **Tên Wi-Fi**: `Aetheria-Hotspot`
2. Mở trình duyệt truy cập:
   ```
   http://10.42.0.1:8000
   ```
3. Vào giao diện Cấu hình Mạng $\rightarrow$ Quét mạng Wi-Fi xung quanh $\rightarrow$ Chọn Wi-Fi 2.4GHz mới và nhập mật khẩu $\rightarrow$ Bấm Kết nối.
4. Pi 4 sẽ tắt Hotspot và chuyển sang kết nối Wi-Fi mới.

---

#### 👉 Cách 3 (Dành cho kỹ thuật viên qua Terminal/Console):
Cắm màn hình + bàn phím hoặc cắm cáp Serial vào Pi 4 và gõ lệnh:
```bash
sudo nmcli dev wifi connect "TEN_WIFI_MOI" password "MAT_KHAU_WIFI"
```
Sau đó kiểm tra IP:
```bash
hostname -I
```
*(Ghi nhớ địa chỉ IP này, ví dụ: `192.168.1.50` để dùng cho Bước 2).*

---

### BƯỚC 2: CẤU HÌNH SUBBOX (ESP32-S3 LOA / NÃO BỘ PHÒNG)

Khi bật nguồn SubBox tại địa điểm mới:
1. SubBox sẽ thử tìm và kết nối lại Wi-Fi cũ 5 lần (~15 giây).
2. Khi không thấy mạng cũ, đèn LED trên SubBox sẽ chớp báo hiệu và SubBox **tự động chuyển sang chế độ Cấu Hình (SoftAP Captive Portal)**:

#### 1. Kết nối vào Wi-Fi do SubBox phát ra:
* Mở cài đặt Wi-Fi trên điện thoại hoặc laptop.
* Tìm mạng Wi-Fi có tên dạng:
  ```
  SubBox-Setup-XXXX
  ```
  *(Trong đó `XXXX` là mã định danh phần cứng của thiết bị, ví dụ `SubBox-Setup-A1B2`)*.
* **Mật khẩu**: **Không có (Mạng mở - Open)**.

#### 2. Mở trang Cấu Hình Web:
* Đa số điện thoại (iPhone / Android) sẽ tự động hiện thông báo *"Đăng nhập vào mạng Wi-Fi"* và mở trang web cấu hình.
* Nếu trang web không tự mở, hãy mở trình duyệt (Chrome / Safari) và truy cập địa chỉ IP:
  ```
  http://192.168.4.1
  ```

#### 3. Điền thông tin kết nối trên giao diện Web:
Trang cấu hình SubBox sẽ hiển thị như sau:
* **Mạng Wi-Fi (2.4GHz)**: Bấm nút `🔄 Quét lại mạng Wi-Fi` $\rightarrow$ Chọn tên Wi-Fi nhà bạn từ menu thả xuống.
* **Mật khẩu Wi-Fi**: Nhập mật khẩu Wi-Fi mới.
* **Vị trí phòng của SubBox**: Chọn phòng đặt thiết bị (Phòng ngủ, Phòng khách, Phòng bếp...).
* **IP Gateway Pi 4**: Nhập địa chỉ IP của Pi 4 vừa lấy được ở **Bước 1** (Ví dụ: `192.168.1.50`).

#### 4. Hoàn tất:
* Nhấn nút **"Lưu Cấu Hình & Kết Nối"**.
* SubBox sẽ lưu cấu hình vào bộ nhớ NVS Flash, tắt mạng Hotspot và khởi động lại.
* Khi kết nối thành công, loa SubBox sẽ phát chuông khởi động (`BOOTUP Chime`) báo hiệu đã vào mạng mới và kết nối tới Pi 4 thành công!

---

### BƯỚC 3: ACTIONBOX (CÔNG TẮC / MIC THU ÂM)

* **Bạn không cần làm bất kỳ thao tác nào trên ActionBox!**
* **Lý do**:
  * ActionBox không dùng Wi-Fi router mà kết nối trực tiếp với SubBox qua giao thức **ESP-NOW (Peer-to-Peer 2.4GHz)**.
  * Khi SubBox kết nối vào router mới, SubBox sẽ hoạt động theo kênh tần số radio của router mới (ví dụ kênh 1, 6, 11...).
  * ActionBox có tính năng tự động quét kênh (`espnow_transport_scan_channels`). Nếu sau 10 giây không nhận được tín hiệu từ SubBox, ActionBox sẽ tự động quét từ kênh 1 đến 13, tìm lại SubBox và tự khóa kênh mới.
  * Các công tắc cơ khí và điều khiển rơ-le cục bộ trên ActionBox vẫn hoạt động độc lập an toàn trong suốt quá trình này.

---

## 🛠️ XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)

### 1. Đã bật SubBox nhưng không thấy Wi-Fi `SubBox-Setup-XXXX`?
* Hãy đợi khoảng 20–30 giây sau khi cắm nguồn (SubBox cần thử kết nối Wi-Fi cũ 5 lần trước khi chuyển sang chế độ Hotspot).
* Kiểm tra đèn LED nguồn của SubBox đã sáng chưa.

### 2. Điện thoại đã kết nối vào `SubBox-Setup-XXXX` nhưng không tự mở trang web?
* Hãy tắt tạm thời 4G/5G (Dữ liệu di động) trên điện thoại để tránh điện thoại tự chuyển sang dùng 4G.
* Mở trình duyệt web (Chrome, Safari, Edge) gõ trực tiếp địa chỉ:
  `http://192.168.4.1`

### 3. Ra lệnh giọng nói không phản hồi sau khi đổi mạng?
* Kiểm tra xem IP của Gateway Pi 4 nhập trong SubBox có bị đổi không:
  * Nếu router mới dùng chế độ cấp IP động (DHCP), IP của Pi 4 có thể thay đổi sau khi khởi động lại.
  * Khuyên dùng: Vào cài đặt Router Wi-Fi để gán **Static IP / IP tĩnh** cố định cho địa chỉ MAC của Raspberry Pi 4.

### 4. Muốn ép SubBox vào chế độ cấu hình Wi-Fi lại từ đầu?
* Nhấn giữ nút cấu hình vật lý (**BUT1 / GPIO 1**) trên SubBox trong 5 giây, hoặc khởi động lại SubBox tại nơi không có Wi-Fi cũ, SubBox sẽ tự động phát lại mạng `SubBox-Setup-XXXX`.
