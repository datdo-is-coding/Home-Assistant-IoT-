#include "registration.h"
#include "nvs_storage.h"
#include "espnow_transport.h"
#include "actionbox_protocol.h"
#include "device_reset.h"
#include "hc_runtime.h"
#include <cstdio>

bool registration_apply(const uint8_t* source, const ClaimFrame& claim, ClaimReceipt& receipt) {
    receipt = {};
    if (!source || hc_runtime_enabled() || is_reset_locked() || !valid_claim(claim)) return false;
    char expected[16];
    snprintf(expected, sizeof(expected), "AB%s", protocol_get_hardware_uid());
    if (strcmp(expected, claim.node_id) != 0) return false;
    const auto* saved = nvs_storage_get_cached_config();
    bool identical = saved->has_assigned_subbox && memcmp(saved->assigned_subbox_mac,source,6)==0 &&
        saved->config_version == claim.revision && strcmp(saved->node_id,claim.node_id)==0 &&
        strcmp(saved->room_id,claim.room)==0;
    for (int i=0;i<3;++i) identical &= strcmp(saved->channel_names[i],claim.channels[i])==0;
    if (!identical) {
        if (saved->has_assigned_subbox || !espnow_transport_is_pairing_mode() ||
            claim.session != espnow_transport_setup_session() || !espnow_transport_is_paired_subbox(source)) return false;
        auto config = *saved;
        strcpy(config.node_id,claim.node_id);
        strcpy(config.room_id,claim.room);
        for (int i=0;i<3;++i) strcpy(config.channel_names[i],claim.channels[i]);
        memcpy(config.assigned_subbox_mac,source,6);
        config.has_assigned_subbox=true;
        config.config_version=claim.revision;
        if (nvs_storage_save_config(&config) != ESP_OK) return false;
    }
    // A lost receipt can be retried after reboot without another NVS write.
    if (espnow_transport_pair_subbox(source) != ESP_OK) return false;
    espnow_transport_set_pairing_mode(false);
    receipt.type=CLAIM_RECEIPT; receipt.version=3; receipt.success=1;
    receipt.revision=claim.revision; receipt.owner_epoch=nvs_storage_get_owner_epoch();
    strcpy(receipt.node_id,claim.node_id); strcpy(receipt.operation,claim.operation);
    return true;
}
