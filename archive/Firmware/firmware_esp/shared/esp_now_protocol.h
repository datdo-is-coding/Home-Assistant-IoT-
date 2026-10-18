#ifndef ESP_NOW_PROTOCOL_H
#define ESP_NOW_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {

    MSG_TYPE_REQ_POWER_STATUS  = 0x01,
    MSG_TYPE_RESP_POWER_STATUS = 0x02,
    MSG_TYPE_CMD_CONTROL       = 0x03,

    MSG_TYPE_RELAY_CMD         = 0x10,
    MSG_TYPE_RELAY_ACK         = 0x11,

    MSG_TYPE_AUDIO_START       = 0x20,
    MSG_TYPE_AUDIO_CHUNK       = 0x21,
    MSG_TYPE_AUDIO_END         = 0x22,

    MSG_TYPE_NODE_HELLO        = 0x30,
    MSG_TYPE_NODE_HELLO_ACK    = 0x31,
    MSG_TYPE_NODE_CFG          = 0x32,
    MSG_TYPE_NODE_CFG_ACK      = 0x33,

    MSG_TYPE_OTA_BEGIN         = 0x40,
    MSG_TYPE_OTA_CHUNK         = 0x41,
    MSG_TYPE_OTA_END           = 0x42,
} esp_now_msg_type_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t reserved;
} espnow_header_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  device_id;
    float    voltage;
    float    current;
    float    power;
    float    energy;
    float    frequency;
    float    pf;
    uint32_t timestamp_ms;
    uint8_t  relay_state;
} esp_now_packet_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  channel;
    uint8_t  state;
    uint32_t timestamp_ms;
} espnow_relay_cmd_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  rl1_state;
    uint8_t  rl2_state;
    uint32_t timestamp_ms;
} espnow_relay_ack_t;

#define CODEC_RAW_PCM       0x00
#define CODEC_IMA_ADPCM     0x01

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t sample_rate;
    uint8_t  bits_per_sample;
    uint8_t  channels;
    uint8_t  wake_word_index;
    uint8_t  codec;
    uint32_t timestamp_ms;
} espnow_audio_start_t;

#define ESPNOW_AUDIO_MAX_PCM_BYTES  240

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t pcm_len;
    uint8_t  pcm_data[ESPNOW_AUDIO_MAX_PCM_BYTES];
} espnow_audio_chunk_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t total_chunks;
    uint32_t total_pcm_bytes;
} espnow_audio_end_t;

#define ESPNOW_DEVICE_ID_LEN  32
#define ESPNOW_ROOM_LEN       24

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  mac[6];
    char     device_id[ESPNOW_DEVICE_ID_LEN];
    uint8_t  rl1_state;
    uint8_t  rl2_state;
    uint8_t  capabilities;
    uint8_t  is_provisioned;
    uint32_t cfg_version;
    uint32_t uptime_s;
    int8_t   rssi;
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
} espnow_node_hello_t;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  channel;
    uint8_t  registered;
    uint32_t cfg_version;
    char     zone_name[ESPNOW_ROOM_LEN];
} espnow_node_hello_ack_t;

#define CAP_RELAY       (1 << 0)
#define CAP_PZEM        (1 << 1)
#define CAP_MIC         (1 << 2)
#define CAP_WAKENET     (1 << 3)
#define CAP_SPEAKER     (1 << 4)
#define CAP_IR          (1 << 5)

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    char     node_id[ESPNOW_DEVICE_ID_LEN];
    char     room[ESPNOW_ROOM_LEN];
    char     rl1_name[16];
    char     rl2_name[16];
    uint32_t cfg_version;
} espnow_node_cfg_t;

#ifdef __cplusplus
}
#endif

#endif
