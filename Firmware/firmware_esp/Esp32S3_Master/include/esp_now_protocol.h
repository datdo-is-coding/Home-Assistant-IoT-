#ifndef ESP_NOW_PROTOCOL_H
#define ESP_NOW_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MSG_TYPE_REQ_POWER_STATUS  = 0x01,
    MSG_TYPE_RESP_POWER_STATUS = 0x02,
    MSG_TYPE_CMD_CONTROL       = 0x03,
} esp_now_msg_type_t;

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

#ifdef __cplusplus
}
#endif

#endif
