#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
bool gateway_discover(char* out_ip, size_t max_ip_len, uint16_t* out_ws_port, uint16_t* out_mqtt_port, uint32_t timeout_ms = 3000);
}
#else
bool gateway_discover(char* out_ip, size_t max_ip_len, uint16_t* out_ws_port, uint16_t* out_mqtt_port, uint32_t timeout_ms);
#endif
