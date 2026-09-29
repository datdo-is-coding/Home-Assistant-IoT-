#include "security_config.h"
#include "nvs.h"
#include "driver/gpio.h"
#include <cstring>

namespace SecurityConfig {
std::string get(const char* key) {
    nvs_handle_t h;
    if (nvs_open("subbox_sec", NVS_READONLY, &h) != ESP_OK) return {};
    size_t size = 0;
    std::string result;
    if (nvs_get_str(h, key, nullptr, &size) == ESP_OK && size > 0 && size <= 8192) {
        result.resize(size);
        if (nvs_get_str(h, key, result.data(), &size) == ESP_OK) result.resize(size - 1);
        else result.clear();
    }
    nvs_close(h);
    return result;
}
bool physicalPresence() { return gpio_get_level(GPIO_NUM_0) == 0; }
esp_err_t set(const char* key, const std::string& value) {
    if (!physicalPresence()) return ESP_ERR_INVALID_STATE;
    const char* allowed[] = {"mqtt_user", "mqtt_pass", "ca_pem", "ws_uri", "ws_token", "mqtt_uri"};
    bool valid = false;
    for (auto name : allowed) valid |= strcmp(key, name) == 0;
    if (!valid || value.empty() || value.size() > 8191) return ESP_ERR_INVALID_ARG;
    if (strcmp(key, "mqtt_uri") == 0 && value.rfind("mqtts://", 0) != 0) return ESP_ERR_INVALID_ARG;
    if (strcmp(key, "ws_uri") == 0 && value.rfind("wss://", 0) != 0) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t err = nvs_open("subbox_sec", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_set_str(h, key, value.c_str());
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}
bool loadPeer(unsigned slot, TrustedPeer& peer) {
    if (slot >= 4) return false;
    nvs_handle_t h;
    if (nvs_open("subbox_sec", NVS_READONLY, &h) != ESP_OK) return false;
    char key[] = "peer0"; key[4] += slot;
    size_t size = sizeof(peer);
    bool ok = nvs_get_blob(h, key, &peer, &size) == ESP_OK && size == sizeof(peer);
    nvs_close(h);
    return ok;
}
esp_err_t savePeer(const TrustedPeer& peer) {
    if (!physicalPresence()) return ESP_ERR_INVALID_STATE;
    if (peer.mac[0] & 1) return ESP_ERR_INVALID_ARG;
    int selected = -1;
    for (unsigned slot = 0; slot < 4; ++slot) {
        TrustedPeer old{};
        if (loadPeer(slot, old)) {
            if (memcmp(peer.mac, old.mac, 6) == 0) { selected = slot; break; }
        } else if (selected < 0) selected = slot;
    }
    if (selected < 0) return ESP_ERR_NO_MEM;
    nvs_handle_t h;
    esp_err_t err = nvs_open("subbox_sec", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    char key[] = "peer0"; key[4] += selected;
    err = nvs_set_blob(h, key, &peer, sizeof(peer));
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}
bool parseHex(const std::string& text, uint8_t* output, size_t bytes) {
    if (text.size() != bytes * 2) return false;
    auto digit = [](char c) -> int {
        if (c >= '0' && c <= '9') return c-'0';
        if (c >= 'a' && c <= 'f') return c-'a'+10;
        if (c >= 'A' && c <= 'F') return c-'A'+10;
        return -1;
    };
    for (size_t i=0; i<bytes; ++i) {
        int a=digit(text[2*i]), b=digit(text[2*i+1]);
        if (a<0 || b<0) return false;
        output[i]=(a<<4)|b;
    }
    return true;
}
}
