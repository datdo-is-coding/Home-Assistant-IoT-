-- Khởi tạo bảng lưu trữ dữ liệu cảm biến năng lượng từ ESP32
CREATE TABLE IF NOT EXISTS sensor_logs (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    voltage NUMERIC(6,2),
    current NUMERIC(6,2),
    power NUMERIC(8,2),
    energy NUMERIC(10,2),
    power_factor NUMERIC(4,2),
    frequency NUMERIC(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
