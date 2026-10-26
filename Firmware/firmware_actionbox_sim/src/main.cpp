#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "config.h"

// Trạng thái Relay & Đo dòng
static bool relay1_state = false; // Kênh 1: Đèn trần
static bool relay2_state = false; // Kênh 2: Quạt trần

static float current_voltage = 220.0f;
static float ch1_power = 0.0f;
static float ch1_current = 0.0f;
static float ch1_energy_kwh = 0.012f;

static float ch2_power = 0.0f;
static float ch2_current = 0.0f;
static float ch2_energy_kwh = 0.025f;

static float total_power = 0.0f;
static float total_current = 0.0f;
static float total_energy_kwh = 0.037f;

// Bộ đếm thời gian
static unsigned long last_telemetry_time = 0;
static unsigned long last_sync_time = 0;
static unsigned long last_energy_calc_time = 0;

// Bộ lọc chống dội nút nhấn
static int last_btn1_val = HIGH;
static int last_btn2_val = HIGH;
static unsigned long last_btn1_debounce = 0;
static unsigned long last_btn2_debounce = 0;
const unsigned long DEBOUNCE_DELAY_MS = 50;

// Pulse latching relay dual-coil
void pulse_latching_relay(int set_pin, int reset_pin, bool turn_on) {
    if (turn_on) {
        digitalWrite(reset_pin, LOW);
        digitalWrite(set_pin, HIGH);
        delay(RELAY_PULSE_MS);
        digitalWrite(set_pin, LOW);
    } else {
        digitalWrite(set_pin, LOW);
        digitalWrite(reset_pin, HIGH);
        delay(RELAY_PULSE_MS);
        digitalWrite(reset_pin, LOW);
    }
}

void set_relay1(bool turn_on) {
    if (relay1_state != turn_on) {
        relay1_state = turn_on;
        pulse_latching_relay(PIN_RELAY1_SET, PIN_RELAY1_RESET, turn_on);
        digitalWrite(PIN_LED1, turn_on ? HIGH : LOW);
        Serial.printf("💡 [RELAY 1 - ĐÈN] Chuyển trạng thái => %s\n", turn_on ? "ON (BẬT)" : "OFF (TẮT)");
    }
}

void set_relay2(bool turn_on) {
    if (relay2_state != turn_on) {
        relay2_state = turn_on;
        pulse_latching_relay(PIN_RELAY2_SET, PIN_RELAY2_RESET, turn_on);
        digitalWrite(PIN_LED2, turn_on ? HIGH : LOW);
        Serial.printf("🌀 [RELAY 2 - QUẠT] Chuyển trạng thái => %s\n", turn_on ? "ON (BẬT)" : "OFF (TẮT)");
    }
}

void setup_hardware() {
    // Tắt amply loa (bảo vệ phần cứng)
    pinMode(PIN_SPEAKER_SD, OUTPUT);
    digitalWrite(PIN_SPEAKER_SD, LOW);

    // Cấu hình LED
    pinMode(PIN_LED1, OUTPUT);
    pinMode(PIN_LED2, OUTPUT);
    digitalWrite(PIN_LED1, LOW);
    digitalWrite(PIN_LED2, LOW);

    // Cấu hình Nút nhấn (Pull-up)
    pinMode(PIN_BTN1, INPUT_PULLUP);
    pinMode(PIN_BTN2, INPUT_PULLUP);

    // Cấu hình chân điều khiển Relay
    pinMode(PIN_RELAY1_SET, OUTPUT);
    pinMode(PIN_RELAY1_RESET, OUTPUT);
    pinMode(PIN_RELAY2_SET, OUTPUT);
    pinMode(PIN_RELAY2_RESET, OUTPUT);
    pinMode(PIN_RELAY3_SET, OUTPUT);
    pinMode(PIN_RELAY3_RESET, OUTPUT);

    digitalWrite(PIN_RELAY1_SET, LOW);
    digitalWrite(PIN_RELAY1_RESET, LOW);
    digitalWrite(PIN_RELAY2_SET, LOW);
    digitalWrite(PIN_RELAY2_RESET, LOW);
    digitalWrite(PIN_RELAY3_SET, LOW);
    digitalWrite(PIN_RELAY3_RESET, LOW);

    // Khởi tạo ban đầu: Bật thử Relay 1 để có dữ liệu tiêu thụ ngay khi khởi động
    set_relay1(true);
    set_relay2(false);
}

