/**
 * @file board_pins.h
 * @brief Hardware GPIO Pinout & Electrical Configuration for ESP32-S3 ActionBox
 * 
 * Sourced directly from schematic: D:\Downloads\IoT_Board.kicad_sch
 * Architecture: ESP32-S3-WROOM-1 / 16MB Flash
 */

#pragma once

#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================= */
/*                          RELAY OUTPUT CONFIGURATION                       */
/* ========================================================================= */

/**
 * @brief Relay Channel Count
 */
#define BOARD_RELAY_CHANNEL_COUNT        2

/**
 * @brief Relay GPIO mapping from IoT_Board.kicad_sch
 * RL1 -> PC817 (U5) -> Relay 1 (K1) -> Connected to ESP32-S3 IO4
 * RL2 -> PC817 (U6) -> Relay 2 (K2) -> Connected to ESP32-S3 IO5
 */
#define BOARD_PIN_RELAY_CH1              GPIO_NUM_4
#define BOARD_PIN_RELAY_CH2              GPIO_NUM_5

/**
 * @brief Relay Driving Technology
 * 0: Monostable standard relay (Continuous HIGH = Closed/ON, LOW = Open/OFF)
 * 1: Magnetic Latching single-coil (H-Bridge or reverse polarity pulse)
 * 2: Magnetic Latching dual-coil (SET pulse pin and RESET pulse pin)
 */
#define BOARD_RELAY_TYPE_MONOSTABLE      0
#define BOARD_RELAY_TYPE_LATCHING_DUAL   1

#define BOARD_RELAY_DRIVE_TYPE           BOARD_RELAY_TYPE_MONOSTABLE

/**
 * @brief Monostable relay logic level (via PC817 optocoupler)
 * 1 = Output HIGH energizes optocoupler LED, switching relay ON
 * 0 = Output LOW de-energizes optocoupler, switching relay OFF
 */
#define BOARD_RELAY_ACTIVE_LEVEL         1

/**
 * @brief Magnetic Latching Pulse Duration in Milliseconds
 * Used when BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL
 */
#define BOARD_RELAY_LATCH_PULSE_MS       50

/**
 * @brief Placeholders for optional Dual-Coil Latching SET / RESET pins
 * If a latching hardware daughterboard is fitted, define dedicated pins here.
 */
#define BOARD_PIN_RELAY_CH1_SET          GPIO_NUM_4
#define BOARD_PIN_RELAY_CH1_RESET        GPIO_NUM_6   /* Placeholder for Ch1 Reset if dual-coil */
#define BOARD_PIN_RELAY_CH2_SET          GPIO_NUM_5
#define BOARD_PIN_RELAY_CH2_RESET        GPIO_NUM_7   /* Placeholder for Ch2 Reset if dual-coil */


/* ========================================================================= */
/*                         PHYSICAL BUTTON CONFIGURATION                     */
/* ========================================================================= */

/**
 * @brief Button Channel Count
 */
#define BOARD_BUTTON_COUNT               2

/**
 * @brief Physical Push Button GPIOs from schematic
 * BUT1 -> SW_Push -> Connected to ESP32-S3 IO1
 * BUT2 -> SW_Push -> Connected to ESP32-S3 IO3
 */
#define BOARD_PIN_BUTTON_CH1             GPIO_NUM_1
#define BOARD_PIN_BUTTON_CH2             GPIO_NUM_3

/**
 * @brief Button Electrical Level
 * Buttons pull down to GND on press; internal pull-up is enabled in software.
 * 0 = Active LOW (Pressed = 0, Released = 1)
 */
#define BOARD_BUTTON_ACTIVE_LEVEL        0


/* ========================================================================= */
/*                           STATUS LED CONFIGURATION                        */
/* ========================================================================= */

/**
 * @brief Status Indicator LEDs from schematic
 * LED1 -> Resistor -> Connected to ESP32-S3 IO48
 * LED2 -> Resistor -> Connected to ESP32-S3 IO47
 */
#define BOARD_PIN_LED_CH1                GPIO_NUM_48
#define BOARD_PIN_LED_CH2                GPIO_NUM_47

