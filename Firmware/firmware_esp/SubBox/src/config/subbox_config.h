/**
 * @file subbox_config.h
 * @brief Global Configuration Constants for SubBox / SubGateway
 *
 * Target: ESP32-S3 with 16MB Flash, 8MB Octal PSRAM, ESP-IDF 6.0.2, FreeRTOS
 */

#pragma once

#include <stdint.h>
#include <stddef.h>

/* ========================================================================= */
/*                         FIRMWARE IDENTIFICATION                          */
/* ========================================================================= */

#define SUBBOX_FW_NAME                  "Aetheria-SubBox-Gateway"
#define SUBBOX_FW_VERSION_MAJOR         1
#define SUBBOX_FW_VERSION_MINOR         0
#define SUBBOX_FW_VERSION_PATCH         0
#define SUBBOX_FW_VERSION_STR           "1.0.0-prod"

#define SUBBOX_DEFAULT_ID               "subbox_bedroom_01"
#define SUBBOX_DEFAULT_ROOM_NAME        "Phòng Ngủ"
#define SUBBOX_DEFAULT_ROOM_CODE        "BEDROOM"

/* ========================================================================= */
/*                         AUDIO ARCHITECTURE LIMITS                         */
/* ========================================================================= */

#define SUBBOX_MAX_ACTIONBOXES_PER_ROOM 4       /**< Maximum ActionBoxes managed per room */
#define SUBBOX_AUDIO_SAMPLE_RATE        16000   /**< 16 kHz standard audio */
#define SUBBOX_AUDIO_BITS_PER_SAMPLE    16      /**< 16-bit PCM */
#define SUBBOX_AUDIO_CHANNELS           1       /**< Mono */

#define SUBBOX_AUDIO_FRAME_MS           10      /**< 10ms frame size */
#define SUBBOX_AUDIO_FRAME_SAMPLES      (SUBBOX_AUDIO_SAMPLE_RATE * SUBBOX_AUDIO_FRAME_MS / 1000) /* 160 samples */
#define SUBBOX_AUDIO_FRAME_BYTES        (SUBBOX_AUDIO_FRAME_SAMPLES * sizeof(int16_t))             /* 320 bytes */

#define SUBBOX_UDP_AUDIO_RX_PORT        5005    /**< UDP port for ActionBox uplink audio */
#define SUBBOX_UDP_AUDIO_TX_PORT        5006    /**< UDP port for ActionBox downlink audio */

#define SUBBOX_AUDIO_MAX_PACKET_PAYLOAD 480     /**< Max PCM payload per transport packet */
#define SUBBOX_PSRAM_RING_BUFFER_BYTES  (256 * 1024) /**< 256 KB PSRAM buffer for audio streams */

/* ========================================================================= */
/*                          VAD ENGINE THRESHOLDS                            */
/* ========================================================================= */

#define SUBBOX_VAD_INITIAL_ENERGY_THRESH 2500000LL  /**< Initial RMS energy threshold for speech */
#define SUBBOX_VAD_SPEECH_ONSET_FRAMES   3          /**< Consecutive frames to trigger onset (~30ms) */
#define SUBBOX_VAD_SILENCE_TIMEOUT_MS    1500       /**< 1.5s silence triggers end-of-speech */
#define SUBBOX_VAD_MAX_SPEECH_DURATION_MS 10000     /**< 10s maximum recording window */

/* ========================================================================= */
/*                         FREERTOS TASK PRIORITIES                          */
/* ========================================================================= */

#define TASK_PRIO_AUDIO_RX              7       /**< High priority: Network packet ingress */
#define TASK_PRIO_AUDIO_MANAGER         6       /**< High priority: Multi-source selection & VAD */
#define TASK_PRIO_VAD                   6       /**< High priority: Frame level energy */
#define TASK_PRIO_ASR                   5       /**< Intensive: Speech recognition engine */
#define TASK_PRIO_NLU                   4       /**< Medium: Text normalization & intent extraction */
#define TASK_PRIO_COMMAND               4       /**< Medium: Command execution & routing */
#define TASK_PRIO_DEVICE_MGR            3       /**< Device registry management */
#define TASK_PRIO_AUDIO_TX              6       /**< High priority: Streaming audio to ActionBox */
#define TASK_PRIO_MQTT                  3       /**< Network: Pi4 communication */
#define TASK_PRIO_TELEMETRY             2       /**< Low: Periodic status logging */
#define TASK_PRIO_CONSOLE               2       /**< Interactive CLI */

/* Task Stack Sizes (Allocated in Internal SRAM or PSRAM) */
#define TASK_STACK_AUDIO_RX             (6 * 1024)
#define TASK_STACK_AUDIO_MANAGER        (6 * 1024)
#define TASK_STACK_VAD                  (4 * 1024)
#define TASK_STACK_ASR                  (16 * 1024) /**< Larger stack for ASR model inference */
#define TASK_STACK_NLU                  (8 * 1024)
#define TASK_STACK_COMMAND              (4 * 1024)
#define TASK_STACK_DEVICE_MGR           (4 * 1024)
#define TASK_STACK_AUDIO_TX             (6 * 1024)
#define TASK_STACK_MQTT                 (6 * 1024)
#define TASK_STACK_TELEMETRY            (3 * 1024)
#define TASK_STACK_CONSOLE              (4 * 1024)

/* ========================================================================= */
/*                          QUEUE BUFFER CAPACITIES                          */
/* ========================================================================= */

#define QUEUE_CAP_AUDIO_RAW_PACKETS     32
#define QUEUE_CAP_VAD_FRAMES            32
#define QUEUE_CAP_ASR_REQUESTS          4
#define QUEUE_CAP_NLU_REQUESTS          8
#define QUEUE_CAP_COMMAND_REQUESTS      16
#define QUEUE_CAP_RESPONSE_AUDIO        16
#define QUEUE_CAP_MQTT_EVENTS           16

/* ========================================================================= */
/*                            NETWORK DEFAULTS                               */
/* ========================================================================= */

#define SUBBOX_DEFAULT_WIFI_SSID        ""
#define SUBBOX_DEFAULT_WIFI_PASS        ""
#define SUBBOX_DEFAULT_MQTT_BROKER_URI  ""
#define SUBBOX_DEFAULT_WS_GATEWAY_URI   ""
#define SUBBOX_MQTT_RECONNECT_MS        5000
