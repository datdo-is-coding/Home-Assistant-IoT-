#include "radio_host.h"
#define private public
#include "audio/audio_transport/espnow_audio_transport.h"
#undef private
#include "storage/nvs_manager.h"
#include "system/subbox_led.h"
#include "cJSON.h"
static bool physical=false, fail_save=false, bad_receipt=false;
static std::vector<RegisteredPeer> saved;
static unsigned sends=0;
namespace SecurityConfig {
bool physicalPresence() {return physical;}
bool isPairingAllowed() {return physical;}
bool isPeerTrusted(const uint8_t*) {return false;}
bool loadPeer(unsigned,TrustedPeer&) {return false;}
bool loadRegistration(unsigned slot,RegisteredPeer& p) {
    if(slot>=saved.size()) return false;p=saved[slot];return true;
}
esp_err_t saveRegistration(const RegisteredPeer& p) {
    if(fail_save) return ESP_FAIL;
    for(auto& old:saved) if(memcmp(old.mac,p.mac,6)==0) {old=p;return ESP_OK;}
    saved.push_back(p);return ESP_OK;
}
}
esp_err_t NVSManager::loadConfig(SubBoxPersistentConfig& c) {c={};return ESP_OK;}
extern "C" void subbox_led_peer_seen() {}
extern "C" bool subbox_led_wifi_connected() {return true;}
extern "C" bool subbox_led_mqtt_connected() {return true;}
extern "C" void subbox_espnow_handle_keyword_event(const uint8_t*,int) {}
int esp_now_send(const uint8_t* mac,const uint8_t* data,size_t len) {
    if(data[0]!=CLAIM_FRAME) return ESP_OK;
    assert(len==sizeof(ClaimFrame) && len<=250);++sends;
    ClaimFrame claim;memcpy(&claim,data,len);assert(valid_claim(claim));
    ClaimReceipt receipt{};receipt.type=CLAIM_RECEIPT;receipt.version=3;receipt.success=1;
    receipt.revision=claim.revision;receipt.owner_epoch=2;
    strcpy(receipt.node_id,claim.node_id);strcpy(receipt.operation,claim.operation);
    if(bad_receipt) strcpy(receipt.operation,"wrong_operation");
    EspNowAudioTransport::getInstance()->handleReceivedPacket(mac,(const uint8_t*)&receipt,sizeof(receipt));
    return ESP_OK;
}
int main() {
    const uint8_t mac[]={0x28,0x84,0x85,0x33,0xDD,0xF8};
    const std::string hello=R"({"type":"SETUP","protocol_version":3,"hardware_uid":"28848533DDF8","node_id":"AB28848533DDF8","setup_session":42,"setup_remaining_ms":10000,"config_version":1,"channel_count":3})";
    const std::string claim=R"({"cmd":"claim","device_uid":"AB28848533DDF8","op_id":"op_claim_test","room_key":"livingroom","setup_session":42,"revision":1,"channels":{"ch1":{"type":"light"},"ch2":{"type":"fan"},"ch3":{"type":"switch"}}})";
    std::string result;
    {
        EspNowAudioTransport transport; assert(transport.init());
        int discovered=0;transport.registerJsonCallback([&](const std::string&) {++discovered;});
        transport.handleReceivedPacket(mac,(const uint8_t*)hello.data(),hello.size());
        assert(discovered==0 && !transport.claimDevice(claim,result));
        physical=true;
        transport.handleReceivedPacket(mac,(const uint8_t*)hello.data(),hello.size());
        assert(discovered==1);
        fail_save=true;assert(!transport.claimDevice(claim,result));assert(result.empty() && saved.empty());
        fail_save=false;bad_receipt=true;
        assert(!transport.claimDevice(claim,result));assert(saved.empty());
        bad_receipt=false;
        assert(transport.claimDevice(claim,result));assert(saved.size()==1);
        assert(result.find("CLAIM_APPLIED")!=std::string::npos);
        assert(result.find("op_claim_test")!=std::string::npos);
    }
    physical=false;result.clear();
    {
        EspNowAudioTransport rebooted;assert(rebooted.init());
        assert(rebooted.claimDevice(claim,result)); // persisted enrollment, no physical window needed for identical retry
        assert(saved.size()==1);
        auto different=claim;different.replace(different.find("livingroom"),10,"bedroom");
        assert(!rebooted.claimDevice(different,result));
    }
    assert(sends>=6);
}
