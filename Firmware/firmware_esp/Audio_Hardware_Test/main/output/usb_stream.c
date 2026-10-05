#include "usb_stream.h"
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/usb_serial_jtag.h"

static const char *TAG = "USB_STREAM";

static uint16_t s_seq = 0;
static bool s_driver_installed = false;

#pragma pack(push, 1)
typedef struct {
    char     riff[4];             /* "RIFF" */
    uint32_t overall_size;        /* File size - 8 */
    char     wave[4];             /* "WAVE" */
    char     fmt_chunk_marker[4]; /* "fmt " */
    uint32_t length_of_fmt;       /* 16 */
    uint16_t format_type;         /* 1 = PCM */
    uint16_t channels;            /* 1 = Mono */
    uint32_t sample_rate;         /* 16000 */
    uint32_t byterate;            /* sample_rate * channels * 2 */
    uint16_t block_align;         /* channels * 2 */
    uint16_t bits_per_sample;     /* 16 */
    char     data_chunk_header[4];/* "data" */
    uint32_t data_size;           /* num_samples * 2 */
} wav_header_t;
#pragma pack(pop)

esp_err_t usb_stream_init(void)
{
    if (!usb_serial_jtag_is_driver_installed()) {
        usb_serial_jtag_driver_config_t cfg = {
            .tx_buffer_size = 4096,
            .rx_buffer_size = 1024,
        };
        esp_err_t err = usb_serial_jtag_driver_install(&cfg);
        if (err == ESP_OK) {
            s_driver_installed = true;
            ESP_LOGI(TAG, "✅ USB-Serial-JTAG driver installed (TX: 4KB, RX: 1KB)");
        } else {
            ESP_LOGW(TAG, "USB driver install returned: %s", esp_err_to_name(err));
        }
    } else {
        s_driver_installed = true;
        ESP_LOGI(TAG, "ℹ️ USB-Serial-JTAG driver already installed by console");
    }

    s_seq = 0;
    return ESP_OK;
}

bool usb_stream_is_connected(void)
{
    return usb_serial_jtag_is_connected();
}

char usb_stream_poll_cmd(void)
{
    uint8_t byte = 0;
    int n = usb_serial_jtag_read_bytes(&byte, 1, 0);
    if (n > 0) {
        return (char)byte;
    }
    return '\0';
}

static esp_err_t send_packet(usb_pkt_type_t type, uint8_t flags, const void *payload, uint16_t payload_len)
{
    usb_pkt_header_t hdr;
    hdr.magic[0] = USB_PKT_MAGIC_0;
    hdr.magic[1] = USB_PKT_MAGIC_1;
    hdr.type     = (uint8_t)type;
    hdr.flags    = flags;
    hdr.length   = payload_len;
    hdr.seq      = s_seq++;

    /* Compute XOR Checksum */
    uint8_t chk = 0;
    const uint8_t *h_bytes = (const uint8_t *)&hdr;
    for (size_t i = 0; i < sizeof(usb_pkt_header_t); i++) {
        chk ^= h_bytes[i];
    }
    if (payload && payload_len > 0) {
        const uint8_t *p_bytes = (const uint8_t *)payload;
        for (uint16_t i = 0; i < payload_len; i++) {
            chk ^= p_bytes[i];
        }
    }

    /* Send Header */
    usb_serial_jtag_write_bytes(&hdr, sizeof(usb_pkt_header_t), pdMS_TO_TICKS(50));

    /* Send Payload */
    if (payload && payload_len > 0) {
        usb_serial_jtag_write_bytes(payload, payload_len, pdMS_TO_TICKS(50));
    }

    /* Send Checksum (1 byte) */
    usb_serial_jtag_write_bytes(&chk, 1, pdMS_TO_TICKS(20));

    return ESP_OK;
}

esp_err_t usb_stream_send_start(uint32_t sample_rate, uint16_t channels, uint16_t bits_per_sample)
{
    s_seq = 0;
    uint32_t info[3] = { sample_rate, (uint32_t)channels, (uint32_t)bits_per_sample };
    return send_packet(USB_PKT_TYPE_START, USB_FLAG_NONE, info, sizeof(info));
}

esp_err_t usb_stream_send_frame(const int16_t *pcm_mono, int num_samples, bool is_speech, bool button_down)
{
    if (!pcm_mono || num_samples <= 0) return ESP_ERR_INVALID_ARG;

    uint8_t flags = USB_FLAG_NONE;
    if (is_speech)   flags |= USB_FLAG_VAD_ACTIVE;
    if (button_down) flags |= USB_FLAG_BUTTON_DN;

    uint16_t bytes = num_samples * sizeof(int16_t);
    return send_packet(USB_PKT_TYPE_AUDIO, flags, pcm_mono, bytes);
}

esp_err_t usb_stream_send_end(uint32_t total_samples)
{
    uint32_t info[2] = { total_samples, AUDIO_SAMPLE_RATE };
    return send_packet(USB_PKT_TYPE_END, USB_FLAG_NONE, info, sizeof(info));
}

esp_err_t usb_stream_send_wav_header(uint32_t num_samples)
{
    wav_header_t wav;
    memcpy(wav.riff, "RIFF", 4);
    wav.overall_size = 36 + (num_samples * 2);
    memcpy(wav.wave, "WAVE", 4);
    memcpy(wav.fmt_chunk_marker, "fmt ", 4);
    wav.length_of_fmt = 16;
    wav.format_type = 1; /* PCM */
    wav.channels = 1;    /* Mono */
    wav.sample_rate = AUDIO_SAMPLE_RATE;
    wav.byterate = AUDIO_SAMPLE_RATE * 1 * 2;
    wav.block_align = 2;
    wav.bits_per_sample = 16;
    memcpy(wav.data_chunk_header, "data", 4);
    wav.data_size = num_samples * 2;

    return send_packet(USB_PKT_TYPE_END, USB_FLAG_NONE, &wav, sizeof(wav_header_t));
}
