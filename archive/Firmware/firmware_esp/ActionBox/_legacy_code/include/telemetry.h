/*
 * Telemetry Module — T1 Actuator Node
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Reads PZEM-004T energy monitor (if HAS_PZEM) and sends
 * telemetry packets to T2 Zone Controller via ESP-NOW.
 */

#ifndef TELEMETRY_H
#define TELEMETRY_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize telemetry subsystem.
 * If HAS_PZEM is enabled, configures UART and spawns periodic reader task.
 * @return ESP_OK on success
 */
esp_err_t telemetry_init(void);

/**
 * @brief Force sending an immediate telemetry update to T2.
 */
void telemetry_send_now(void);

#ifdef __cplusplus
}
#endif

#endif /* TELEMETRY_H */