void connect_wifi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.printf("\n[WiFi] Đang kết nối tới mạng: %s ...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 25) {
        delay(500);
        digitalWrite(PIN_LED1, !digitalRead(PIN_LED1));
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Kết nối thành công! IP: %s | RSSI: %d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        digitalWrite(PIN_LED1, relay1_state ? HIGH : LOW);
    } else {
        Serial.println("\n[WiFi] Kết nối thất bại. Sẽ tự động thử lại sau.");
    }
}

void check_buttons() {
    int r1 = digitalRead(PIN_BTN1);
    if (r1 != last_btn1_val) {
        last_btn1_debounce = millis();
    }
    if ((millis() - last_btn1_debounce) > DEBOUNCE_DELAY_MS) {
        static int btn1_state = HIGH;
        if (r1 != btn1_state) {
            btn1_state = r1;
            if (btn1_state == LOW) { // Nhấn nút 1
                set_relay1(!relay1_state);
            }
        }
    }
    last_btn1_val = r1;

    int r2 = digitalRead(PIN_BTN2);
    if (r2 != last_btn2_val) {
        last_btn2_debounce = millis();
    }
    if ((millis() - last_btn2_debounce) > DEBOUNCE_DELAY_MS) {
        static int btn2_state = HIGH;
        if (r2 != btn2_state) {
            btn2_state = r2;
            if (btn2_state == LOW) { // Nhấn nút 2
                set_relay2(!relay2_state);
            }
        }
    }
    last_btn2_val = r2;
}

void update_simulated_measurements() {
    unsigned long now = millis();
    float delta_hours = (now - last_energy_calc_time) / 3600000.0f;
    last_energy_calc_time = now;

    // Giả lập điện áp lưới: dao động nhẹ 219.5V - 222.5V
    float v_noise = ((random(0, 30) - 15) / 10.0f);
    current_voltage = 221.0f + v_noise;

    // Kênh 1: Đèn trần (khi bật: dao động 38W - 42W)
    if (relay1_state) {
        float p_noise = ((random(0, 40) - 20) / 10.0f);
        ch1_power = 40.0f + p_noise;
        ch1_current = ch1_power / current_voltage;
        ch1_energy_kwh += (ch1_power * delta_hours) / 1000.0f;
    } else {
        ch1_power = 0.0f;
        ch1_current = 0.0f;
    }

    // Kênh 2: Quạt trần (khi bật: dao động 57W - 63W)
    if (relay2_state) {
        float p_noise = ((random(0, 60) - 30) / 10.0f);
        ch2_power = 60.0f + p_noise;
        ch2_current = ch2_power / current_voltage;
        ch2_energy_kwh += (ch2_power * delta_hours) / 1000.0f;
    } else {
        ch2_power = 0.0f;
        ch2_current = 0.0f;
    }

    total_power = ch1_power + ch2_power;
    total_current = ch1_current + ch2_current;
    total_energy_kwh = ch1_energy_kwh + ch2_energy_kwh;
}

