#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "driver/gpio.h"
#include "driver/i2s_std.h"

/* ─── Hardware Pin Definitions ───────────────────────────────────────── */
#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    GPIO_NUM_15
#define MIC_I2S_GPIO_WS      GPIO_NUM_16
#define MIC_I2S_GPIO_DIN     GPIO_NUM_8

#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_I2S_GPIO_BCLK    GPIO_NUM_17
#define SPK_I2S_GPIO_WS      GPIO_NUM_18
#define SPK_I2S_GPIO_DOUT    GPIO_NUM_21
#define SPK_SD_GPIO          GPIO_NUM_2     /* MAX98357A Amp Enable (1: Run, 0: Mute) */

#define BUT1_GPIO            GPIO_NUM_1     /* Physical Push Button 1 */
#define BUT2_GPIO            GPIO_NUM_3     /* Physical Push Button 2 */
#define BOOT_GPIO            GPIO_NUM_0     /* On-board BOOT Button */

#define LED1_GPIO            GPIO_NUM_48    /* System Status LED (Green) */
#define LED2_GPIO            GPIO_NUM_47    /* Audio Active LED (Blue) */

/* ─── Audio Signal Configuration ─────────────────────────────────────── */
#define AUDIO_SAMPLE_RATE    16000
#define AUDIO_FRAME_SAMPLES  320            /* 20ms per frame @ 16kHz */
#define MAX_RECORD_SECONDS   6              /* Maximum record duration for dataset collection */
#define MAX_RECORD_SAMPLES   (AUDIO_SAMPLE_RATE * MAX_RECORD_SECONDS) /* 96,000 samples = 192KB */

/* ─── Application States & Trigger Sources ───────────────────────────── */
typedef enum {
    STATE_IDLE = 0,             /* Waiting for button / VAD / USB command */
    STATE_RECORDING,            /* Actively capturing & streaming over USB */
    STATE_FINALIZE,             /* Finalizing recording, sending END packet */
    STATE_PLAYING,              /* Local playback over speaker (optional) */
} app_state_t;

typedef enum {
    TRIGGER_NONE = 0,
    TRIGGER_BUTTON,             /* BUT1 or BOOT button pressed */
    TRIGGER_USB_CMD,            /* USB command ('r'/'R' to record, 's' to stop) */
    TRIGGER_VAD,                /* Voice Activity Detection by energy */
} trigger_source_t;

/* ─── USB Binary Packet Framing Protocol ─────────────────────────────── */
#define USB_PKT_MAGIC_0      0xAA
#define USB_PKT_MAGIC_1      0x55

typedef enum {
    USB_PKT_TYPE_AUDIO  = 0x01,  /* 20ms PCM audio frame (320 samples = 640 bytes) */
    USB_PKT_TYPE_START  = 0x02,  /* Session start notification */
    USB_PKT_TYPE_END    = 0x03,  /* Session end notification with total samples */
    USB_PKT_TYPE_STATUS = 0x04,  /* Status / Ping / Energy level */
} usb_pkt_type_t;

typedef enum {
    USB_FLAG_NONE       = 0x00,
    USB_FLAG_VAD_ACTIVE = 0x01,  /* Voice energy active */
    USB_FLAG_BUTTON_DN  = 0x02,  /* Button is pressed */
} usb_pkt_flag_t;

#pragma pack(push, 1)
typedef struct {
    uint8_t  magic[2];       /* 0xAA, 0x55 */
    uint8_t  type;           /* usb_pkt_type_t */
    uint8_t  flags;          /* usb_pkt_flag_t */
    uint16_t length;         /* Payload byte length (Little-Endian) */
    uint16_t seq;            /* Sequence number (Little-Endian) */
} usb_pkt_header_t;
#pragma pack(pop)
