#pragma once
#include <string>
#include <cstdint>
#include "esp_err.h"

struct TrustedPeer { uint8_t mac[6]; uint8_t lmk[16]; };
static_assert(sizeof(TrustedPeer) == 22, "Persistent peer layout");
namespace SecurityConfig {
std::string get(const char* key);
esp_err_t set(const char* key, const std::string& value);
bool loadPeer(unsigned slot, TrustedPeer& peer);
esp_err_t savePeer(const TrustedPeer& peer);
bool parseHex(const std::string& text, uint8_t* output, size_t bytes);
bool physicalPresence();
}
