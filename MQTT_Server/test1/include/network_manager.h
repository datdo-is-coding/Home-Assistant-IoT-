#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>

// Struct trạng thái kết nối
struct StatusFlags {
  bool wifiConnected;
  bool mqttConnected;
  bool overVoltage;    // Quá áp
  bool overCurrent;    // Quá dòng
};

// Cấu hình Wi-Fi & MQTT
extern const char* ssid;
extern const char* password;
extern const char* mqtt_server;
extern const int mqtt_port;

extern WiFiClient espClient;
extern PubSubClient client;
extern StatusFlags status;

// Các hàm quản lý mạng Wi-Fi & MQTT
void setup_network();
void setup_wifi();
void reconnectMQTT();
void handle_network();
void publishMQTTData(float voltage, float current, float power, float energy, float pf, float freq);

#endif // NETWORK_MANAGER_H
