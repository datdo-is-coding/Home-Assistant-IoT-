/*
 * T1 Actuator Node — Hardware Configuration
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * GPIO assignments and variant flags for T1 ESP32-S3 nodes.
 * Override defaults here to match your specific PCB wiring.
 */

#ifndef T1_CONFIG_H
#define T1_CONFIG_H

/* ─── Firmware Identity ──────────────────────────────────────────────── */

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

/* ─── Feature Flags (set via platformio.ini build_flags) ─────────────── */

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
#define HAS_ADPCM     1   /* 1 = IMA-ADPCM 4:1 compression over ESP-NOW, 0 = raw PCM */
#endif

#ifndef HAS_PZEM
#define HAS_PZEM      0
#endif

/* ─── Relay GPIOs (Active-LOW, PC817 optocoupler) ────────────────────── */

#define RELAY_CH1_GPIO    4    /* Schematic: IO4 → RL1 (Đèn) */
#define RELAY_CH2_GPIO    5    /* Schematic: IO5 → RL2 (Quạt) */
#define RELAY_ACTIVE_LOW  true

/* ─── Button GPIOs (Internal Pull-Up) ────────────────────────────────── */

#define BUT1_GPIO         1    /* Schematic: IO1 → BUT1 (Toggle RL1 / Factory Reset) */
#define BUT2_GPIO         3    /* Schematic: IO3 → BUT2 (Toggle RL2) */

/* ─── LED GPIOs ──────────────────────────────────────────────────────── */

#define LED1_GPIO         48   /* System status / Power */
#define LED2_GPIO         47   /* Voice / Activity indicator */

/* ─── I2S Microphone (INMP441) ───────────────────────────────────────── */

#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    15   /* Schematic: IO15 → MIC_BCLK */
#define MIC_I2S_GPIO_WS      16   /* Schematic: IO16 → MIC_WS */
#define MIC_I2S_GPIO_DIN     8    /* Schematic: IO8  → MIC_DIN */

/* ─── PZEM-004T UART (only if HAS_PZEM) ─────────────────────────────── */

#if HAS_PZEM
#define PZEM_UART_NUM        UART_NUM_1
#define PZEM_UART_TX_GPIO    43   /* UART1 TX */
#define PZEM_UART_RX_GPIO    44   /* UART1 RX */
#define PZEM_BAUD_RATE       9600
#endif

/* ─── ESP-NOW Configuration ──────────────────────────────────────────── */

#define ESPNOW_WIFI_CHANNEL  11   /* Must match T2 Zone Controller channel */
#define ESPNOW_HEARTBEAT_S   30   /* Heartbeat interval in seconds */
#define ESPNOW_TELE_INTERVAL_MS  2000  /* Telemetry send interval (ms) */

/* ─── Audio Configuration ────────────────────────────────────────────── */

#define AUDIO_SAMPLE_RATE    16000
#define AUDIO_BITS           16
#define AUDIO_CHANNELS       1

/* VAD (Voice Activity Detection) — tuned for low latency */
#define VAD_SILENCE_ENERGY   1200000 /* Mean-square silence threshold (calibrated for 4x gain) */
#define VAD_SILENCE_FRAMES   30      /* 30 × 20ms = 600ms silence to end */
#define VAD_IGNORE_FRAMES    15      /* Ignore first 0.3s for speech onset */
#define MAX_STREAM_FRAMES    500     /* 500 × 20ms = 10 seconds max recording */

/* ─── WakeNet Configuration ──────────────────────────────────────────── */

#define T1_WAKENET_WAKEWORD   "wn9_hiesp"

/* ─── Capability Bitmask (auto-computed) ─────────────────────────────── */

#include "esp_now_protocol.h"

#define T1_CAPABILITIES  ( \
    (HAS_RELAY   ? CAP_RELAY   : 0) | \
    (HAS_PZEM    ? CAP_PZEM    : 0) | \
    (HAS_MIC     ? CAP_MIC     : 0) | \
    (HAS_WAKENET ? CAP_WAKENET : 0)   \
)

#endif /* T1_CONFIG_H */