/**
 * @brief LED Active Level
 * 1 = HIGH illuminates LED
 * 0 = LOW illuminates LED
 */
#define BOARD_LED_ACTIVE_LEVEL           1


/* ========================================================================= */
/*                 BL0942 ENERGY MEASUREMENT UART CONFIGURATION              */
/* ========================================================================= */

/**
 * @brief BL0942 Energy Metering IC UART Connections from schematic
 * BL_TX  -> Common TX to BL0942 ICs -> ESP32-S3 IO9
 * BL_RX1 -> Channel 1 BL0942 TX      -> ESP32-S3 IO10
 * BL_RX2 -> Channel 2 BL0942 TX      -> ESP32-S3 IO11
 */
#define BOARD_PIN_BL0942_TX              GPIO_NUM_9
#define BOARD_PIN_BL0942_RX_CH1          GPIO_NUM_10
#define BOARD_PIN_BL0942_RX_CH2          GPIO_NUM_11

/**
 * @brief Hardware UART Peripherals used for BL0942
 * ESP32-S3 UART1 handles Channel 1 (TX=IO9, RX=IO10)
 * ESP32-S3 UART2 handles Channel 2 (TX=IO9 shared / -1, RX=IO11)
 */
#define BOARD_BL0942_UART_NUM_CH1        UART_NUM_1
#define BOARD_BL0942_UART_NUM_CH2        UART_NUM_2
#define BOARD_BL0942_UART_BAUDRATE       4800   /* Default BL0942 UART Baudrate */


/* ========================================================================= */
/*                         SPEAKER HARDWARE SHUTDOWN                         */
/* ========================================================================= */

/**
 * @brief ActionBox Speaker Policy
 * ActionBox does NOT use a speaker. The MAX98357 audio amplifier must be
 * held permanently in hardware SHUTDOWN (SD_MODE = 0) to eliminate quiescent
 * current draw, pop noise, and speaker coil heating.
 */
#define BOARD_FEATURE_SPEAKER_ENABLED    0

#define BOARD_PIN_SPEAKER_SD             GPIO_NUM_2   /* SP_SD pin -> Shutdown active LOW */
#define BOARD_PIN_SPEAKER_BCLK           GPIO_NUM_17  /* SP_BCLK */
#define BOARD_PIN_SPEAKER_LRC            GPIO_NUM_18  /* SP_LRC */
#define BOARD_PIN_SPEAKER_DOUT           GPIO_NUM_21  /* SP_DOUT */


/* ========================================================================= */
/*                   I2S MICROPHONE CONFIGURATION (INMP441)                  */
/* ========================================================================= */

/**
 * @brief INMP441 MEMS Microphone I2S Connections from schematic
 * MIC_BCLK -> ESP32-S3 IO15
 * MIC_WS   -> ESP32-S3 IO16 (LRCLK / Word Select)
 * MIC_DIN  -> ESP32-S3 IO8  (Serial Data Input)
 */
#define BOARD_FEATURE_MIC_ENABLED        1

#define BOARD_PIN_MIC_BCLK               GPIO_NUM_15
#define BOARD_PIN_MIC_WS                 GPIO_NUM_16
#define BOARD_PIN_MIC_DIN                GPIO_NUM_8
#define BOARD_MIC_I2S_PORT               I2S_NUM_0

/**
 * @brief Voice Activity & Listening Status Indicator
 * Maps to LED2 (GPIO 47) as defined in system architecture
 */
#define BOARD_PIN_LED_VOICE              BOARD_PIN_LED_CH2



/* ========================================================================= */
/*                         SYSTEM & DEBUG CONFIGURATION                      */
/* ========================================================================= */

/**
 * @brief Debug UART0 from schematic
 * TX0 -> ESP32-S3 IO43 (TXD0)
 * RX0 -> ESP32-S3 IO44 (RXD0)
 */
#define BOARD_PIN_DEBUG_TX               GPIO_NUM_43
#define BOARD_PIN_DEBUG_RX               GPIO_NUM_44

#ifdef __cplusplus
}
#endif
