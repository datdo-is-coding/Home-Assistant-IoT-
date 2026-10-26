#pragma once

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void subbox_espnow_handle_keyword_event(const uint8_t *data, int len);

#ifdef __cplusplus
}
#endif
