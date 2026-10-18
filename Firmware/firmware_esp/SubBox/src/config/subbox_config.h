#pragma once

#include <stdint.h>
#include <stddef.h>

#define SUBBOX_FW_NAME                  "Aetheria-SubBox-Gateway"
#define SUBBOX_FW_VERSION_MAJOR         1
#define SUBBOX_FW_VERSION_MINOR         0
#define SUBBOX_FW_VERSION_PATCH         0
#define SUBBOX_FW_VERSION_STR           "1.0.0-prod"

#define SUBBOX_DEFAULT_ID               "subbox_bedroom_01"
#define SUBBOX_DEFAULT_ROOM_NAME        "Phòng Ngủ"
#define SUBBOX_DEFAULT_ROOM_CODE        "BEDROOM"

#define SUBBOX_MAX_ACTIONBOXES_PER_ROOM 4
#define SUBBOX_AUDIO_SAMPLE_RATE        16000
#define SUBBOX_AUDIO_BITS_PER_SAMPLE    16
#define SUBBOX_AUDIO_CHANNELS           1

#define SUBBOX_AUDIO_FRAME_MS           10
#define SUBBOX_AUDIO_FRAME_SAMPLES      (SUBBOX_AUDIO_SAMPLE_RATE * SUBBOX_AUDIO_FRAME_MS / 1000)
#define SUBBOX_AUDIO_FRAME_BYTES        (SUBBOX_AUDIO_FRAME_SAMPLES * sizeof(int16_t))

#define SUBBOX_UDP_AUDIO_RX_PORT        5005
#define SUBBOX_UDP_AUDIO_TX_PORT        5006

#define SUBBOX_AUDIO_MAX_PACKET_PAYLOAD 480
#define SUBBOX_PSRAM_RING_BUFFER_BYTES  (256 * 1024)

#define SUBBOX_VAD_INITIAL_ENERGY_THRESH 2500000LL
#define SUBBOX_VAD_SPEECH_ONSET_FRAMES   3
#define SUBBOX_VAD_SILENCE_TIMEOUT_MS    1500
#define SUBBOX_VAD_MAX_SPEECH_DURATION_MS 10000

#define TASK_PRIO_AUDIO_RX              7
#define TASK_PRIO_AUDIO_MANAGER         6
#define TASK_PRIO_VAD                   6
#define TASK_PRIO_ASR                   5
#define TASK_PRIO_NLU                   4
#define TASK_PRIO_COMMAND               4
#define TASK_PRIO_DEVICE_MGR            3
#define TASK_PRIO_AUDIO_TX              6
#define TASK_PRIO_MQTT                  3
#define TASK_PRIO_TELEMETRY             2
#define TASK_PRIO_CONSOLE               2

#define TASK_STACK_AUDIO_RX             (6 * 1024)
#define TASK_STACK_AUDIO_MANAGER        (6 * 1024)
#define TASK_STACK_VAD                  (4 * 1024)
#define TASK_STACK_ASR                  (16 * 1024)
#define TASK_STACK_NLU                  (8 * 1024)
#define TASK_STACK_COMMAND              (4 * 1024)
#define TASK_STACK_DEVICE_MGR           (4 * 1024)
#define TASK_STACK_AUDIO_TX             (6 * 1024)
#define TASK_STACK_MQTT                 (6 * 1024)
#define TASK_STACK_TELEMETRY            (3 * 1024)
#define TASK_STACK_CONSOLE              (4 * 1024)

#define QUEUE_CAP_AUDIO_RAW_PACKETS     32
#define QUEUE_CAP_VAD_FRAMES            32
#define QUEUE_CAP_ASR_REQUESTS          4
#define QUEUE_CAP_NLU_REQUESTS          8
#define QUEUE_CAP_COMMAND_REQUESTS      16
#define QUEUE_CAP_RESPONSE_AUDIO        16
#define QUEUE_CAP_MQTT_EVENTS           16

#define SUBBOX_DEFAULT_WIFI_SSID        "XIAOMI"
#define SUBBOX_DEFAULT_WIFI_PASS        "1234567890"
#define SUBBOX_DEFAULT_MQTT_BROKER_URI  "mqtts://192.168.11.29:8883"
#define SUBBOX_DEFAULT_WS_GATEWAY_URI   "ws://192.168.11.29:8765/ws/audio"
#define SUBBOX_MQTT_RECONNECT_MS        5000
