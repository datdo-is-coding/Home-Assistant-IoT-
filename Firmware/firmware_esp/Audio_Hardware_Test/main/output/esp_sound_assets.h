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

#endif
