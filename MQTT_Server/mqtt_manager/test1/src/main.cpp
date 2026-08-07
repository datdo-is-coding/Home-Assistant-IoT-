/*
 * =============================================================
 *  SMART HOME ENERGY MONITOR - TFT 1.8" ST7735 Display (128x160)
 *  ESP32 + HLW8012/HLW8032 (Simulated) + MQTT + PostgreSQL
 * =============================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include "network_manager.h"

// ============================================================
// CẤU HÌNH PHẦN CỨNG
// ============================================================
#define TFT_CS    5
#define TFT_RST   21
#define TFT_DC    22
#define BTN_PAGE  2   // Chuyển nút nhấn sang chân D2 (GPIO 2)

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

// ============================================================
// BẢNG MÀU - THIẾT KẾ HIỆN ĐẠI
// ============================================================
#define RGB565(r, g, b) ((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | (((b) & 0xF8) >> 3))

#define COLOR_BG_DARK     RGB565(15, 15, 25)
#define COLOR_BG_CARD     RGB565(25, 28, 45)
#define COLOR_BG_HEADER   RGB565(20, 60, 120)

#define COLOR_WHITE       RGB565(240, 240, 245)
#define COLOR_GRAY        RGB565(120, 125, 140)
#define COLOR_LIGHT_GRAY  RGB565(180, 185, 195)

#define COLOR_CYAN        RGB565(0, 210, 255)
#define COLOR_GREEN       RGB565(0, 230, 118)
#define COLOR_YELLOW      RGB565(255, 214, 0)
#define COLOR_ORANGE      RGB565(255, 152, 0)
#define COLOR_RED         RGB565(255, 60, 60)
#define COLOR_PURPLE      RGB565(180, 100, 255)

#define COLOR_LINE        RGB565(40, 45, 65)
#define COLOR_BORDER      RGB565(50, 55, 80)

#define COLOR_BAR_BG      RGB565(35, 38, 55)
#define COLOR_BAR_LOW     COLOR_GREEN
#define COLOR_BAR_MED     COLOR_YELLOW
#define COLOR_BAR_HIGH    COLOR_RED

// ============================================================
// STRUCT DỮ LIỆU CẢM BIẾN
// ============================================================
struct SensorData {
  float voltage;       // Điện áp (V)
  float current;       // Dòng điện (A)
  float power;         // Công suất (W)
  float energy;        // Điện năng tiêu thụ (Wh/kWh)
  float powerFactor;   // Hệ số công suất
  float frequency;     // Tần số (Hz)
  float maxCurrent;    // Dòng max cho thanh bar (A)
};

struct HistoryData {
  float today;         // Hôm nay (Wh)
  float yesterday;     // Hôm qua (Wh)
  float month;         // Tháng này (kWh)
  float lastMonth;     // Tháng trước (kWh)
};

struct MoneyData {
  unsigned long thisMonth;  // Tiền tháng này (VND)
  unsigned long lastMonth;  // Tiền tháng trước (VND)
  float pricePerKWh;        // Giá điện trung bình (VND/kWh)
};

struct TimeData {
  uint8_t hour;
  uint8_t minute;
  uint8_t second;
  uint8_t day;
  uint8_t month;
  uint16_t year;
};

// Khởi tạo dữ liệu mặc định
SensorData sensor = {220.5, 0.51, 112.5, 1921.6, 0.99, 50.0, 16.0};
HistoryData history = {1700, 7500, 9200, 0};
MoneyData money = {20058, 0, 2800};
TimeData timeNow = {17, 15, 30, 25, 7, 2026};
StatusFlags status = {false, false, false, false};

// ============================================================
// BIẾN ĐIỀU KHIỂN TRANG VÀ THỜI GIAN
// ============================================================
#define TOTAL_PAGES    3
#define MQTT_INTERVAL  3000  // Đẩy dữ liệu MQTT mỗi 3s

int  currentPage = 0;
unsigned long lastPageSwitch = 0;
unsigned long lastTimeUpdate = 0;
unsigned long lastMqttSend = 0;
bool needFullRedraw = true;
bool btnPressed = false;
unsigned long lastBtnPressTime = 0;

#define VOLTAGE_MAX   250.0   // Quá áp (V)
#define VOLTAGE_MIN   180.0   // Thiếu áp (V)
#define CURRENT_MAX   15.0    // Quá dòng (A)

// Prototype hàm UI
void drawSplashScreen();
void drawHeader();
void drawPage0();
void drawPage1();
void drawPage2();
void drawCurrentPage();
void switchPage(int page);
void formatMoney(unsigned long value, char* buf);
void checkAlarms();
void updateTime();
void handleButton();

// ============================================================
// HÀM TẠO DỮ LIỆU CẢM BIẾN GIẢ LẬP (RANDOM)
// ============================================================
void generateMockSensorData() {
  sensor.voltage = 215.0 + random(0, 200) / 10.0;             // 215.0V - 235.0V
  sensor.current = 0.2 + random(0, 480) / 100.0;               // 0.20A - 5.00A
  sensor.power = sensor.voltage * sensor.current * 0.98;       // P = U * I * PF
  sensor.energy += (sensor.power / 3600.0);                    // Cộng dồn Wh
  sensor.powerFactor = 0.97 + (random(0, 3) / 100.0);          // ~0.97 - 0.99
  sensor.frequency = 49.9 + (random(0, 3) / 10.0);             // 49.9Hz - 50.1Hz

  history.today += (sensor.power / 3600.0);
  money.thisMonth = (unsigned long)((history.month + (history.today / 1000.0)) * money.pricePerKWh);
}

// ============================================================
// HÀM VẼ ĐỒ HỌA UI TFT
// ============================================================
void fillRoundRect(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r, uint16_t color) {
  tft.fillRoundRect(x, y, w, h, r, color);
}

void drawRoundRect(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r, uint16_t color) {
  tft.drawRoundRect(x, y, w, h, r, color);
}

void drawWifiIcon(int16_t cx, int16_t cy, uint16_t color) {
  tft.fillCircle(cx, cy + 3, 1, color);
  for (int i = -30; i <= 30; i++) {
    float rad = i * 3.14159 / 180.0;
    tft.drawPixel(cx + (int)(4 * sin(rad)), cy - (int)(4 * cos(rad)) + 3, color);
    tft.drawPixel(cx + (int)(7 * sin(rad)), cy - (int)(7 * cos(rad)) + 3, color);
  }
}

void drawMqttIcon(int16_t cx, int16_t cy, uint16_t color) {
  tft.drawFastVLine(cx, cy - 2, 7, color);
  tft.drawFastHLine(cx - 3, cy - 2, 7, color);
  tft.drawPixel(cx - 2, cy - 4, color);
  tft.drawPixel(cx + 2, cy - 4, color);
  tft.drawPixel(cx, cy - 5, color);
}

void drawWarningIcon(int16_t cx, int16_t cy, uint16_t color) {
  tft.drawLine(cx, cy - 4, cx - 4, cy + 3, color);
  tft.drawLine(cx, cy - 4, cx + 4, cy + 3, color);
  tft.drawFastHLine(cx - 4, cy + 3, 9, color);
  tft.drawFastVLine(cx, cy - 2, 3, color);
  tft.drawPixel(cx, cy + 2, color);
}

void drawBoltIcon(int16_t x, int16_t y, uint16_t color) {
  tft.drawLine(x + 3, y, x + 1, y + 4, color);
  tft.drawLine(x + 1, y + 4, x + 3, y + 4, color);
  tft.drawLine(x + 3, y + 4, x, y + 8, color);
}

void drawClockIcon(int16_t cx, int16_t cy, uint16_t color) {
  tft.drawCircle(cx, cy, 3, color);
  tft.drawLine(cx, cy, cx, cy - 2, color);
  tft.drawLine(cx, cy, cx + 2, cy, color);
}

void drawCoinIcon(int16_t cx, int16_t cy, uint16_t color) {
  tft.drawCircle(cx, cy, 4, color);
  tft.setCursor(cx - 2, cy - 3);
  tft.setTextColor(color);
  tft.setTextSize(1);
  tft.print("$");
}

void drawProgressBar(int16_t x, int16_t y, int16_t w, int16_t h, float value, float maxVal) {
  fillRoundRect(x, y, w, h, 2, COLOR_BAR_BG);
  float percent = (value / maxVal) * 100.0;
  if (percent > 100.0) percent = 100.0;
  if (percent < 0.0) percent = 0.0;

  int fillW = (int)((w - 2) * percent / 100.0);
  if (fillW < 1) fillW = 1;

  uint16_t barColor = (percent < 50.0) ? COLOR_BAR_LOW : ((percent < 80.0) ? COLOR_BAR_MED : COLOR_BAR_HIGH);
  fillRoundRect(x + 1, y + 1, fillW, h - 2, 1, barColor);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_WHITE);
  tft.setCursor(x + w + 2, y + (h / 2) - 3);
  tft.print((int)percent);
  tft.print("%");
}

void drawPageIndicator(int activePage) {
  int dotSpacing = 10;
  int totalW = TOTAL_PAGES * dotSpacing;
  int startX = (128 - totalW) / 2;
  int y = 153;

  for (int i = 0; i < TOTAL_PAGES; i++) {
    int cx = startX + i * dotSpacing + 3;
    if (i == activePage) {
      tft.fillCircle(cx, y, 3, COLOR_CYAN);
    } else {
      tft.drawCircle(cx, y, 2, COLOR_GRAY);
    }
  }
}

void drawHeader() {
  tft.fillRect(0, 0, 128, 17, COLOR_BG_HEADER);
  tft.drawFastHLine(0, 16, 128, RGB565(30, 80, 160));

  drawWifiIcon(8, 5, status.wifiConnected ? COLOR_GREEN : COLOR_RED);
  drawMqttIcon(22, 5, status.mqttConnected ? COLOR_GREEN : COLOR_RED);

  if (status.overVoltage || status.overCurrent) {
    drawWarningIcon(36, 6, COLOR_RED);
  }

  tft.setTextSize(1);
  tft.setTextColor(COLOR_WHITE);
  char timeBuf[6];
  sprintf(timeBuf, "%02d:%02d", timeNow.hour, timeNow.minute);
  tft.setCursor(94, 4);
  tft.print(timeBuf);
}

void drawPage0() {
  fillRoundRect(2, 20, 124, 38, 4, COLOR_BG_CARD);
  drawRoundRect(2, 20, 124, 38, 4, COLOR_BORDER);

  drawBoltIcon(5, 24, COLOR_YELLOW);

  tft.setTextSize(1);
  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(14, 23);
  tft.print("Volt");

  tft.setTextColor((sensor.voltage > VOLTAGE_MAX || sensor.voltage < VOLTAGE_MIN) ? COLOR_RED : COLOR_CYAN);
  tft.setCursor(14, 34);
  tft.print(sensor.voltage, 1);
  tft.setTextColor(COLOR_GRAY);
  tft.print("V");

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(68, 23);
  tft.print("Curr");

  tft.setTextColor((sensor.current > CURRENT_MAX) ? COLOR_RED : COLOR_GREEN);
  tft.setCursor(68, 34);
  tft.print(sensor.current, 2);
  tft.setTextColor(COLOR_GRAY);
  tft.print("A");

  drawProgressBar(14, 47, 65, 6, sensor.current, sensor.maxCurrent);

  fillRoundRect(2, 60, 124, 34, 4, COLOR_BG_CARD);
  drawRoundRect(2, 60, 124, 34, 4, COLOR_BORDER);

  drawBoltIcon(5, 64, COLOR_ORANGE);
  tft.setTextSize(1);
  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(14, 63);
  tft.print("Power");
  tft.setTextColor(COLOR_ORANGE);
  tft.setCursor(14, 75);
  tft.print(sensor.power, 1);
  tft.setTextColor(COLOR_GRAY);
  tft.print("W");

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(68, 63);
  tft.print("Energy");
  tft.setTextColor(COLOR_PURPLE);
  tft.setCursor(68, 75);
  if (sensor.energy >= 1000) {
    tft.print(sensor.energy / 1000.0, 1);
    tft.setTextColor(COLOR_GRAY);
    tft.print("k");
  } else {
    tft.print(sensor.energy, 0);
    tft.setTextColor(COLOR_GRAY);
    tft.print("W");
  }

  fillRoundRect(2, 97, 60, 28, 4, COLOR_BG_CARD);
  drawRoundRect(2, 97, 60, 28, 4, COLOR_BORDER);

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(6, 100);
  tft.print("PF");
  tft.setTextColor(COLOR_CYAN);
  tft.setCursor(6, 112);
  tft.print(sensor.powerFactor, 2);

  fillRoundRect(66, 97, 60, 28, 4, COLOR_BG_CARD);
  drawRoundRect(66, 97, 60, 28, 4, COLOR_BORDER);

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(70, 100);
  tft.print("Freq");
  tft.setTextColor(COLOR_CYAN);
  tft.setCursor(70, 112);
  tft.print(sensor.frequency, 1);
  tft.setTextColor(COLOR_GRAY);
  tft.print("Hz");

  if (status.overVoltage || status.overCurrent) {
    fillRoundRect(2, 128, 124, 12, 3, COLOR_RED);
    tft.setTextSize(1);
    tft.setTextColor(COLOR_WHITE);
    if (status.overVoltage && status.overCurrent) {
      tft.setCursor(10, 130);
      tft.print("!! OVER V & I !!");
    } else if (status.overVoltage) {
      tft.setCursor(15, 130);
      tft.print("!! OVER VOLTAGE !!");
    } else {
      tft.setCursor(15, 130);
      tft.print("!! OVER CURRENT !!");
    }
  }
}

void drawPage1() {
  drawClockIcon(8, 25, COLOR_CYAN);
  tft.setTextSize(1);
  tft.setTextColor(COLOR_CYAN);
  tft.setCursor(16, 21);
  tft.print("ENERGY HISTORY");

  tft.drawFastHLine(4, 31, 120, COLOR_LINE);

  fillRoundRect(3, 34, 122, 22, 3, COLOR_BG_CARD);
  drawRoundRect(3, 34, 122, 22, 3, COLOR_BORDER);

  tft.setTextColor(COLOR_GREEN);
  tft.setCursor(7, 37);
  tft.print("Today");

  tft.setTextColor(COLOR_WHITE);
  char buf[16];
  if (history.today >= 1000) {
    dtostrf(history.today / 1000.0, 4, 1, buf);
    tft.setCursor(72, 37);
    tft.print(buf);
    tft.setTextColor(COLOR_GRAY);
    tft.print("kWh");
  } else {
    dtostrf(history.today, 4, 0, buf);
    tft.setCursor(72, 37);
    tft.print(buf);
    tft.setTextColor(COLOR_GRAY);
    tft.print("Wh");
  }

  drawProgressBar(16, 48, 68, 4, history.today, 10000);

  fillRoundRect(3, 58, 122, 17, 3, COLOR_BG_CARD);
  drawRoundRect(3, 58, 122, 17, 3, COLOR_BORDER);

  tft.setTextColor(COLOR_LIGHT_GRAY);
  tft.setCursor(7, 62);
  tft.print("Yesterday");
  tft.setTextColor(COLOR_WHITE);
  if (history.yesterday >= 1000) {
    dtostrf(history.yesterday / 1000.0, 4, 1, buf);
    tft.setCursor(72, 62);
    tft.print(buf);
    tft.setTextColor(COLOR_GRAY);
    tft.print("kWh");
  } else {
    dtostrf(history.yesterday, 4, 0, buf);
    tft.setCursor(72, 62);
    tft.print(buf);
    tft.setTextColor(COLOR_GRAY);
    tft.print("Wh");
  }

  fillRoundRect(3, 77, 122, 17, 3, COLOR_BG_CARD);
  drawRoundRect(3, 77, 122, 17, 3, COLOR_BORDER);

  tft.setTextColor(COLOR_CYAN);
  tft.setCursor(7, 81);
  tft.print("This Month");
  tft.setTextColor(COLOR_WHITE);
  dtostrf(history.month / 1000.0, 4, 1, buf);
  tft.setCursor(72, 81);
  tft.print(buf);
  tft.setTextColor(COLOR_GRAY);
  tft.print("kWh");

  fillRoundRect(3, 96, 122, 17, 3, COLOR_BG_CARD);
  drawRoundRect(3, 96, 122, 17, 3, COLOR_BORDER);

  tft.setTextColor(COLOR_PURPLE);
  tft.setCursor(7, 100);
  tft.print("Last Month");
  tft.setTextColor(COLOR_WHITE);
  dtostrf(history.lastMonth / 1000.0, 4, 1, buf);
  tft.setCursor(72, 100);
  tft.print(buf);
  tft.setTextColor(COLOR_GRAY);
  tft.print("kWh");

  tft.setTextColor(COLOR_GRAY);
  tft.setTextSize(1);
  char dateBuf[12];
  sprintf(dateBuf, "%02d/%02d/%04d", timeNow.day, timeNow.month, timeNow.year);
  tft.setCursor(34, 120);
  tft.print(dateBuf);
}

void drawPage2() {
  drawCoinIcon(8, 25, COLOR_YELLOW);
  tft.setTextSize(1);
  tft.setTextColor(COLOR_YELLOW);
  tft.setCursor(16, 21);
  tft.print("ELECTRIC COST");

  tft.drawFastHLine(4, 31, 120, COLOR_LINE);

  fillRoundRect(3, 35, 122, 40, 4, COLOR_BG_CARD);
  drawRoundRect(3, 35, 122, 40, 4, RGB565(50, 120, 50));

  tft.setTextColor(COLOR_GREEN);
  tft.setCursor(7, 39);
  tft.print("This Month");

  char moneyBuf[16];
  formatMoney(money.thisMonth, moneyBuf);

  char fullMoneyStr[24];
  sprintf(fullMoneyStr, "%s d", moneyBuf);
  int16_t tw = strlen(fullMoneyStr) * 6;
  int16_t mx = (128 - tw) / 2;
  if (mx < 6) mx = 6;

  tft.setTextSize(1);
  tft.setCursor(mx, 53);
  tft.setTextColor(COLOR_WHITE);
  tft.print(moneyBuf);
  tft.setTextColor(COLOR_YELLOW);
  tft.print(" d");

  fillRoundRect(3, 78, 122, 26, 4, COLOR_BG_CARD);
  drawRoundRect(3, 78, 122, 26, 4, COLOR_BORDER);

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(7, 82);
  tft.print("Last Month");

  tft.setTextSize(1);
  tft.setTextColor(COLOR_LIGHT_GRAY);
  formatMoney(money.lastMonth, moneyBuf);
  tft.setCursor(7, 93);
  tft.print(moneyBuf);
  tft.setTextColor(COLOR_GRAY);
  tft.print(" VND");

  fillRoundRect(3, 107, 122, 17, 3, COLOR_BG_CARD);
  drawRoundRect(3, 107, 122, 17, 3, COLOR_BORDER);

  tft.setTextColor(COLOR_ORANGE);
  tft.setCursor(7, 111);
  tft.print("Avg: ");
  tft.setTextColor(COLOR_WHITE);
  tft.print((int)money.pricePerKWh);
  tft.setTextColor(COLOR_GRAY);
  tft.print(" VND/kWh");
}

void formatMoney(unsigned long value, char* buf) {
  if (value == 0) {
    strcpy(buf, "0");
    return;
  }
  char tmp[16];
  sprintf(tmp, "%lu", value);
  int len = strlen(tmp);
  int commas = (len - 1) / 3;
  int newLen = len + commas;
  buf[newLen] = '\0';

  int j = newLen - 1;
  int count = 0;
  for (int i = len - 1; i >= 0; i--) {
    buf[j--] = tmp[i];
    count++;
    if (count % 3 == 0 && i > 0) {
      buf[j--] = ',';
    }
  }
}

void switchPage(int page) {
  currentPage = page % TOTAL_PAGES;
  needFullRedraw = true;
  lastPageSwitch = millis();
}

void drawCurrentPage() {
  if (!needFullRedraw) return;

  tft.fillRect(0, 17, 128, 136, COLOR_BG_DARK);
  drawHeader();

  switch (currentPage) {
    case 0: drawPage0(); break;
    case 1: drawPage1(); break;
    case 2: drawPage2(); break;
  }

  drawPageIndicator(currentPage);
  needFullRedraw = false;
}

void checkAlarms() {
  bool prevOV = status.overVoltage;
  bool prevOC = status.overCurrent;

  status.overVoltage = (sensor.voltage > VOLTAGE_MAX || sensor.voltage < VOLTAGE_MIN);
  status.overCurrent = (sensor.current > CURRENT_MAX);

  if (prevOV != status.overVoltage || prevOC != status.overCurrent) {
    needFullRedraw = true;
  }
}

void updateTime() {
  timeNow.second++;
  if (timeNow.second >= 60) {
    timeNow.second = 0;
    timeNow.minute++;
    if (timeNow.minute >= 60) {
      timeNow.minute = 0;
      timeNow.hour++;
      if (timeNow.hour >= 24) {
        timeNow.hour = 0;
      }
    }
    drawHeader();
  }
}

void handleButton() {
  bool reading = (digitalRead(BTN_PAGE) == LOW);
  if (reading && !btnPressed && (millis() - lastBtnPressTime > 200)) {
    btnPressed = true;
    lastBtnPressTime = millis();
    switchPage(currentPage + 1);
  }
  if (!reading) {
    btnPressed = false;
  }
}

void drawSplashScreen() {
  tft.fillScreen(COLOR_BG_DARK);

  drawBoltIcon(58, 35, COLOR_CYAN);
  drawBoltIcon(62, 35, COLOR_CYAN);
  drawBoltIcon(60, 33, COLOR_CYAN);
  drawBoltIcon(60, 37, COLOR_CYAN);

  tft.drawCircle(62, 45, 18, COLOR_CYAN);
  tft.drawCircle(62, 45, 20, RGB565(0, 100, 150));

  tft.setTextSize(1);
  tft.setTextColor(COLOR_WHITE);

  tft.setCursor(25, 75);
  tft.print("SMART  HOME");

  tft.setTextColor(COLOR_CYAN);
  tft.setCursor(16, 90);
  tft.print("ENERGY MONITOR");

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(40, 110);
  tft.print("v1.0.0");

  tft.drawRoundRect(20, 130, 88, 6, 2, COLOR_BORDER);
  for (int i = 0; i < 84; i++) {
    tft.fillRect(22, 132, i, 2, COLOR_CYAN);
    delay(15);
  }

  tft.setTextColor(COLOR_GRAY);
  tft.setCursor(42, 145);
  tft.print("BTL IoT");
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(0));
  Serial.println(F("Smart Home Energy Monitor - Starting..."));

  pinMode(BTN_PAGE, INPUT_PULLUP);

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(0);

  drawSplashScreen();
  delay(1500);

  // Khởi tạo mạng Wi-Fi & MQTT từ network_manager module
  setup_network();

  needFullRedraw = true;
  drawCurrentPage();
}

// ============================================================
// LOOP CHÍNH
// ============================================================
void loop() {
  unsigned long now = millis();

  // 1. Quản lý tự động kết nối Wi-Fi & MQTT (Chạy từ network_manager)
  handle_network();

  // 2. Tạo dữ liệu cảm biến giả lập
  generateMockSensorData();

  // 3. Đẩy dữ liệu lên MQTT Broker định kỳ 3 giây (Dùng hàm từ network_manager)
  if (now - lastMqttSend >= MQTT_INTERVAL) {
    lastMqttSend = now;
    publishMQTTData(sensor.voltage, sensor.current, sensor.power, sensor.energy, sensor.powerFactor, sensor.frequency);
  }

  // 4. Xử lý nút nhấn chuyển trang (Chỉ chuyển trang khi nhấn nút D2)
  handleButton();

  // 6. Cập nhật thời gian mỗi giây
  if (now - lastTimeUpdate >= 1000) {
    lastTimeUpdate = now;
    updateTime();
  }

  // 7. Kiểm tra cảnh báo quá tải
  checkAlarms();

  // 8. Vẽ lại trang hiện tại
  drawCurrentPage();

  delay(50);
}
