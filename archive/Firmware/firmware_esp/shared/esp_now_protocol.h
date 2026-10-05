/*
 * ESP-NOW Protocol — 3-Tier IoT Architecture
 * DTV Smart Home — Shared between T1 Actuator Nodes & T2 Zone Controllers
 *
 * Extension of the original 2-tier protocol to support:
 *   - Audio streaming (T1 → T2 via ESP-NOW)
 *   - Relay commands (T2 → T1 via ESP-NOW)
 *   - Node registration & heartbeat
 *   - Zone management
 *
 * ESP-NOW payload limit: 250 bytes per packet.
 */

#ifndef ESP_NOW_PROTOCOL_H
#define ESP_NOW_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Message Types ──────────────────────────────────────────────────── */

typedef enum {
    /* Legacy (backward compat with ESP32 WROOM energy slave) */
    MSG_TYPE_REQ_POWER_STATUS  = 0x01,  /* T2 → T1: request PZEM telemetry */
    MSG_TYPE_RESP_POWER_STATUS = 0x02,  /* T1 → T2: PZEM telemetry response */
    MSG_TYPE_CMD_CONTROL       = 0x03,  /* Legacy control (deprecated) */

    /* Relay Control (T2 ↔ T1) */
    MSG_TYPE_RELAY_CMD         = 0x10,  /* T2 → T1: set relay channel/state */
    MSG_TYPE_RELAY_ACK         = 0x11,  /* T1 → T2: relay state confirmed */

    /* Audio Streaming (T1 → T2) */
    MSG_TYPE_AUDIO_START       = 0x20,  /* T1 → T2: WakeNet detected, begin stream */
    MSG_TYPE_AUDIO_CHUNK       = 0x21,  /* T1 → T2: PCM audio data chunk */
    MSG_TYPE_AUDIO_END         = 0x22,  /* T1 → T2: silence/VAD end, stop stream */

    /* Node Management (T1 ↔ T2) */
    MSG_TYPE_NODE_HELLO        = 0x30,  /* T1 → T2: boot registration / heartbeat */
    MSG_TYPE_NODE_HELLO_ACK    = 0x31,  /* T2 → T1: hello acknowledged, config sync */
    MSG_TYPE_NODE_CFG          = 0x32,  /* T2 → T1: push provisioning config */
    MSG_TYPE_NODE_CFG_ACK      = 0x33,  /* T1 → T2: config saved confirmation */

    /* OTA (T2 → T1, future) */
    MSG_TYPE_OTA_BEGIN         = 0x40,  /* T2 → T1: OTA update start */
    MSG_TYPE_OTA_CHUNK         = 0x41,  /* T2 → T1: OTA firmware chunk */
    MSG_TYPE_OTA_END           = 0x42,  /* T2 → T1: OTA update complete */
} esp_now_msg_type_t;

/* ─── Common Packet Header (4 bytes, present in every packet) ────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* esp_now_msg_type_t */
    uint8_t  seq;                /* Sequence number (0-255, wrapping) */
    uint16_t reserved;           /* Alignment / future flags */
} espnow_header_t;

/* ─── Legacy Power Telemetry Packet (backward compat) ────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_REQ/RESP_POWER_STATUS */
    uint8_t  device_id;          /* Sender Device ID */
    float    voltage;            /* AC Voltage (Volts) */
    float    current;            /* AC Current (Amperes) */
    float    power;              /* Active Power (Watts) */
    float    energy;             /* Accumulated Energy (kWh) */
    float    frequency;          /* AC Frequency (Hz) */
    float    pf;                 /* Power Factor (0.00 ~ 1.00) */
    uint32_t timestamp_ms;       /* Packet timestamp */
    uint8_t  relay_state;        /* Combined relay bits: bit0=RL1, bit1=RL2 */
} esp_now_packet_t;

/* ─── Relay Command Packet (T2 → T1, 8 bytes) ───────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_RELAY_CMD = 0x10 */
    uint8_t  seq;                /* Sequence # (for dedup on T1) */
    uint8_t  channel;            /* 1 or 2 */
    uint8_t  state;              /* 1=ON, 0=OFF */
    uint32_t timestamp_ms;       /* Command timestamp */
} espnow_relay_cmd_t;            /* Total: 8 bytes */

/* ─── Relay ACK Packet (T1 → T2, 8 bytes) ────────────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_RELAY_ACK = 0x11 */
    uint8_t  seq;                /* Echo of command seq */
    uint8_t  rl1_state;          /* Actual RL1 GPIO state (0/1) */
    uint8_t  rl2_state;          /* Actual RL2 GPIO state (0/1) */
    uint32_t timestamp_ms;       /* ACK timestamp */
} espnow_relay_ack_t;            /* Total: 8 bytes */

/* Audio Codec Types */
#define CODEC_RAW_PCM       0x00  /* Raw 16-bit uncompressed PCM */
#define CODEC_IMA_ADPCM     0x01  /* IMA-ADPCM 4:1 compressed audio */

