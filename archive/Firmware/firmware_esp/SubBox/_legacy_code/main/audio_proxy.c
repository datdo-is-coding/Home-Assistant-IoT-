/*
 * Audio Proxy — Implementation
 * DTV Smart Home — T2 Zone Controller
 */

#include "audio_proxy.h"
#include "ws_audio_client.h"
#include "audio_feedback.h"
#include "esp_now_protocol.h"
#include "adpcm.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "AUDIO_PROXY";

static uint8_t s_active_t1_mac[6] = {0};
static volatile bool s_is_active = false;
static uint8_t s_current_codec = CODEC_RAW_PCM;
static adpcm_state_t s_adpcm_dec_state;
static int16_t s_pcm_dec_buf[480];

esp_err_t audio_proxy_init(const char *gateway_ws_uri, i2s_chan_handle_t spk_handle)
{
    ESP_LOGI(TAG, "Initializing Audio Proxy (Gateway WS: %s)...", gateway_ws_uri);

    /* Initialize local feedback chimes */
    if (spk_handle) {
        audio_feedback_init(spk_handle);
    }

    /* Initialize Gateway WebSocket audio client */
    esp_err_t err = ws_audio_client_init(gateway_ws_uri, spk_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init ws_audio_client: %s", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

void audio_proxy_on_stream_start(const uint8_t *sender_mac, uint8_t wake_word_index, uint8_t codec)
{
    memcpy(s_active_t1_mac, sender_mac, 6);
    s_is_active = true;
    s_current_codec = codec;
    adpcm_init_state(&s_adpcm_dec_state);

    ESP_LOGI(TAG, "🎙️ Audio stream started by T1 [%02X:%02X:%02X:%02X:%02X:%02X] (wake_word=%d, codec=%s)",
             sender_mac[0], sender_mac[1], sender_mac[2],
             sender_mac[3], sender_mac[4], sender_mac[5],
             wake_word_index, (codec == CODEC_IMA_ADPCM) ? "ADPCM" : "RAW_PCM");

    /* Play prompt Ding! feedback chime through T2's speaker */
    audio_feedback_play(AUDIO_FB_WAKEUP);

    /* Start WebSocket audio stream to Gateway */
    if (!ws_audio_is_streaming()) {
        esp_err_t err = ws_audio_start_stream();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "ws_audio_start_stream returned %s", esp_err_to_name(err));
        }
    }
}

void audio_proxy_on_chunk(const uint8_t *sender_mac, const uint8_t *pcm_data, uint16_t pcm_len)
{
    if (!s_is_active) return;

    if (s_current_codec == CODEC_IMA_ADPCM) {
        /* Decode 4-bit ADPCM into 16-bit PCM samples */
        int decoded_samples = adpcm_decode(pcm_data, pcm_len, s_pcm_dec_buf, &s_adpcm_dec_state);
        ws_audio_feed_pcm(s_pcm_dec_buf, decoded_samples);
    } else {
        /* Raw PCM 16-bit */
        int num_samples = pcm_len / sizeof(int16_t);
        ws_audio_feed_pcm((const int16_t *)pcm_data, num_samples);
    }
}

void audio_proxy_on_stream_end(const uint8_t *sender_mac, uint16_t total_chunks, uint32_t total_pcm_bytes)
{
    ESP_LOGI(TAG, "🎙️ Audio stream ended by T1 [%02X:%02X:%02X:%02X:%02X:%02X] (chunks=%u, bytes=%lu)",
             sender_mac[0], sender_mac[1], sender_mac[2],
             sender_mac[3], sender_mac[4], sender_mac[5],
             total_chunks, (unsigned long)total_pcm_bytes);

    /* Immediately notify Gateway that speech has ended */
    ws_audio_stop_stream();

    s_is_active = false;
    memset(s_active_t1_mac, 0, 6);
}

bool audio_proxy_is_active(void)
{
    return s_is_active || ws_audio_is_streaming();
}
