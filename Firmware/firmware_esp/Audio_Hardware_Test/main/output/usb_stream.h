#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize USB Serial stream driver.
 */
esp_err_t usb_stream_init(void);

/**
 * @brief Send session start packet over USB.
 *
 * @param sample_rate Audio sample rate (e.g. 16000)
 * @param channels Number of channels (1 = mono)
 * @param bits_per_sample (16)
 */
esp_err_t usb_stream_send_start(uint32_t sample_rate, uint16_t channels, uint16_t bits_per_sample);

/**
 * @brief Send a framed audio chunk (e.g. 20ms = 320 samples = 640 bytes).
 *
 * @param pcm_mono Array of int16_t samples
 * @param num_samples Number of samples
 * @param is_speech true if voice detected
 * @param button_down true if button currently held
 */
esp_err_t usb_stream_send_frame(const int16_t *pcm_mono, int num_samples, bool is_speech, bool button_down);

/**
 * @brief Send session end packet with total samples and duration.
 *
 * @param total_samples Total recorded samples in session
 */
esp_err_t usb_stream_send_end(uint32_t total_samples);

/**
 * @brief Send complete WAV header for a given number of audio samples.
 */
esp_err_t usb_stream_send_wav_header(uint32_t num_samples);

/**
 * @brief Poll for incoming commands from USB ('r', 's', 'c', etc.)
 *
 * @return char Command character or '\0' if none.
 */
char usb_stream_poll_cmd(void);

/**
 * @brief Check if USB host is currently connected.
 */
bool usb_stream_is_connected(void);

#ifdef __cplusplus
}
#endif
