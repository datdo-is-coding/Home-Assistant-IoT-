#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "driver/gpio.h"
#include "driver/i2s_std.h"

#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    GPIO_NUM_15
#define MIC_I2S_GPIO_WS      GPIO_NUM_16
#define MIC_I2S_GPIO_DIN     GPIO_NUM_8

#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_I2S_GPIO_BCLK    GPIO_NUM_17
#define SPK_I2S_GPIO_WS      GPIO_NUM_18
#define SPK_I2S_GPIO_DOUT    GPIO_NUM_21
#define SPK_SD_GPIO          GPIO_NUM_2

#define BUT1_GPIO            GPIO_NUM_1
#define BUT2_GPIO            GPIO_NUM_3
#define BOOT_GPIO            GPIO_NUM_0

#define LED1_GPIO            GPIO_NUM_48
#define LED2_GPIO            GPIO_NUM_47

#define AUDIO_SAMPLE_RATE    16000
#define AUDIO_FRAME_SAMPLES  320
#define MAX_RECORD_SECONDS   6
#define MAX_RECORD_SAMPLES   (AUDIO_SAMPLE_RATE * MAX_RECORD_SECONDS)

typedef enum {
    STATE_IDLE = 0,
    STATE_RECORDING,
    STATE_FINALIZE,
    STATE_PLAYING,
} app_state_t;

typedef enum {
    TRIGGER_NONE = 0,
    TRIGGER_BUTTON,
    TRIGGER_USB_CMD,
    TRIGGER_VAD,
} trigger_source_t;

#define USB_PKT_MAGIC_0      0xAA
#define USB_PKT_MAGIC_1      0x55

typedef enum {
    USB_PKT_TYPE_AUDIO  = 0x01,
    USB_PKT_TYPE_START  = 0x02,
    USB_PKT_TYPE_END    = 0x03,
    USB_PKT_TYPE_STATUS = 0x04,
} usb_pkt_type_t;

typedef enum {
    USB_FLAG_NONE       = 0x00,
    USB_FLAG_VAD_ACTIVE = 0x01,
    USB_FLAG_BUTTON_DN  = 0x02,
} usb_pkt_flag_t;

#pragma pack(push, 1)
typedef struct {
    uint8_t  magic[2];
    uint8_t  type;
    uint8_t  flags;
    uint16_t length;
    uint16_t seq;
} usb_pkt_header_t;
#pragma pack(pop)
