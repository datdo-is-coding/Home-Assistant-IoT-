#pragma once
#include "hc_runtime.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef bool (*hc_ota_emit_fn)(uint8_t type,const uint8_t *payload,size_t length);
esp_err_t hc_ota_init(hc_ota_emit_fn emit,bool subbox);
bool hc_ota_receive(uint8_t type,const uint8_t *payload,size_t length);
/* Signal completed local initialization/diagnostics; connectivity and relay load are not health evidence. */
void hc_ota_health_ready(void);
#ifdef __cplusplus
}
#endif
