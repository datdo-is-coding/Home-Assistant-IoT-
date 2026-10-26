#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==========================================
// THÔNG TIN WI-FI & FIREBASE REALTIME DATABASE
// ==========================================
#define WIFI_SSID             "XIAOMI"
#define WIFI_PASS             "1234567890"

#define FIREBASE_HOST         "https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app"
#define FIREBASE_DEVICE_NODE  "/devices/action_box_01"

// Chu kỳ cập nhật dữ liệu lên Firebase (ms)
#define TELEMETRY_INTERVAL_MS 2000

// ==========================================
// CẤU HÌNH PHẦN CỨNG MẠCH ACTION BOX V2 (ESP32-S3)
// ==========================================
// Speaker Shutdown (Mute MAX98357)
#define PIN_SPEAKER_SD        38

// Đèn LED trạng thái
#define PIN_LED1              3
#define PIN_LED2              2

// Nút nhấn cục bộ (Pull-up nội, nhấn = LOW)
#define PIN_BTN1              13
#define PIN_BTN2              14

// Rơ-le chốt 2 cuộn (Dual-Coil Latching Relay HKE3-LT-S)
// Kích xung HIGH 50ms vào cuộn SET để đóng, cuộn RESET để ngắt
#define RELAY_PULSE_MS        50

#define PIN_RELAY1_SET        16
#define PIN_RELAY1_RESET      15

#define PIN_RELAY2_SET        7
#define PIN_RELAY2_RESET      6

#define PIN_RELAY3_SET        5
#define PIN_RELAY3_RESET      4

#endif // CONFIG_H
