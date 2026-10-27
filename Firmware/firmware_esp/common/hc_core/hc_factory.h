#pragma once
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Trusted USB-only manufacturing build; a normal build never embeds credentials. */
esp_err_t hc_factory_apply(void);
#ifdef __cplusplus
}
#endif
