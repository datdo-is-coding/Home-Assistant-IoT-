#ifndef ESP_NOW_PROTOCOL_H
#define ESP_NOW_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ESP-NOW Message Types
typedef enum {
    MSG_TYPE_REQ_POWER_STATUS  = 0x01,  // Request live power metrics from WROOM Slave
    MSG_TYPE_RESP_POWER_STATUS = 0x02,  // Response containing PZEM-004T metrics
    MSG_TYPE_CMD_CONTROL       = 0x03,  // Command to control devices (e.g. Relay ON/OFF)
} esp_now_msg_type_t;

// ESP-NOW Packet Data Payload
typedef struct __attribute__((packed)) {
    uint8_t  msg_type;       // Message Type (esp_now_msg_type_t)
    uint8_t  device_id;      // Sender Device ID
    float    voltage;        // AC Voltage (Volts)
    float    current;        // AC Current (Amperes)
    float    power;          // Active Power (Watts)
    float    energy;         // Accumulated Energy (kWh)
    float    frequency;      // AC Frequency (Hz)
    float    pf;             // Power Factor (0.00 ~ 1.00)
    uint32_t timestamp_ms;   // Packet timestamp
    uint8_t  relay_state;    // Device Relay Status (0=OFF, 1=ON)
} esp_now_packet_t;

#ifdef __cplusplus
}
#endif

#endif // ESP_NOW_PROTOCOL_H
