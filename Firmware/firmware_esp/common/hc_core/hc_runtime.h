#pragma once
#include <stdbool.h>
#include "esp_err.h"
#include "hc_protocol.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef bool (*hc_send_up_fn)(const uint8_t *data, size_t length);
typedef bool (*hc_apply_fn)(uint8_t channel, bool on);
typedef bool (*hc_sample_fn)(uint8_t channel, bool *on, float *amps, bool *valid, uint16_t *fault);
esp_err_t hc_runtime_init(bool subbox, hc_send_up_fn uplink, hc_apply_fn apply, hc_sample_fn sample);
bool hc_runtime_enabled(void);
typedef bool (*hc_application_fn)(uint8_t type,const uint8_t *data,size_t size);
void hc_runtime_set_application_handler(hc_application_fn handler);
bool hc_runtime_emit(uint8_t type,const uint8_t *data,size_t size);
bool hc_runtime_registered(void);
uint32_t hc_runtime_peer_node_id(const uint8_t mac[6]);
bool hc_runtime_online(void);
bool hc_runtime_parent_mac(uint8_t out[6]);
uint32_t hc_runtime_node_id(void);
bool hc_runtime_receive_radio(const uint8_t mac[6], const uint8_t *data, size_t length);
bool hc_runtime_receive_mqtt(const uint8_t *data, size_t length);
bool hc_runtime_trusted_peer(const uint8_t mac[6]);
#ifdef __cplusplus
}
#endif
