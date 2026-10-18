#pragma once

#include <stdint.h>
#include <stddef.h>
#include "config/subbox_config.h"

#ifdef __cplusplus
extern "C" {
#endif

#define AUDIO_PROTOCOL_VERSION          1

typedef enum {
    AUDIO_CODEC_RAW_PCM                 = 0x00,
    AUDIO_CODEC_OPUS                    = 0x01,
    AUDIO_CODEC_ADPCM                   = 0x02
} AudioCodecType;

typedef enum {
    AUDIO_MSG_TYPE_STREAM_START         = 0x20,
    AUDIO_MSG_TYPE_STREAM_CHUNK         = 0x21,
    AUDIO_MSG_TYPE_STREAM_END           = 0x22,
    AUDIO_MSG_TYPE_DOWNLINK_TTS         = 0x23
} AudioMsgType;

#define MSG_TYPE_KEYWORD_EVENT 0x25

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  keyword_id;
    uint8_t  confidence_pct;
    uint32_t session_id;
    uint32_t rel_time_ms;
} ActionBoxKeywordEventPacket;

#pragma pack(push, 1)

typedef struct {
    uint8_t  version;
    uint8_t  msg_type;
    char     source_node_id[32];
    uint16_t sequence_num;
    uint32_t timestamp_ms;
    uint8_t  codec;
    uint16_t sample_rate;
    uint8_t  channels;
    uint16_t payload_len;
    uint8_t  payload[SUBBOX_AUDIO_MAX_PACKET_PAYLOAD];
} AudioPacket;

#pragma pack(pop)

#ifdef __cplusplus
}
#endif
