# 🚀 HƯỚNG DẪN VẬN HÀNH HỆ THỐNG SERVER IOT (MQTT + DATABASE POSTGRESQL + ESP32 ENERGY MONITOR)

---

## 📌 1. TỔNG QUAN HỆ THỐNG
Hệ thống chạy hoàn toàn bằng **Docker Compose** bao gồm 4 dịch vụ:
1. **`iot_mosquitto`**: MQTT Broker (Cổng `1883` truyền nhận tin nhắn).
2. **`iot_postgres`**: Cơ sở dữ liệu PostgreSQL (Cổng `5432`, múi giờ Việt Nam `+07`).
3. **`iot_subscriber`**: Service Python chạy ngầm tự động nhận tin năng lượng từ MQTT và lưu vào Database.
4. **`iot_adminer`**: Trang Web quản lý dữ liệu trực quan (Cổng `8080`).

---

## 💻 2. CÁC LỆNH KHỞI ĐỘNG VÀ QUẢN LÝ SERVER

Mở **Terminal** tại thư mục `/home/pham_vinh/Desktop/mqtt_manager` và sử dụng các lệnh sau:

```bash
cd ~/Desktop/mqtt_manager
```

### 🔹 Khởi động Server (chạy ngầm 24/7):
```bash
docker compose up -d
```

### 🔹 Kiểm tra trạng thái các phần mềm đang chạy:
```bash
docker compose ps
```

### 🔹 Xem dữ liệu ESP32 đẩy về thời gian thực (Real-time Logs):
```bash
docker logs -f iot_subscriber
```
*(Nhấn `Ctrl + C` để thoát màn hình xem log)*

### 🔹 Dừng toàn bộ Server:
```bash
docker compose down
```

---

## 🌐 3. HƯỚNG DẪN XEM DỮ LIỆU TRÊN TRÌNH DUYỆT WEB (ADMINER)

1. Truy cập địa chỉ Web: **[http://localhost:8080](http://localhost:8080)**
2. Nhập thông tin đăng nhập:
   * **System (Hệ quản trị):** `PostgreSQL`
   * **Server (Máy chủ):** `postgres`
   * **Username (Tài khoản):** `iot_user`
   * **Password (Mật khẩu):** `iot_password`
   * **Database (Cơ sở dữ liệu):** `iot_db`
3. Click chọn bảng **`sensor_logs`** bên cột trái.
4. **Cách xem bản tin mới nhất:** Click trực tiếp vào tiêu đề cột **`id`** hoặc chữ **`created_at`** trên đầu bảng để sắp xếp giảm dần (`DESC`). Các cột thông số bao gồm: `voltage` (V), `current` (A), `power` (W), `energy` (Wh), `power_factor` (PF), `frequency` (Hz).

---

## 📡 4. HƯỚNG DẪN KẾT NỐI ESP32 (HARDWARE)

Trong mã nguồn ESP32 PlatformIO (`test1/src/main.cpp`), cấu hình các thông số sau:

* **Địa chỉ IP Server Ubuntu:** `192.168.41.101`
* **Cổng MQTT (Port):** `1883`
* **Topic gửi dữ liệu:** `esp32/sensor/data`

### Định dạng bản tin JSON điện năng chuẩn từ ESP32:
```json
{
  "device_id": "ESP32_Energy_Monitor",
  "voltage": 225.40,
  "current": 1.35,
  "power": 298.20,
  "energy": 1925.10,
  "power_factor": 0.98,
  "frequency": 50.00
}
```
