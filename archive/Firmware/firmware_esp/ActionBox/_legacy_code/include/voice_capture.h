/*
 * Voice Capture — T1 Actuator Node
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Audio pipeline: INMP441 I2S Mic → ESP-SR AFE → WakeNet → PCM Stream → ESP-NOW
 *
 * This is the core voice input module. It:
 *   1. Initializes I2S for INMP441 microphone
 *   2. Creates ESP-SR Audio Front-End (AFE) pipeline
 *   3. Runs WakeNet wake-word detection continuously ("Hi ESP")
 *   4. When wake word detected → streams raw PCM via ESP-NOW to T2
 *   5. Stops streaming when VAD detects silence or max duration reached
 *
 * Refactored from Esp32S3_Master/main.c — keeps same AFE/WakeNet logic,
 * but streams via ESP-NOW instead of WebSocket.
 */

#ifndef VOICE_CAPTURE_H
#define VOICE_CAPTURE_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize I2S microphone and start WakeNet detection task.
 * This creates the AFE pipeline and starts listening for "Hi ESP".
 * When detected, it automatically streams PCM to T2 via espnow_slave.
 * @return ESP_OK on success
 */
esp_err_t voice_capture_init(void);

/**
 * @brief Check if currently streaming audio to T2.
 * @return true if an active voice session is in progress
 */
bool voice_capture_is_streaming(void);

/**
 * @brief Manually start streaming voice session (e.g. from button event or energy trigger).
 * @param trigger_source  0=Button/Manual, 1=Energy VAD / Wake word
 */
void voice_capture_start_streaming(uint8_t trigger_source);

/**
 * @brief Stop active streaming voice session.
 */
void voice_capture_stop_streaming(void);

#ifdef __cplusplus
}
#endif

#endif /* VOICE_CAPTURE_H */
