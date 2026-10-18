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
    uint8_t              channel;
    uint32_t             timestamp;
    uint32_t             settle_ms;

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
    char       status[8];
    uint8_t    channel;
    char       state[16];
    char       error_msg[48];
    uint32_t   current_ma;
    uint32_t   voltage_v;
    int32_t    power_w;
    uint32_t   uptime_s;
} ActionBoxResponse;

void protocol_init(void);
const char* protocol_get_hardware_uid(void);
esp_err_t protocol_serialize_load_report(const ActionBoxResponse *ack, uint32_t command_ms, const CurrentMeasurement *sample, char *out_json, size_t max_len);

esp_err_t protocol_parse_command(const char *json_str, ActionBoxCommand *out_cmd);

bool protocol_is_duplicate_request(uint32_t request_id, uint32_t session_id, char *out_cached_json, size_t max_len);

esp_err_t protocol_serialize_response(const ActionBoxResponse *resp, char *out_json, size_t max_len);

esp_err_t protocol_serialize_telemetry(char *out_json, size_t max_len);

esp_err_t protocol_serialize_fault_alert(uint8_t channel, RelayFault fault_type, uint32_t current_ma, char *out_json, size_t max_len);

#define MSG_TYPE_AUDIO_START             0x20
#define MSG_TYPE_AUDIO_CHUNK             0x21
#define MSG_TYPE_AUDIO_END               0x22
#define MSG_TYPE_KEYWORD_EVENT           0x25

#define CODEC_RAW_PCM                    0x00
#define CODEC_IMA_ADPCM                  0x01

#define ESPNOW_AUDIO_MAX_PCM_BYTES       240

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t sample_rate;
    uint8_t  bits_per_sample;
    uint8_t  channels;
    uint8_t  wake_word_index;
    uint8_t  codec;
    uint32_t timestamp_ms;
} ActionBoxAudioStartPacket;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t pcm_len;
    uint8_t  pcm_data[ESPNOW_AUDIO_MAX_PCM_BYTES];
} ActionBoxAudioChunkPacket;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint16_t total_chunks;
    uint32_t total_pcm_bytes;
} ActionBoxAudioEndPacket;

typedef struct __attribute__((packed)) {
    uint8_t  msg_type;
    uint8_t  seq;
    uint8_t  keyword_id;
    uint8_t  confidence_pct;
    uint32_t session_id;
    uint32_t rel_time_ms;
} ActionBoxKeywordEventPacket;

#ifdef __cplusplus
}
#endif
