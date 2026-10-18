#ifndef T2_CONFIG_H
#define T2_CONFIG_H

#include "driver/gpio.h"
#include "driver/i2s_std.h"

#define T2_FW_NAME        "T2_Zone_Controller"

#ifndef FW_VERSION_MAJOR
#define FW_VERSION_MAJOR  1
#endif
#ifndef FW_VERSION_MINOR
#define FW_VERSION_MINOR  0
#endif
#ifndef FW_VERSION_PATCH
#define FW_VERSION_PATCH  0
#endif

#define DEFAULT_ZONE_NAME      "living_room"
#define DEFAULT_ZONE_LABEL     "Phòng Khách"

#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_I2S_GPIO_BCLK    GPIO_NUM_17
#define SPK_I2S_GPIO_WS      GPIO_NUM_18
#define SPK_I2S_GPIO_DOUT    GPIO_NUM_21
#define SPK_SD_GPIO          GPIO_NUM_2

#define HAS_LOCAL_MIC        1
#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    GPIO_NUM_15
#define MIC_I2S_GPIO_WS      GPIO_NUM_16
#define MIC_I2S_GPIO_DIN     GPIO_NUM_8

#define LED1_GPIO            GPIO_NUM_48
#define LED2_GPIO            GPIO_NUM_47

#define BUT1_GPIO            GPIO_NUM_1
#define BUT2_GPIO            GPIO_NUM_3

#define HAS_IR               1
#define IR_TX_GPIO           GPIO_NUM_4
#define IR_RX_GPIO           GPIO_NUM_5

#define ESPNOW_WIFI_CHANNEL  11
#define MAX_T1_NODES_PER_ZONE 16
#define NODE_HEARTBEAT_TIMEOUT_MS 90000

#define DEFAULT_GATEWAY_IP   "192.168.11.29"
#define DEFAULT_MQTT_PORT    1883
#define DEFAULT_WS_PORT      8765
#define DEFAULT_MQTT_USER    "admin"
#define DEFAULT_MQTT_PASS    "SmarthomePass2026!"

#endif
