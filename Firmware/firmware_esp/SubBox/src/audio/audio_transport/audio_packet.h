/**
 * @file audio_packet.h
 * @brief Network Audio Packet Definitions for ActionBox <-> SubBox Transmission
 */

#pragma once

#include <stdint.h>
#include <stddef.h>
#include "config/subbox_config.h"

#ifdef __cplusplus
extern "C" {
#endif

#define AUDIO_PROTOCOL_VERSION          1

typedef enum {
    AUDIO_CODEC_RAW_PCM                 = 0x00,  /**< 16-bit Signed Little-Endian PCM */
    AUDIO_CODEC_OPUS                    = 0x01,  /**< Compressed Opus audio */
    AUDIO_CODEC_ADPCM                   = 0x02   /**< IMA-ADPCM */
} AudioCodecType;

typedef enum {
    AUDIO_MSG_TYPE_STREAM_START         = 0x20,  /**< WakeNet / Speech onset trigger */
    AUDIO_MSG_TYPE_STREAM_CHUNK         = 0x21,  /**< Active audio payload chunk */
    AUDIO_MSG_TYPE_STREAM_END           = 0x22,  /**< VAD silence / max duration end */
    AUDIO_MSG_TYPE_DOWNLINK_TTS         = 0x23   /**< SubBox -> ActionBox TTS / Chime audio */
} AudioMsgType;

#pragma pack(push, 1)

/**
 * @brief Universal Audio Packet Header & Payload
 */
typedef struct {
    uint8_t  version;                            /**< Protocol version (AUDIO_PROTOCOL_VERSION) */
    uint8_t  msg_type;                           /**< AudioMsgType */
    char     source_node_id[32];                 /**< Originating ActionBox ID (e.g. "AB_BEDROOM_01") */
    uint16_t sequence_num;                       /**< Monotonic sequence number for loss detection */
    uint32_t timestamp_ms;                       /**< Millisecond timestamp */
    uint8_t  codec;                              /**< AudioCodecType */
    uint16_t sample_rate;                        /**< Sample rate in Hz (e.g. 16000) */
    uint8_t  channels;                           /**< Channel count (1 = Mono) */
    uint16_t payload_len;                        /**< Actual audio bytes in payload */
    uint8_t  payload[SUBBOX_AUDIO_MAX_PACKET_PAYLOAD]; /**< Raw audio sample data */
} AudioPacket;

#pragma pack(pop)

#ifdef __cplusplus
}
#endif
