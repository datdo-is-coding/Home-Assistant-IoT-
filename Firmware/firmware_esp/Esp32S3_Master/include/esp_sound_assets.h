/*
 * Studio Acoustic Soundscapes for ESP32-S3.
 * All audio formatted at 16kHz, 16-bit Mono Little-Endian Signed Raw PCM.
 * Resides in Flash RODATA (0 bytes internal SRAM consumed).
 */

#ifndef ESP_SOUND_ASSETS_H
#define ESP_SOUND_ASSETS_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

extern const size_t bootup_sound_pcm_len;
extern const uint8_t bootup_sound_pcm[];

extern const size_t listen_success_pcm_len;
extern const uint8_t listen_success_pcm[];

extern const size_t new_noti_pcm_len;
extern const uint8_t new_noti_pcm[];

extern const size_t wrong_sound_pcm_len;
extern const uint8_t wrong_sound_pcm[];

#ifdef __cplusplus
}
#endif

#endif /* ESP_SOUND_ASSETS_H */
