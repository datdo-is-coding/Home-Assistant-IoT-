#pragma once

#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BOARD_PIN_LED_SYSTEM            GPIO_NUM_48
#define BOARD_PIN_LED_AI_ACTIVE         GPIO_NUM_47
#define BOARD_LED_ACTIVE_LEVEL          1

#define BOARD_PIN_BUTTON_CONFIG         GPIO_NUM_1
#define BOARD_PIN_BUTTON_MUTE           GPIO_NUM_3
#define BOARD_BUTTON_ACTIVE_LEVEL       0

#define BOARD_PIN_RELAY_CH1             GPIO_NUM_4
#define BOARD_PIN_RELAY_CH2             GPIO_NUM_5
#define BOARD_RELAY_ACTIVE_LEVEL        1

#define BOARD_PIN_SPEAKER_SD            GPIO_NUM_2
#define BOARD_PIN_SPEAKER_BCLK          GPIO_NUM_17
#define BOARD_PIN_SPEAKER_LRC           GPIO_NUM_18
#define BOARD_PIN_SPEAKER_DOUT          GPIO_NUM_21

#define BOARD_PIN_DEBUG_TX              GPIO_NUM_43
#define BOARD_PIN_DEBUG_RX              GPIO_NUM_44

#ifdef __cplusplus
}
#endif
