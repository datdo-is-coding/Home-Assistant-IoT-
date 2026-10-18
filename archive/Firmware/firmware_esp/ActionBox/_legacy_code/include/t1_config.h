#ifndef T1_CONFIG_H
#define T1_CONFIG_H

#define T1_FW_NAME        "T1_Actuator"

#ifndef FW_VERSION_MAJOR
#define FW_VERSION_MAJOR  1
#endif
#ifndef FW_VERSION_MINOR
#define FW_VERSION_MINOR  0
#endif
#ifndef FW_VERSION_PATCH
#define FW_VERSION_PATCH  0
#endif

#ifndef HAS_RELAY
#define HAS_RELAY     1
#endif

#ifndef HAS_MIC
#define HAS_MIC       1
#endif

#ifndef HAS_WAKENET
#define HAS_WAKENET   1
#endif

#ifndef HAS_ADPCM
#define HAS_ADPCM     1
#endif

#ifndef HAS_PZEM
#define HAS_PZEM      0
#endif

#define RELAY_CH1_GPIO    4
#define RELAY_CH2_GPIO    5
#define RELAY_ACTIVE_LOW  true

#define BUT1_GPIO         1
#define BUT2_GPIO         3

#define LED1_GPIO         48
#define LED2_GPIO         47

#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    15
#define MIC_I2S_GPIO_WS      16
#define MIC_I2S_GPIO_DIN     8

#if HAS_PZEM
#define PZEM_UART_NUM        UART_NUM_1
#define PZEM_UART_TX_GPIO    43
#define PZEM_UART_RX_GPIO    44
#define PZEM_BAUD_RATE       9600
#endif

#define ESPNOW_WIFI_CHANNEL  11
#define ESPNOW_HEARTBEAT_S   30
#define ESPNOW_TELE_INTERVAL_MS  2000

#define AUDIO_SAMPLE_RATE    16000
#define AUDIO_BITS           16
#define AUDIO_CHANNELS       1

#define VAD_SILENCE_ENERGY   1200000
#define VAD_SILENCE_FRAMES   30
#define VAD_IGNORE_FRAMES    15
#define MAX_STREAM_FRAMES    500

#define T1_WAKENET_WAKEWORD   "wn9_hiesp"

#include "esp_now_protocol.h"

#define T1_CAPABILITIES  ( \
    (HAS_RELAY   ? CAP_RELAY   : 0) | \
    (HAS_PZEM    ? CAP_PZEM    : 0) | \
    (HAS_MIC     ? CAP_MIC     : 0) | \
    (HAS_WAKENET ? CAP_WAKENET : 0)   \
)

#endif
