#pragma once

#include <stdint.h>
#include "sdkconfig.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define APP_FW_NAME                     "ActionBox"
#define APP_FW_VERSION_MAJOR            1
#define APP_FW_VERSION_MINOR            0
#define APP_FW_VERSION_PATCH            0
#define APP_FW_VERSION_STR              "1.0.0"

#define APP_DEFAULT_NODE_ID             "AB001"
#define APP_DEFAULT_ROOM_ID             "LIVING_ROOM"
#define APP_PROTOCOL_VERSION            3

#define APP_MAX_NODE_ID_LEN             16
#define APP_MAX_ROOM_ID_LEN             16
#define APP_MAX_CH_NAME_LEN             24

#define SAFETY_DEFAULT_MAX_CURRENT_MA   10000

#define SAFETY_ABSOLUTE_MAX_CURRENT_MA  16000

#define SAFETY_OVERCURRENT_PERSIST_MS   300

#define SAFETY_RELAY_STAGGER_DELAY_MS   150

#define SAFETY_COMMS_TIMEOUT_MS         5000

#define SAFETY_WATCHDOG_TIMEOUT_MS      5000

#define BUTTON_DEBOUNCE_TIME_MS         30
#define BUTTON_LONG_PRESS_TIME_MS       1200
#define BUTTON_HOLD_FACTORY_RESET_MS    10000

#define SENSOR_SAMPLE_INTERVAL_MS       200

#define TELEMETRY_REPORT_INTERVAL_MS    1000

#define TASK_PRIORITY_SAFETY            (configMAX_PRIORITIES - 1)
#define TASK_PRIORITY_RELAY             (configMAX_PRIORITIES - 2)
#define TASK_PRIORITY_BUTTON            (configMAX_PRIORITIES - 3)
#define TASK_PRIORITY_SENSOR            (configMAX_PRIORITIES - 4)
#define TASK_PRIORITY_NETWORK           (configMAX_PRIORITIES - 5)
#define TASK_PRIORITY_TELEMETRY         (tskIDLE_PRIORITY + 2)

#define TASK_STACK_SIZE_SAFETY          4096
#define TASK_STACK_SIZE_RELAY           4096
#define TASK_STACK_SIZE_BUTTON          3072
#define TASK_STACK_SIZE_SENSOR          4096
#define TASK_STACK_SIZE_NETWORK         8192
#define TASK_STACK_SIZE_TELEMETRY       3072

#define QUEUE_CAPACITY_RELAY_CMD        16
#define QUEUE_CAPACITY_SENSOR_DATA      16
#define QUEUE_CAPACITY_NETWORK_TX       16
#define QUEUE_CAPACITY_NETWORK_RX       16

#ifdef __cplusplus
}
#endif

#ifndef APP_ESPNOW_CHANNEL
#define APP_ESPNOW_CHANNEL CONFIG_ACTIONBOX_ESPNOW_CHANNEL
#endif
#if APP_ESPNOW_CHANNEL < 1 || APP_ESPNOW_CHANNEL > 13
#error "Invalid ESP-NOW channel"
#endif

#define SAFETY_SENSOR_TIMEOUT_MS 2000
