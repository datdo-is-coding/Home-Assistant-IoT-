#include "host_idf.h"
#include "device_manager.h"
#include "device_reset.h"
#include "espnow_transport.h"
#include "led_driver.h"
#include "nvs_storage.h"
#include "voice_capture.h"

static bool pairing = false, locked = false;
static LedPattern indicator = LedPattern::OFF;
bool hc_runtime_enabled() { return false; }
extern "C" bool is_reset_locked() { return locked; }
extern "C" void espnow_transport_set_pairing_mode(bool active) { pairing = active; }
extern "C" esp_err_t relay_toggle(uint8_t) { assert(false); return ESP_FAIL; }
extern "C" RelayState relay_get_state(uint8_t) { assert(false); return RELAY_STATE_OFF; }
extern "C" void nvs_storage_record_relay_state(uint8_t, RelayState) { assert(false); }
extern "C" void voice_capture_start_streaming(uint8_t) { assert(false); }
extern "C" uint32_t nvs_storage_get_owner_epoch() { return 0; }
extern "C" esp_err_t prepare_reset(ResetKind, const char*, uint32_t) { assert(false); return ESP_FAIL; }
extern "C" esp_err_t execute_confirmed_reset(ResetKind, const char*) { assert(false); return ESP_FAIL; }
extern "C" void cancel_armed_reset() { assert(false); }
extern "C" void led_set_pattern(uint8_t, LedDriverPattern) { assert(false); }
void led_set_pattern(uint8_t ch, LedPattern pattern) { assert(ch == 1); indicator = pattern; }

int main() {
    auto gesture = classify_release(6000, false, ArmedKind::NONE);
    assert(gesture == ButtonAction::START_SETUP);
    device_manager_on_button_event(1, gesture, nullptr);
    assert(pairing && "BUT1 setup must actually enable ESP-NOW pairing");
    assert(indicator == LedPattern::CLAIMING);
    pairing = false;
    locked = true;
    device_manager_on_button_event(1, gesture, nullptr);
    assert(!pairing);
}
