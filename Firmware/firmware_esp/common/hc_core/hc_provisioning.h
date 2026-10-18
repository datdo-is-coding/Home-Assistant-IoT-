#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
#define HC_ENROLLMENT_SIZE 547
#define HC_ENROLLMENT_RECEIPT_SIZE 78
#define HC_PEER_GRANT_SIZE 110
#define HC_PEER_RECEIPT_SIZE 82
#define HC_PAIR_HELLO_SIZE 60

typedef struct {
    uint32_t schema, node_id, parent_id, revision;
    uint64_t peer_generation;
    uint8_t key[32], pmk[16], channel, subbox, committed, peer_count;
    char factory_id[16], model[32], wifi_ssid[33], wifi_password[65], mqtt_uri[128];
    uint8_t ota_pubkey[65], claim_nonce[32];
    char claim_id[32], room_id[32];
    struct { uint32_t node_id; uint8_t mac[6], lmk[16], nonce[32]; } peers[4];
} hc_provisioned_config;
esp_err_t hc_provisioning_load(hc_provisioned_config *out);

esp_err_t hc_provisioning_start(bool subbox);
void hc_provisioning_stop(void);
bool hc_provisioning_active(void);

esp_err_t hc_provisioning_button_init(bool subbox);
esp_err_t hc_provisioning_reset(void);
esp_err_t hc_provisioning_revision(uint32_t revision);

esp_err_t hc_provisioning_apply(const uint8_t *packet, size_t length);

esp_err_t hc_provisioning_install_peer(const uint8_t *grant, size_t length);
esp_err_t hc_provisioning_peer_receipt(const uint8_t mac[6], const uint8_t *hello,
                                      size_t length, uint8_t receipt[HC_PEER_RECEIPT_SIZE]);

esp_err_t hc_provisioning_pair_hello(uint8_t out[HC_PAIR_HELLO_SIZE]);
esp_err_t hc_provisioning_pair_receive(const uint8_t mac[6], const uint8_t *data,
                                      size_t length, uint8_t reply[HC_PAIR_HELLO_SIZE]);

esp_err_t hc_provisioning_receipt(bool gateway_authenticated,
                                 uint8_t out[HC_ENROLLMENT_RECEIPT_SIZE]);

esp_err_t hc_provisioning_commit(void);
#ifdef __cplusplus
}
#endif
