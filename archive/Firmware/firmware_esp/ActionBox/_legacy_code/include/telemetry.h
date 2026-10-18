#ifndef TELEMETRY_H
#define TELEMETRY_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t telemetry_init(void);

void telemetry_send_now(void);

#ifdef __cplusplus
}
#endif

#endif
