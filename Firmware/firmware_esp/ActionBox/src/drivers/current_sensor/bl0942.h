/**
 * @file bl0942.h
 * @brief Belling BL0942 Dedicated Energy Metering IC Driver over UART
 */

#pragma once

#include "current_sensor.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Standard Factory Reference Multipliers for CT with 33R burden */
#define BL0942_DEFAULT_CAL_CURRENT       0.001f       /* Raw -> mA (33R burden, CT) */
#define BL0942_DEFAULT_CAL_VOLTAGE       0.0000732f   /* Raw -> V */
#define BL0942_DEFAULT_CAL_POWER         0.000596f    /* Raw -> W */

/**
 * @brief Initialize BL0942 UART driver for Channel 1 and Channel 2
 * @return ESP_OK on success
 */
esp_err_t bl0942_driver_init(void);

/**
 * @brief Read latest current, voltage, power, and validity from BL0942 for specified channel (Hardware UART read)
 * @param channel Channel ID (1 or 2)
 * @param out_meas Destination measurement pointer
 * @return ESP_OK on success, ESP_ERR_TIMEOUT if chip does not respond, ESP_ERR_INVALID_CRC if checksum fails
 */
esp_err_t bl0942_read_channel(uint8_t channel, CurrentMeasurement *out_meas);

/**
 * @brief Retrieve the latest cached measurement without triggering a hardware UART transaction
 * @param channel Channel ID (1 or 2)
 * @param out_meas Destination measurement pointer
 * @return ESP_OK on success
 */
esp_err_t bl0942_get_latest_measurement(uint8_t channel, CurrentMeasurement *out_meas);

/**
 * @brief Update calibration factors for a channel (dynamically loaded from NVS)
 * @param channel Channel ID (1 or 2)
 * @param cal Pointer to calibration values
 * @return ESP_OK on success
 */
esp_err_t bl0942_set_calibration(uint8_t channel, const SensorCalibration *cal);

/**
 * @brief Retrieve current calibration factors for a channel
 * @param channel Channel ID (1 or 2)
 * @param out_cal Pointer to destination struct
 * @return ESP_OK on success
 */
esp_err_t bl0942_get_calibration(uint8_t channel, SensorCalibration *out_cal);

/**
 * @brief Expose the abstract sensor driver instance
 * @return Pointer to ICurrentSensorDriver
 */
const ICurrentSensorDriver* bl0942_get_driver(void);

#ifdef __cplusplus
}
#endif
