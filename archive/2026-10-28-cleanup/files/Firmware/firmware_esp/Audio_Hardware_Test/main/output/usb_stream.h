#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "../app_config.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t usb_stream_init(void);

esp_err_t usb_stream_send_start(uint32_t sample_rate, uint16_t channels, uint16_t bits_per_sample);

esp_err_t usb_stream_send_frame(const int16_t *pcm_mono, int num_samples, bool is_speech, bool button_down);

esp_err_t usb_stream_send_end(uint32_t total_samples);

esp_err_t usb_stream_send_wav_header(uint32_t num_samples);

char usb_stream_poll_cmd(void);

bool usb_stream_is_connected(void);

#ifdef __cplusplus
}
#endif
