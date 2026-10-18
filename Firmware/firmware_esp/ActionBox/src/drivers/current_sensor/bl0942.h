#pragma once

#include "current_sensor.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BL0942_DEFAULT_CAL_CURRENT       0.001f
#define BL0942_DEFAULT_CAL_VOLTAGE       0.0000732f
#define BL0942_DEFAULT_CAL_POWER         0.000596f

esp_err_t bl0942_driver_init(void);

esp_err_t bl0942_read_channel(uint8_t channel, CurrentMeasurement *out_meas);

esp_err_t bl0942_get_latest_measurement(uint8_t channel, CurrentMeasurement *out_meas);

esp_err_t bl0942_set_calibration(uint8_t channel, const SensorCalibration *cal);

esp_err_t bl0942_get_calibration(uint8_t channel, SensorCalibration *out_cal);

const ICurrentSensorDriver* bl0942_get_driver(void);

#ifdef __cplusplus
}
#endif
