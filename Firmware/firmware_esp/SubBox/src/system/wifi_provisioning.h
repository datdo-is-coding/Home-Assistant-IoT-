/**
 * @file wifi_provisioning.h
 * @brief SubBox SoftAP Captive Portal Wi-Fi Provisioning Engine
 */

#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Start SoftAP Captive Portal Provisioning.
 * Spawns SoftAP "SubBox-Setup-XXXX", DNS redirection, and embedded HTTP setup portal.
 */
esp_err_t wifi_provisioning_start(void);

/**
 * @brief Stop provisioning portal and free resources.
 */
void wifi_provisioning_stop(void);

/**
 * @brief Check if provisioning mode is active.
 */
bool wifi_provisioning_is_active(void);

#ifdef __cplusplus
}
#endif
