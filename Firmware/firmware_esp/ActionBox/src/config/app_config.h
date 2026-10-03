/**
 * @file app_config.h
 * @brief Application Configuration, Safety Thresholds & FreeRTOS Tunables
 */

#pragma once

#include <stdint.h>
#include "sdkconfig.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================= */
/*                          FIRMWARE & DEVICE IDENTITY                       */
/* ========================================================================= */

#define APP_FW_NAME                     "ActionBox"
#define APP_FW_VERSION_MAJOR            1
#define APP_FW_VERSION_MINOR            0
#define APP_FW_VERSION_PATCH            0
#define APP_FW_VERSION_STR              "1.0.0"

#define APP_DEFAULT_NODE_ID             "AB001"
#define APP_DEFAULT_ROOM_ID             "LIVING_ROOM"
#define APP_PROTOCOL_VERSION            3

/* Maximum string lengths */
#define APP_MAX_NODE_ID_LEN             16
#define APP_MAX_ROOM_ID_LEN             16
#define APP_MAX_CH_NAME_LEN             24


/* ========================================================================= */
/*                       SAFETY & PROTECTION THRESHOLDS                      */
/* ========================================================================= */

/**
 * @brief Maximum Current Protection Limit in Milliamps (RMS)
 * 10000 mA = 10.0 Amps RMS (Standard 10A wall relay socket rating)
 */
#define SAFETY_DEFAULT_MAX_CURRENT_MA   10000

/**
 * @brief Absolute Hard Ceiling Current Limit in Milliamps (RMS)
 * If current exceeds this threshold even for 1 cycle, cut off instantly.
 * 16000 mA = 16.0 Amps (PCB trace/fuse safety ceiling)
 */
#define SAFETY_ABSOLUTE_MAX_CURRENT_MA  16000

/**
 * @brief Overcurrent Persistence Debounce Time in Milliseconds
 * Prevents false trips from harmless inrush current (e.g. motor/SMPS capacitor charge).
 */
#define SAFETY_OVERCURRENT_PERSIST_MS   300

/**
 * @brief Simultaneous Relay Activation Stagger Delay in Milliseconds
 * Enforces a minimum gap between activating Channel 1 and Channel 2 to limit peak inrush.
 */
#define SAFETY_RELAY_STAGGER_DELAY_MS   150

/**
 * @brief SubBox Communication Heartbeat Watchdog Timeout in Milliseconds
 * If no communication is received from SubBox within 10s, scan channels 1-13.
 * NOTE: Local button and relay safety control continues unimpeded!
 */
#define SAFETY_COMMS_TIMEOUT_MS         5000

/**
 * @brief Task Watchdog Timer (TWDT) Timeout in Milliseconds
 */
#define SAFETY_WATCHDOG_TIMEOUT_MS      5000


/* ========================================================================= */
/*                     BUTTON DEBOUNCE & GESTURE TIMING                      */
/* ========================================================================= */

#define BUTTON_DEBOUNCE_TIME_MS         30
#define BUTTON_LONG_PRESS_TIME_MS       1200
#define BUTTON_HOLD_FACTORY_RESET_MS    10000


/* ========================================================================= */
/*                        SENSOR SAMPLING & TELEMETRY                        */
/* ========================================================================= */

/**
 * @brief Interval between BL0942 UART register queries
 */
#define SENSOR_SAMPLE_INTERVAL_MS       200

/**
 * @brief Periodic Telemetry Transmission Interval to SubBox
 */
#define TELEMETRY_REPORT_INTERVAL_MS    1000


/* ========================================================================= */
/*                   FREERTOS TASK PRIORITIES & STACK SIZES                  */
/* ========================================================================= */

#define TASK_PRIORITY_SAFETY            (configMAX_PRIORITIES - 1)  /* Highest: Safety supervisor */
#define TASK_PRIORITY_RELAY             (configMAX_PRIORITIES - 2)  /* Immediate actuation */
#define TASK_PRIORITY_BUTTON            (configMAX_PRIORITIES - 3)  /* Local user interaction */
#define TASK_PRIORITY_SENSOR            (configMAX_PRIORITIES - 4)  /* Continuous sensor polling */
#define TASK_PRIORITY_NETWORK           (configMAX_PRIORITIES - 5)  /* ESP-NOW packets */
#define TASK_PRIORITY_TELEMETRY         (tskIDLE_PRIORITY + 2)      /* Periodic reporting */

#define TASK_STACK_SIZE_SAFETY          4096
#define TASK_STACK_SIZE_RELAY           4096
#define TASK_STACK_SIZE_BUTTON          3072
#define TASK_STACK_SIZE_SENSOR          4096
#define TASK_STACK_SIZE_NETWORK         8192
#define TASK_STACK_SIZE_TELEMETRY       3072

/* Queue Capacities */
#define QUEUE_CAPACITY_RELAY_CMD        16
#define QUEUE_CAPACITY_SENSOR_DATA      16
#define QUEUE_CAPACITY_NETWORK_TX       16
#define QUEUE_CAPACITY_NETWORK_RX       16

#ifdef __cplusplus
}
#endif

// Match the 2.4 GHz AP channel used by SubBox (menuconfig > ActionBox radio).
#ifndef APP_ESPNOW_CHANNEL
#define APP_ESPNOW_CHANNEL CONFIG_ACTIONBOX_ESPNOW_CHANNEL
#endif
#if APP_ESPNOW_CHANNEL < 1 || APP_ESPNOW_CHANNEL > 13
#error "Invalid ESP-NOW channel"
#endif

#define SAFETY_SENSOR_TIMEOUT_MS 2000  /**< Maximum age of a valid current sample before OFF/lockout. */
