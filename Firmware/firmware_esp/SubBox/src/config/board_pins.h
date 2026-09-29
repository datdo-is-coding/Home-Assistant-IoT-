/**
 * @file board_pins.h
 * @brief Hardware GPIO Pinout for ESP32-S3 SubBox / SubGateway
 *
 * Source: D:\Downloads\IoT_Board.kicad_sch
 * Architecture: ESP32-S3 / 16MB Flash / 16MB PSRAM
 *
 * NOTE: The SubBox does NOT utilize a local I2S microphone. All voice inputs
 * arrive from ActionBoxes over the network.
 */

#pragma once

#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================= */
/*                           STATUS LED CONFIGURATION                        */
/* ========================================================================= */

#define BOARD_PIN_LED_SYSTEM            GPIO_NUM_48  /**< LED1: System / Network status */
#define BOARD_PIN_LED_AI_ACTIVE         GPIO_NUM_47  /**< LED2: ASR / NLU processing indicator */
#define BOARD_LED_ACTIVE_LEVEL          1

/* ========================================================================= */
/*                         PHYSICAL BUTTON CONFIGURATION                     */
/* ========================================================================= */

#define BOARD_PIN_BUTTON_CONFIG         GPIO_NUM_1   /**< BUT1: Wi-Fi Re-pair / Factory reset */
#define BOARD_PIN_BUTTON_MUTE           GPIO_NUM_3   /**< BUT2: Mute / Room beacon trigger */
#define BOARD_BUTTON_ACTIVE_LEVEL       0            /**< Active LOW (pull-up enabled) */

/* ========================================================================= */
/*                         LOCAL RELAY OUTPUTS (OPTIONAL)                    */
/* ========================================================================= */

#define BOARD_PIN_RELAY_CH1             GPIO_NUM_4
#define BOARD_PIN_RELAY_CH2             GPIO_NUM_5
#define BOARD_RELAY_ACTIVE_LEVEL        1

/* ========================================================================= */
/*                        SPEAKER (FOR LOCAL AUDIO PLAYBACK)                 */
/* ========================================================================= */

#define BOARD_PIN_SPEAKER_SD            GPIO_NUM_2   /**< SP_SD pin -> Shutdown active LOW */
#define BOARD_PIN_SPEAKER_BCLK          GPIO_NUM_17  /**< SP_BCLK */
#define BOARD_PIN_SPEAKER_LRC           GPIO_NUM_18  /**< SP_LRC */
#define BOARD_PIN_SPEAKER_DOUT          GPIO_NUM_21  /**< SP_DOUT */

/* ========================================================================= */
/*                         SYSTEM & DEBUG CONFIGURATION                      */
/* ========================================================================= */

#define BOARD_PIN_DEBUG_TX              GPIO_NUM_43
#define BOARD_PIN_DEBUG_RX              GPIO_NUM_44

#ifdef __cplusplus
}
#endif