/* ─── Audio Start Packet (T1 → T2, 12 bytes) ─────────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_START = 0x20 */
    uint8_t  seq;                /* Session start seq (0) */
    uint16_t sample_rate;        /* 16000 Hz */
    uint8_t  bits_per_sample;    /* 16 */
    uint8_t  channels;           /* 1 (mono) */
    uint8_t  wake_word_index;    /* Which wake word triggered (0 = "Hi ESP") */
    uint8_t  codec;              /* CODEC_RAW_PCM or CODEC_IMA_ADPCM */
    uint32_t timestamp_ms;       /* Detection timestamp */
} espnow_audio_start_t;          /* Total: 12 bytes */

/* ─── Audio Chunk Packet (T1 → T2, max 244 bytes) ────────────────────── */

#define ESPNOW_AUDIO_MAX_PCM_BYTES  240  /* 120 samples × 2 bytes (or 480 ADPCM samples) */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_CHUNK = 0x21 */
    uint8_t  seq;                /* Chunk sequence (wrapping 0-255) */
    uint16_t pcm_len;            /* Actual PCM bytes in this chunk (≤ 240) */
    uint8_t  pcm_data[ESPNOW_AUDIO_MAX_PCM_BYTES];
} espnow_audio_chunk_t;          /* Total: 4 + 240 = 244 bytes (< 250 limit) */

/* ─── Audio End Packet (T1 → T2, 8 bytes) ─────────────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_END = 0x22 */
    uint8_t  seq;                /* Final seq number */
    uint16_t total_chunks;       /* Total audio chunks sent in this session */
    uint32_t total_pcm_bytes;    /* Total PCM bytes sent */
} espnow_audio_end_t;            /* Total: 8 bytes */

/* ─── Node Hello Packet (T1 → T2, ~64 bytes) ─────────────────────────── */

#define ESPNOW_DEVICE_ID_LEN  32
#define ESPNOW_ROOM_LEN       24

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_NODE_HELLO = 0x30 */
    uint8_t  seq;
    uint8_t  mac[6];             /* T1 node Wi-Fi MAC */
    char     device_id[ESPNOW_DEVICE_ID_LEN]; /* e.g. "node_7f3a91c2" */
    uint8_t  rl1_state;          /* Current relay 1 state */
    uint8_t  rl2_state;          /* Current relay 2 state */
    uint8_t  capabilities;       /* Bitfield: see CAP_* defines below */
    uint8_t  is_provisioned;     /* 0=factory_new, 1=provisioned */
    uint32_t cfg_version;        /* Config version from NVS */
    uint32_t uptime_s;           /* Seconds since boot */
    int8_t   rssi;               /* Wi-Fi RSSI (or 0 if no Wi-Fi) */
    uint8_t  fw_major;           /* Firmware version major */
    uint8_t  fw_minor;           /* Firmware version minor */
    uint8_t  fw_patch;           /* Firmware version patch */
} espnow_node_hello_t;

/* ─── Node Hello ACK Packet (T2 → T1, ~32 bytes) ─────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_NODE_HELLO_ACK = 0x31 */
    uint8_t  seq;
    uint8_t  channel;            /* Current Wi-Fi channel */
    uint8_t  registered;         /* 1=success */
    uint32_t cfg_version;        /* Current zone config version */
    char     zone_name[ESPNOW_ROOM_LEN]; /* Zone name string */
} espnow_node_hello_ack_t;

/* ─── Capability Bitfield ─────────────────────────────────────────────── */

#define CAP_RELAY       (1 << 0)   /* Has relay outputs */
#define CAP_PZEM        (1 << 1)   /* Has PZEM-004T energy sensor */
#define CAP_MIC         (1 << 2)   /* Has INMP441 microphone */
#define CAP_WAKENET     (1 << 3)   /* Has WakeNet wake-word detection */
#define CAP_SPEAKER     (1 << 4)   /* Has MAX98357A speaker */
#define CAP_IR          (1 << 5)   /* Has IR TX/RX */

/* ─── Node Config Packet (T2 → T1, ~96 bytes) ────────────────────────── */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_NODE_CFG = 0x32 */
    uint8_t  seq;
    char     node_id[ESPNOW_DEVICE_ID_LEN]; /* Assigned node ID */
    char     room[ESPNOW_ROOM_LEN];         /* Assigned room slug */
    char     rl1_name[16];       /* "light", "fan", etc. */
    char     rl2_name[16];       /* "light", "fan", etc. */
    uint32_t cfg_version;        /* Config version */
} espnow_node_cfg_t;

/* ─── Telemetry Packet (T1 → T2, reusing legacy format) ──────────────── */
/* Use esp_now_packet_t above with MSG_TYPE_RESP_POWER_STATUS */

#ifdef __cplusplus
}
#endif

#endif /* ESP_NOW_PROTOCOL_H */