void send_telemetry_to_firebase() {
    if (WiFi.status() != WL_CONNECTED) return;

    WiFiClientSecure client;
    client.setInsecure(); // Bỏ qua xác thực chứng chỉ SSL để kết nối nhanh

    HTTPClient https;
    String url = String(FIREBASE_HOST) + String(FIREBASE_DEVICE_NODE) + ".json";

    if (!https.begin(client, url)) {
        Serial.println("❌ [Firebase] Không thể kết nối HTTPS");
        return;
    }

    https.addHeader("Content-Type", "application/json");

    // Xây dựng JSON Telemetry
    String json = "{";
    json += "\"device_id\":\"action_box_01\",";
    json += "\"name\":\"Action Box Phòng Khách\",";
    json += "\"online\":true,";
    json += "\"voltage\":" + String(current_voltage, 1) + ",";
    json += "\"total_current\":" + String(total_current, 2) + ",";
    json += "\"total_power\":" + String(total_power, 1) + ",";
    json += "\"total_energy_kwh\":" + String(total_energy_kwh, 4) + ",";
    json += "\"last_updated\":" + String(millis()) + ",";
    json += "\"channels\":{";
    
    // Kênh 1
    json += "\"ch1\":{";
    json += "\"id\":\"lr_light\",";
    json += "\"name\":\"Đèn trần\",";
    json += "\"state\":" + String(relay1_state ? "true" : "false") + ",";
    json += "\"voltage\":" + String(current_voltage, 1) + ",";
    json += "\"current\":" + String(ch1_current, 2) + ",";
    json += "\"power\":" + String(ch1_power, 1) + ",";
    json += "\"energy_kwh\":" + String(ch1_energy_kwh, 4);
    json += "},";

    // Kênh 2
    json += "\"ch2\":{";
    json += "\"id\":\"lr_fan\",";
    json += "\"name\":\"Quạt trần\",";
    json += "\"state\":" + String(relay2_state ? "true" : "false") + ",";
    json += "\"voltage\":" + String(current_voltage, 1) + ",";
    json += "\"current\":" + String(ch2_current, 2) + ",";
    json += "\"power\":" + String(ch2_power, 1) + ",";
    json += "\"energy_kwh\":" + String(ch2_energy_kwh, 4);
    json += "}";

    json += "}}";

    int httpCode = https.sendRequest("PATCH", json);

    if (httpCode == HTTP_CODE_OK || httpCode == 204) {
        Serial.printf("⚡ [Firebase] Gửi thành công! V=%.1fV | P_total=%.1fW (Đèn: %.1fW, Quạt: %.1fW) | E=%.4f kWh\n",
                      current_voltage, total_power, ch1_power, ch2_power, total_energy_kwh);
    } else {
        Serial.printf("⚠️ [Firebase] Gửi lỗi, HTTP Code: %d\n", httpCode);
    }

    https.end();
}

void sync_commands_from_firebase() {
    if (WiFi.status() != WL_CONNECTED) return;

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient https;
    String url = String(FIREBASE_HOST) + String(FIREBASE_DEVICE_NODE) + "/channels.json";

    if (!https.begin(client, url)) return;

    int httpCode = https.GET();
    if (httpCode == HTTP_CODE_OK) {
        String payload = https.getString();
        
        // Kiểm tra lệnh cho kênh 1 (Đèn)
        int ch1_idx = payload.indexOf("\"ch1\"");
        if (ch1_idx != -1) {
            int state_idx = payload.indexOf("\"state\":", ch1_idx);
            if (state_idx != -1) {
                bool state = payload.substring(state_idx + 8, state_idx + 12).indexOf("true") != -1;
                set_relay1(state);
            }
        }

        // Kiểm tra lệnh cho kênh 2 (Quạt)
        int ch2_idx = payload.indexOf("\"ch2\"");
        if (ch2_idx != -1) {
            int state_idx = payload.indexOf("\"state\":", ch2_idx);
            if (state_idx != -1) {
                bool state = payload.substring(state_idx + 8, state_idx + 12).indexOf("true") != -1;
                set_relay2(state);
            }
        }
    }
    https.end();
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n========================================================");
    Serial.println("   ACTION BOX (ESP32-S3) — SIMULATED POWER METER FW    ");
    Serial.println("========================================================");

    setup_hardware();
    last_energy_calc_time = millis();

    connect_wifi();
}

void loop() {
    // 1. Tự động kết nối lại WiFi nếu mất mạng
    if (WiFi.status() != WL_CONNECTED) {
        static unsigned long last_reconnect = 0;
        if (millis() - last_reconnect > 5000) {
            last_reconnect = millis();
            connect_wifi();
        }
    }

    // 2. Kiểm tra thao tác nút nhấn cục bộ trên mạch Action Box
    check_buttons();

    // 3. Cập nhật giả lập thông số đo dòng & điện áp
    update_simulated_measurements();

    // 4. Định kỳ gửi Telemetry lên Firebase Realtime Database
    if (millis() - last_telemetry_time >= TELEMETRY_INTERVAL_MS) {
        last_telemetry_time = millis();
        send_telemetry_to_firebase();
    }

    // 5. Định kỳ đồng bộ lệnh điều khiển từ App qua Firebase (mỗi 1.5s)
    if (millis() - last_sync_time >= 1500) {
        last_sync_time = millis();
        sync_commands_from_firebase();
    }

    delay(20);
}
