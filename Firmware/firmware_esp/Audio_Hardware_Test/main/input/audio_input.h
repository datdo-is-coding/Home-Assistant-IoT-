#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize INMP441 I2S microphone and calibrate DSP filters.
 */
esp_err_t audio_input_init(void);

/**
 * @brief Read and filter an audio frame.
 * Applies:
 *   1. Hardware channel lock (prevents zero-crossing channel swap bugs)
 *   2. 4th-Order Linkwitz-Riley HPF @ 180Hz (-45dB mains/hum cut)
 *   3. 4th-Order Linkwitz-Riley LPF @ 3400Hz (-64dB hiss cut)
 *   4. Soft-Knee Downward Expander (Zero output during pauses)
 *
 * @param out_mono Pointer to destination buffer (must hold `samples` elements).
 * @param samples Number of mono samples to read (e.g., AUDIO_FRAME_SAMPLES).
 * @param out_rms Output RMS value of the processed frame.
 * @return esp_err_t ESP_OK on success.
 */
esp_err_t audio_input_read_clean(int16_t *out_mono, int samples, float *out_rms);

/**
 * @brief Get calibrated ambient noise floor RMS.
 */
/**
 * @brief Flush stale DMA buffers (useful after playing loud tones).
 */
void audio_input_flush_buffers(void);

/**
 * @brief Determine if the frame RMS indicates active voice speech.
 */
bool audio_input_is_speech(float frame_rms);

#ifdef __cplusplus
}
#endif


