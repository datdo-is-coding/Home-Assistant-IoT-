/**
 * @file actionbox_protocol.h
 * @brief Idempotent JSON Command & Telemetry Protocol Definition for ActionBox <-> SubBox
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "app_config.h"
#include "relay_driver.h"
#include "current_sensor.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    CMD_TYPE_UNKNOWN     = 0,
    CMD_TYPE_TURN_ON     = 1,
    CMD_TYPE_TURN_OFF    = 2,
    CMD_TYPE_TOGGLE      = 3,
    CMD_TYPE_GET_STATE   = 4,
    CMD_TYPE_GET_CURRENT = 5,
    CMD_TYPE_GET_POWER   = 6,
    CMD_TYPE_CLEAR_FAULT = 7,
    CMD_TYPE_PING        = 8,
    CMD_TYPE_SET_CONFIG  = 9
} ActionBoxCommandType;

typedef struct {
    uint32_t             version;
    char                 node_id[APP_MAX_NODE_ID_LEN];
    uint32_t             request_id;
    uint32_t             session_id;
    ActionBoxCommandType cmd;
    uint8_t              channel;        /**< 1 or 2 (or 0 for all/node-level) */
    uint32_t             timestamp;
    uint32_t             settle_ms;
    /* Optional parameter payload for SET_CONFIG */
    char                 new_node_id[APP_MAX_NODE_ID_LEN];
    char                 new_room_id[APP_MAX_ROOM_ID_LEN];
    uint32_t             max_current_ma;
} ActionBoxCommand;

typedef struct {
    uint32_t   version;
    char       node_id[APP_MAX_NODE_ID_LEN];
    uint32_t   request_id;
    uint32_t   session_id;
    bool       success;
    char       status[8];            /**< "OK" or "ERROR" */
    uint8_t    channel;
    char       state[16];             /**< "ON", "OFF", "FAULT", or "PONG" */
    char       error_msg[48];
    uint32_t   current_ma;
    uint32_t   voltage_v;
    int32_t    power_w;
    uint32_t   uptime_s;
} ActionBoxResponse;

/**
 * @brief Initialize protocol idempotency cache
 */
void protocol_init(void);
const char* protocol_get_hardware_uid(void);
esp_err_t protocol_serialize_load_report(const ActionBoxResponse *ack, uint32_t command_ms, const CurrentMeasurement *sample, char *out_json, size_t max_len);

/**
 * @brief Parse incoming JSON string from SubBox into ActionBoxCommand
 * @param json_str Null-terminated JSON string
 * @param out_cmd Destination struct pointer
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on schema/version mismatch
 */
esp_err_t protocol_parse_command(const char *json_str, ActionBoxCommand *out_cmd);

/**
 * @brief Check if request ID was already processed recently (idempotency check)
 * @param request_id Request ID to check
 * @param out_cached_json Pointer to buffer for cached response if found
 * @param max_len Maximum length of cached buffer
 * @return true if duplicate request was found, false if this is a fresh request
 */
bool protocol_is_duplicate_request(uint32_t request_id, uint32_t session_id, char *out_cached_json, size_t max_len);

/**
 * @brief Format ActionBoxResponse into JSON string and cache for idempotency
 * @param resp Pointer to response struct
 * @param out_json Destination buffer
 * @param max_len Size of destination buffer
 * @return ESP_OK on success
 */
esp_err_t protocol_serialize_response(const ActionBoxResponse *resp, char *out_json, size_t max_len);

/**
 * @brief Format periodic telemetry / heartbeat packet into JSON string
 * @param out_json Destination buffer
 * @param max_len Size of buffer
 * @return ESP_OK on success
 */
esp_err_t protocol_serialize_telemetry(char *out_json, size_t max_len);

/**
 * @brief Format urgent overcurrent/fault notification packet into JSON string
 * @param channel Channel ID (1 or 2)
 * @param fault_type Fault code
 * @param current_ma Trip current reading
 * @param out_json Destination buffer
 * @param max_len Size of buffer
 * @return ESP_OK on success
 */
esp_err_t protocol_serialize_fault_alert(uint8_t channel, RelayFault fault_type, uint32_t current_ma, char *out_json, size_t max_len);

/* ========================================================================= */
/*                   BINARY AUDIO STREAMING PACKET DEFINITIONS               */
/* ========================================================================= */

#define MSG_TYPE_AUDIO_START             0x20
#define MSG_TYPE_AUDIO_CHUNK             0x21
#define MSG_TYPE_AUDIO_END               0x22

#define CODEC_RAW_PCM                    0x00
#define CODEC_IMA_ADPCM                  0x01

#define ESPNOW_AUDIO_MAX_PCM_BYTES       240  /* 120 samples x 2 bytes @ 16kHz = 7.5ms */

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_START = 0x20 */
    uint8_t  seq;                /* Sequence 0 */
    uint16_t sample_rate;        /* 16000 */
    uint8_t  bits_per_sample;    /* 16 */
    uint8_t  channels;           /* 1 (mono) */
    uint8_t  wake_word_index;    /* 0 = "Hi ESP", 1 = VAD energy onset */
    uint8_t  codec;              /* CODEC_RAW_PCM */
    uint32_t timestamp_ms;
} ActionBoxAudioStartPacket;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_CHUNK = 0x21 */
    uint8_t  seq;                /* Sequence number (wrapping 0-255) */
    uint16_t pcm_len;            /* <= 240 bytes */
    uint8_t  pcm_data[ESPNOW_AUDIO_MAX_PCM_BYTES];
} ActionBoxAudioChunkPacket;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;           /* MSG_TYPE_AUDIO_END = 0x22 */
    uint8_t  seq;
    uint16_t total_chunks;
    uint32_t total_pcm_bytes;
} ActionBoxAudioEndPacket;

#ifdef __cplusplus
}
#endif
