/**
 * @file current_sensor.h
 * @brief Abstract Current & Energy Measurement Interface
 */

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
    uint32_t       current_rms_ma;  /**< RMS Current in Milliamps (mA) */
    uint32_t       voltage_rms_v;   /**< RMS Voltage in Volts (V) */
    int32_t        active_power_w;  /**< Active Power in Watts (W) */
    uint32_t       energy_wh;       /**< Accumulated Energy in Watt-hours */
    SensorValidity validity;        /**< Sensor reading health & validity */
    bool           overcurrent;     /**< Immediate over-current flag */
    uint32_t       sample_count;    /**< Rolling valid sample counter */
    uint32_t       timestamp_ms;    /**< System timestamp of last sample */
} CurrentMeasurement;

typedef struct {
    float current_factor;  /**< Multiplier: raw_irms -> mA */
    float voltage_factor;  /**< Multiplier: raw_vrms -> V */
    float power_factor;    /**< Multiplier: raw_watt -> W */
} SensorCalibration;

/**
 * @brief Abstract Sensor Interface Function Pointers
 */
typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*read)(uint8_t channel, CurrentMeasurement *out_meas);
    esp_err_t (*set_calibration)(uint8_t channel, const SensorCalibration *cal);
    esp_err_t (*get_calibration)(uint8_t channel, SensorCalibration *out_cal);
} ICurrentSensorDriver;

#ifdef __cplusplus
}
#endif
