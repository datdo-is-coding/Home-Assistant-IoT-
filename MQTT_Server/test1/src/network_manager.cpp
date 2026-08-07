#include "network_manager.h"

// Cấu hình Wi-Fi
const char* ssid = "NHA 19G Tang 4";
const char* password = "0983656645";

// Cấu hình MQTT Broker
const char* mqtt_server = "192.168.41.101";
const int mqtt_port = 1883;

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.print("Đang kết nối Wi-Fi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 20) {
    delay(500);
    Serial.print(".");
    tries++;
  }

  status.wifiConnected = (WiFi.status() == WL_CONNECTED);
  if (status.wifiConnected) {
    Serial.println("\n✅ Wi-Fi kết nối thành công!");
    Serial.print("IP ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n❌ Wi-Fi thất bại!");
  }
}

void reconnectMQTT() {
  if (!client.connected()) {
    status.mqttConnected = false;
    Serial.print("Đang nối MQTT Broker...");
    String clientId = "ESP32Energy-";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str())) {
      Serial.println(" Thành công!");
      status.mqttConnected = true;
    } else {
      Serial.print(" Thất bại, rc=");
      Serial.println(client.state());
    }
  } else {
    status.mqttConnected = true;
  }
}

void setup_network() {
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
}

void handle_network() {
  if (WiFi.status() != WL_CONNECTED) {
    status.wifiConnected = false;
    setup_wifi();
  } else {
    status.wifiConnected = true;
  }

  if (!client.connected()) {
    reconnectMQTT();
  }
  client.loop();
}

void publishMQTTData(float voltage, float current, float power, float energy, float pf, float freq) {
  if (!client.connected()) return;

  String payload = "{";
  payload += "\"device_id\": \"ESP32_Energy_Monitor\",";
  payload += "\"voltage\": " + String(voltage, 2) + ",";
  payload += "\"current\": " + String(current, 2) + ",";
  payload += "\"power\": " + String(power, 2) + ",";
  payload += "\"energy\": " + String(energy, 2) + ",";
  payload += "\"power_factor\": " + String(pf, 2) + ",";
  payload += "\"frequency\": " + String(freq, 2);
  payload += "}";

  Serial.print("📡 Gửi bản tin MQTT: ");
  Serial.println(payload);
  client.publish("esp32/sensor/data", payload.c_str());
}
