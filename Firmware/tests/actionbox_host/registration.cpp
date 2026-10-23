#include "host_idf.h"
#include "registration.h"
#include "nvs_storage.h"
#include <vector>
static ActionBoxPersistentConfig config{};
static bool setup = false, fail_save = false, locked = false;
static unsigned saves = 0;
static uint8_t parent[6] = {2,2,3,4,5,6};
bool hc_runtime_enabled() { return false; }
extern "C" bool is_reset_locked() { return locked; }
extern "C" const ActionBoxPersistentConfig* nvs_storage_get_cached_config() { return &config; }
extern "C" esp_err_t nvs_storage_save_config(const ActionBoxPersistentConfig* c) {
    ++saves; if(fail_save) return ESP_FAIL; config = *c; return ESP_OK;
}
extern "C" uint32_t nvs_storage_get_owner_epoch() { return 2; }
extern "C" bool espnow_transport_is_pairing_mode() { return setup; }
extern "C" uint32_t espnow_transport_setup_session() { return 42; }
extern "C" bool espnow_transport_is_paired_subbox(const uint8_t* m) { return memcmp(m,parent,6)==0; }
extern "C" void espnow_transport_set_pairing_mode(bool v) { setup=v; }
extern "C" esp_err_t espnow_transport_pair_subbox(const uint8_t*) { return ESP_OK; }
extern "C" const char* protocol_get_hardware_uid() { return "28848533DDF8"; }
int main() {
    ClaimFrame frame{};
    frame.type = CLAIM_FRAME; frame.version=3; frame.session=42; frame.revision=2;
    strcpy(frame.node_id,"AB28848533DDF8"); strcpy(frame.room,"livingroom");
    strcpy(frame.operation,"op_claim_test");
    strcpy(frame.channels[0],"light"); strcpy(frame.channels[1],"fan"); strcpy(frame.channels[2],"switch");
    ClaimReceipt ack{};
    assert(!registration_apply(parent,frame,ack)); // no physical window
    setup=true; fail_save=true;
    assert(!registration_apply(parent,frame,ack));
    assert(!config.has_assigned_subbox && setup);
    fail_save=false; frame.session=99;
    assert(!registration_apply(parent,frame,ack));
    frame.session=42; locked=true;
    assert(!registration_apply(parent,frame,ack)); locked=false;
    assert(registration_apply(parent,frame,ack));
    assert(config.has_assigned_subbox && !setup && ack.revision==2 && ack.owner_epoch==2);
    assert(memcmp(config.assigned_subbox_mac,parent,6)==0);
    const auto count=saves;
    assert(registration_apply(parent,frame,ack)); // lost receipt, closed setup, no repeated flash write
    assert(saves==count);
    uint8_t attacker[6]={4,2,3,4,5,6};
    assert(!registration_apply(attacker,frame,ack));
    strcpy(frame.room,"different");
    assert(!registration_apply(parent,frame,ack));
    memset(frame.operation,'x',sizeof(frame.operation));
    assert(!registration_apply(parent,frame,ack));
}
