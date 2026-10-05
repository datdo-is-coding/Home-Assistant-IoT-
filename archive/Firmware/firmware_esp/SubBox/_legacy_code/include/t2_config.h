/*
 * T2 Zone Controller — Hardware & Network Configuration
 * DTV Smart Home — 3-Tier IoT Architecture
 */

#ifndef T2_CONFIG_H
#define T2_CONFIG_H

#include "driver/gpio.h"
#include "driver/i2s_std.h"

/* ─── Firmware Info ─────────────────────────────────────────────────── */

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

/* ─── Default Zone Identity ─────────────────────────────────────────── */

#define DEFAULT_ZONE_NAME      "living_room"
#define DEFAULT_ZONE_LABEL     "Phòng Khách"

/* ─── I2S Speaker / DAC (MAX98357A) ─────────────────────────────────── */

#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_I2S_GPIO_BCLK    GPIO_NUM_17   /* Schematic: SP_BCLK (IO17) */
#define SPK_I2S_GPIO_WS      GPIO_NUM_18   /* Schematic: SP_LRC  (IO18) */
#define SPK_I2S_GPIO_DOUT    GPIO_NUM_21   /* Schematic: SP_DOUT (IO21) */
#define SPK_SD_GPIO          GPIO_NUM_2    /* Schematic: SP_SD   (IO2 - Amp Shutdown/Enable) */

/* ─── Optional Local Microphone (INMP441) ────────────────────────────── */

#define HAS_LOCAL_MIC        1
#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    GPIO_NUM_15   /* Schematic: MIC_BCLK (IO15) */
#define MIC_I2S_GPIO_WS      GPIO_NUM_16   /* Schematic: MIC_WS   (IO16) */
#define MIC_I2S_GPIO_DIN     GPIO_NUM_8    /* Schematic: MIC_DIN  (IO8)  */

/* ─── Status LEDs ────────────────────────────────────────────────────── */

#define LED1_GPIO            GPIO_NUM_48   /* System / Wi-Fi status */
#define LED2_GPIO            GPIO_NUM_47   /* Voice / Mesh activity */

/* ─── Buttons (Optional local controls) ──────────────────────────────── */

#define BUT1_GPIO            GPIO_NUM_1    /* Toggle or Factory Reset */
#define BUT2_GPIO            GPIO_NUM_3    /* Toggle */

/* ─── Infrared (IR) Blaster & Receiver ───────────────────────────────── */

#define HAS_IR               1
#define IR_TX_GPIO           GPIO_NUM_4    /* RMT IR LED transmitter */
#define IR_RX_GPIO           GPIO_NUM_5    /* TSOP / VS1838B receiver (optional) */

/* ─── Wi-Fi & ESP-NOW Mesh ───────────────────────────────────────────── */

#define ESPNOW_WIFI_CHANNEL  11            /* Shared channel between T1 and T2 */
#define MAX_T1_NODES_PER_ZONE 16           /* Max managed T1 nodes in this zone */
#define NODE_HEARTBEAT_TIMEOUT_MS 90000    /* 90s without hello = marked offline */

/* ─── Gateway Endpoints ──────────────────────────────────────────────── */

#define DEFAULT_GATEWAY_IP   "192.168.11.29"
#define DEFAULT_MQTT_PORT    1883
#define DEFAULT_WS_PORT      8765
#define DEFAULT_MQTT_USER    "admin"
#define DEFAULT_MQTT_PASS    "SmarthomePass2026!"

#endif /* T2_CONFIG_H */
