/**
 * @file voice_capture.h
 * @brief Voice Capture, WakeNet ("Hi ESP") & VAD Streaming Engine for ActionBox
 *
 * Architecture:
 * - INMP441 I2S MEMS Microphone (16kHz / 16-bit Mono)
 * - Bandpass Filter (180Hz HPF + 3400Hz LPF) & DC Offset Removal
 * - WakeNet Wake Word detection ("Hi ESP") & Real-time Energy VAD
 * - Automatic speech onset detection & 1.5s silence end detection
 * - ESP-NOW Audio Chunk Streaming (240 bytes / 120 samples per packet to SubBox)
 * - Visual Feedback via LED2 (GPIO 47): ON during speech listening/streaming, OFF when idle
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize I2S microphone, audio DSP filters, WakeNet/VAD, and spawn capture task
 * @return ESP_OK on success
 */
esp_err_t voice_capture_init(void);

/**
 * @brief Check if audio streaming session is actively in progress
 * @return true if currently streaming voice to SubBox
 */
bool voice_capture_is_streaming(void);

/**
 * @brief Manually or programmatically start a voice streaming session
 * @param trigger_source 0 = WakeNet "Hi ESP", 1 = VAD Energy onset, 2 = Button/Manual
 */
void voice_capture_start_streaming(uint8_t trigger_source);

/**
 * @brief Stop active voice streaming session, send AUDIO_END, and turn off LED2
 */
void voice_capture_stop_streaming(void);

/**
 * @brief Set VAD sensitivity threshold
 * @param energy_threshold Mean square energy threshold (default ~2,500,000)
 */
void voice_capture_set_vad_threshold(int64_t energy_threshold);

/**
 * @brief Retrieve current audio diagnostic metrics
 * @param out_rms Pointer to float receiving latest RMS level
 * @param out_is_speech Pointer to bool receiving VAD speech state
 */
void voice_capture_get_diagnostics(float *out_rms, bool *out_is_speech);

#ifdef __cplusplus
}
#endif
