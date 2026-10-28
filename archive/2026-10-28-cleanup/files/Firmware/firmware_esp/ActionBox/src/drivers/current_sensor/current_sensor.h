#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SENSOR_STATUS_VALID       = 0,
    SENSOR_STATUS_UNINITIALIZED = 1,
    SENSOR_STATUS_TIMEOUT     = 2,
    SENSOR_STATUS_CHECKSUM_ERR= 3,
    SENSOR_STATUS_OUT_OF_RANGE= 4
} SensorValidity;

typedef struct {
    uint32_t       current_rms_ma;
    uint32_t       voltage_rms_v;
    int32_t        active_power_w;
    uint32_t       energy_wh;
    SensorValidity validity;
    bool           overcurrent;
    uint32_t       sample_count;
    uint32_t       timestamp_ms;
} CurrentMeasurement;

typedef struct {
    float current_factor;
    float voltage_factor;
    float power_factor;
} SensorCalibration;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*read)(uint8_t channel, CurrentMeasurement *out_meas);
    esp_err_t (*set_calibration)(uint8_t channel, const SensorCalibration *cal);
    esp_err_t (*get_calibration)(uint8_t channel, SensorCalibration *out_cal);
} ICurrentSensorDriver;

#ifdef __cplusplus
}
#endif
