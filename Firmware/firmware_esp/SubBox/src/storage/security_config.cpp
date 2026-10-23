#include "security_config.h"
#include "config/board_pins.h"
#include "nvs.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include <cstring>
#include <atomic>

namespace SecurityConfig {
static std::atomic<int64_t> s_pairing_window_expires_us{0};

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
bool physicalPresence() {
    static bool s_pin_inited = false;
    if (!s_pin_inited) {
        gpio_config_t cfg = {};
        cfg.pin_bit_mask = 1ULL << BOARD_PIN_BUTTON_CONFIG;
        cfg.mode = GPIO_MODE_INPUT;
        cfg.pull_up_en = (BOARD_BUTTON_ACTIVE_LEVEL == 0) ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE;
        cfg.pull_down_en = (BOARD_BUTTON_ACTIVE_LEVEL == 1) ? GPIO_PULLDOWN_ENABLE : GPIO_PULLDOWN_DISABLE;
        cfg.intr_type = GPIO_INTR_DISABLE;
        gpio_config(&cfg);
        s_pin_inited = true;
    }
    return gpio_get_level(BOARD_PIN_BUTTON_CONFIG) == BOARD_BUTTON_ACTIVE_LEVEL;
}

void openPairingWindow(uint32_t duration_ms) {
    if (physicalPresence()) {
        s_pairing_window_expires_us.store(esp_timer_get_time() + ((int64_t)duration_ms * 1000));
    }
}

bool isPairingAllowed() {
    if (physicalPresence()) {
        openPairingWindow(180000);
        return true;
    }
    int64_t expires_us = s_pairing_window_expires_us.load();
    if (expires_us > 0) {
        return esp_timer_get_time() < expires_us;
    }
    return false;
}

bool hasConfiguredPeers() {
    for (unsigned slot = 0; slot < 4; ++slot) {
        TrustedPeer p{};
        if (loadPeer(slot, p)) return true;
        RegisteredPeer registered{};
        if (loadRegistration(slot, registered)) return true;
    }
    return false;
}

bool isPeerTrusted(const uint8_t* mac) {
    if (!mac) return false;
    // CRITICAL: NEVER automatically trust when peer list is empty!
    for (unsigned slot = 0; slot < 4; ++slot) {
        TrustedPeer p{};
        if (loadPeer(slot, p)) {
            if (memcmp(p.mac, mac, 6) == 0) return true;
        }
    }
    return false;
}

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
    if (!isPairingAllowed()) return ESP_ERR_INVALID_STATE;
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

esp_err_t clearPeers() {
    nvs_handle_t h;
    esp_err_t err = nvs_open("subbox_sec", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    for (unsigned slot = 0; slot < 4; ++slot) {
        char key[] = "peer0"; key[4] += slot;
        nvs_erase_key(h, key);
        char reg_key[] = "reg0"; reg_key[3] += slot;
        nvs_erase_key(h, reg_key);
    }
    err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t clearCredentials() {
    nvs_handle_t h;
    esp_err_t err = nvs_open("subbox_sec", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    const char* cred_keys[] = {"mqtt_user", "mqtt_pass", "ca_pem", "ws_uri", "ws_token", "mqtt_uri"};
    for (auto k : cred_keys) {
        nvs_erase_key(h, k);
    }
    err = nvs_commit(h);
    nvs_close(h);
    return err;
}

uint32_t getOwnerEpoch() {
    nvs_handle_t h;
    if (nvs_open("subbox_sec", NVS_READONLY, &h) != ESP_OK) return 1;
    uint32_t epoch = 1;
    nvs_get_u32(h, "owner_epoch", &epoch);
    nvs_close(h);
    return (epoch == 0) ? 1 : epoch;
}

esp_err_t setOwnerEpoch(uint32_t epoch) {
    nvs_handle_t h;
    esp_err_t err = nvs_open("subbox_sec", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_set_u32(h, "owner_epoch", epoch);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t incrementOwnerEpoch() {
    uint32_t current = getOwnerEpoch();
    return setOwnerEpoch(current + 1);
}

esp_err_t networkReset() {
    s_pairing_window_expires_us.store(esp_timer_get_time() + (180LL * 1000 * 1000));
    return ESP_OK;
}

esp_err_t factoryReset() {
    s_pairing_window_expires_us.store(0);
    clearCredentials();
    clearPeers();
    incrementOwnerEpoch();
    return ESP_OK;
}
}

namespace SecurityConfig {
bool loadRegistration(unsigned slot, RegisteredPeer& peer) {
    if (slot>=4) return false;
    nvs_handle_t h;
    if (nvs_open("subbox_sec",NVS_READONLY,&h)!=ESP_OK) return false;
    char key[]="reg0"; key[3]+=slot;
    size_t size=sizeof(peer);
    const bool ok=nvs_get_blob(h,key,&peer,&size)==ESP_OK && size==sizeof(peer) && valid_claim(peer.claim);
    nvs_close(h); return ok;
}
esp_err_t saveRegistration(const RegisteredPeer& peer) {
    if (!valid_claim(peer.claim) || (peer.mac[0]&1)) return ESP_ERR_INVALID_ARG;
    int selected=-1; unsigned used=0;
    for(unsigned i=0;i<4;++i) {
        TrustedPeer encrypted{};
        if(loadPeer(i,encrypted)) {
            ++used;
            if(memcmp(encrypted.mac,peer.mac,6)==0) return ESP_ERR_INVALID_STATE;
        }
        RegisteredPeer old{};
        if(loadRegistration(i,old)) {
            ++used;
            if(memcmp(old.mac,peer.mac,6)==0) {
                // Recover a lost MQTT receipt without reopening physical setup.
                if(memcmp(&old,&peer,sizeof(peer))==0) return ESP_OK;
                selected=i;
            }
        }
    }
    if(!isPairingAllowed()) return ESP_ERR_INVALID_STATE;
    if(selected<0) {
        if(used>=4) return ESP_ERR_NO_MEM;
        for(unsigned i=0;i<4;++i) { RegisteredPeer old{}; if(!loadRegistration(i,old)) {selected=i;break;} }
    }
    if(selected<0) return ESP_ERR_NO_MEM;
    nvs_handle_t h;
    esp_err_t err=nvs_open("subbox_sec",NVS_READWRITE,&h);
    if(err!=ESP_OK) return err;
    char key[]="reg0"; key[3]+=selected;
    err=nvs_set_blob(h,key,&peer,sizeof(peer));
    if(err==ESP_OK) err=nvs_commit(h);
    nvs_close(h); return err;
}
}
