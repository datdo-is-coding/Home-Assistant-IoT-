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
bool isPairingAllowed();
void openPairingWindow(uint32_t duration_ms = 60000);
bool hasConfiguredPeers();
bool isPeerTrusted(const uint8_t* mac);
esp_err_t clearPeers();
esp_err_t clearCredentials();
esp_err_t networkReset();
esp_err_t factoryReset();
uint32_t getOwnerEpoch();
esp_err_t setOwnerEpoch(uint32_t epoch);
esp_err_t incrementOwnerEpoch();
}

#include "registration_wire.h"
namespace SecurityConfig {
bool loadRegistration(unsigned slot, RegisteredPeer& peer);
esp_err_t saveRegistration(const RegisteredPeer& peer);
}
