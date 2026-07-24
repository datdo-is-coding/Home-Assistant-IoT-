/*
 * ESP32-S3 N16R8 Voice Assistant Firmware (ESP-SR / ESP-Skainet)
 * DTV Energy Ecosystem - Smart Voice Control
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"

#include "esp_afe_sr_models.h"
#include "esp_afe_sr_iface.h"
#include "esp_nsn_models.h"
#include "model_path.h"

#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_mac.h"
#include "esp_now_protocol.h"
#include "esp_http_server.h"
#include "esp_ota_ops.h"


#ifndef MIN
#define MIN(a,b) (((a)<(b))?(a):(b))
#endif

static const char *TAG = "ESP32S3_VOICE_MASTER";

static uint8_t broadcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

#include "driver/rmt_tx.h"

#define RGB_LED_GPIO GPIO_NUM_48

static rmt_channel_handle_t led_chan = NULL;
static rmt_encoder_handle_t bytes_encoder = NULL;

static void init_rgb_led(void)
{
    rmt_tx_channel_config_t tx_chan_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = RGB_LED_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz = 10 * 1000 * 1000, // 10MHz (1 tick = 100ns)
        .trans_queue_depth = 4,
    };
    if (rmt_new_tx_channel(&tx_chan_config, &led_chan) == ESP_OK) {
        rmt_bytes_encoder_config_t bytes_encoder_config = {
            .bit0 = {
                .duration0 = 4,
                .level0 = 1,
                .duration1 = 8,
                .level1 = 0,
            },
            .bit1 = {
                .duration0 = 8,
                .level0 = 1,
                .duration1 = 4,
                .level1 = 0,
            },
            .flags = {
                .msb_first = 1
            }
        };
        if (rmt_new_bytes_encoder(&bytes_encoder_config, &bytes_encoder) == ESP_OK) {
            rmt_enable(led_chan);
            ESP_LOGI(TAG, "Hardware RMT WS2812 RGB LED Driver initialized on GPIO %d!", RGB_LED_GPIO);
            return;
        }
    }

    ESP_LOGE(TAG, "Failed to initialize RMT WS2812 RGB LED driver on GPIO %d", RGB_LED_GPIO);
}

static void set_rgb_led_color(uint8_t r, uint8_t g, uint8_t b)
{
    if (!led_chan || !bytes_encoder) return;
    uint8_t grb[3] = {g, r, b}; // WS2812 protocol requires Green-Red-Blue
    rmt_transmit_config_t tx_config = {
        .loop_count = 0,
    };
    rmt_transmit(led_chan, bytes_encoder, grb, sizeof(grb), &tx_config);
}


static void send_esp_now_request_power(void);



// Live Telemetry Cache for Web Dashboard & App
static float live_voltage = 0.0f;
static float live_current = 0.0f;
static float live_power   = 0.0f;
static float live_energy  = 0.0f;
static float live_freq    = 50.0f;
static float live_pf      = 1.0f;
static uint32_t last_telemetry_ms = 0;



// ============================================================================
// I2S MICROPHONE PIN DEFINITIONS (Default: INMP441 MEMS Mic)
// ============================================================================
#define MIC_I2S_PORT         I2S_NUM_0
#define MIC_I2S_GPIO_BCLK    GPIO_NUM_47
#define MIC_I2S_GPIO_WS      GPIO_NUM_10
#define MIC_I2S_GPIO_DIN     GPIO_NUM_21


// ============================================================================
// I2S SPEAKER / DAC PIN DEFINITIONS (Default: MAX98357A I2S DAC/AMP)
// ============================================================================
#define SPK_I2S_PORT         I2S_NUM_1
#define SPK_I2S_GPIO_BCLK    GPIO_NUM_15
#define SPK_I2S_GPIO_WS      GPIO_NUM_16
#define SPK_I2S_GPIO_DOUT    GPIO_NUM_7

static i2s_chan_handle_t rx_handle = NULL;
static i2s_chan_handle_t tx_handle = NULL;
static const esp_afe_sr_iface_t *afe_handle = &ESP_AFE_SR_HANDLE;
static esp_afe_sr_data_t *afe_data = NULL;
static volatile bool is_listening = false;


/**
 * @brief Initialize I2S Microphone Channel (16kHz, 16-bit Mono/Stereo)
 */
static esp_err_t init_i2s_microphone(void)
{
    ESP_LOGI(TAG, "Initializing INMP441 I2S Microphone (BCLK:%d, WS:%d, DIN:%d)...", 
             MIC_I2S_GPIO_BCLK, MIC_I2S_GPIO_WS, MIC_I2S_GPIO_DIN);

    i2s_chan_config_t chan_cfg = {
        .id = MIC_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = MIC_I2S_GPIO_BCLK,
            .ws   = MIC_I2S_GPIO_WS,
            .dout = I2S_GPIO_UNUSED,
            .din  = MIC_I2S_GPIO_DIN,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx_handle, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));
    ESP_LOGI(TAG, "INMP441 I2S Microphone successfully initialized!");
    return ESP_OK;
}

/**
 * @brief ESP-NOW Data Receive Callback (Handles packets from ESP32 WROOM Energy Slave)
 */
static void esp_now_recv_callback(const esp_now_recv_info_t *recv_info, const uint8_t *data, int len)
{
    if (len < sizeof(esp_now_packet_t)) {
        ESP_LOGW(TAG, "Received incomplete ESP-NOW packet (%d bytes)", len);
        return;
    }

    const esp_now_packet_t *pkt = (const esp_now_packet_t *)data;

    if (pkt->msg_type == MSG_TYPE_RESP_POWER_STATUS) {
        live_voltage = pkt->voltage;
        live_current = pkt->current;
        live_power   = pkt->power;
        live_energy  = pkt->energy;
        live_freq    = pkt->frequency;
        live_pf      = pkt->pf;
        last_telemetry_ms = (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS);

        // Flash Emerald Green RGB LED on successful packet reception!
        set_rgb_led_color(0, 200, 100);

        ESP_LOGI(TAG, "=================================================");
        ESP_LOGI(TAG, "⚡ LIVE POWER METRICS FROM ESP32 WROOM SLAVE:");
        ESP_LOGI(TAG, "  - Voltage    : %.2f V", pkt->voltage);
        ESP_LOGI(TAG, "  - Current    : %.3f A", pkt->current);
        ESP_LOGI(TAG, "  - Active Pwr : %.2f W", pkt->power);
        ESP_LOGI(TAG, "  - Energy     : %.3f kWh", pkt->energy);
        ESP_LOGI(TAG, "  - Frequency  : %.1f Hz", pkt->frequency);
        ESP_LOGI(TAG, "  - PowerFact  : %.2f", pkt->pf);
        ESP_LOGI(TAG, "=================================================");
    }

}

// ============================================================================
// WEB SERVER & WEB OTA IMPLEMENTATION
// ============================================================================

static const char index_html[] = 
"<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
"<title>ESP32-S3 Voice Master Hub</title>"
"<style>"
"body{background:#0f172a;color:#f8fafc;font-family:system-ui,sans-serif;margin:0;padding:20px;}"
".card{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:20px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.5);}"
"h1,h2{color:#38bdf8;margin-top:0;}"
".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:15px;}"
".metric{background:#0f172a;border-radius:8px;padding:12px;text-align:center;}"
".val{font-size:22px;font-weight:bold;color:#4ade80;}"
".lbl{font-size:12px;color:#94a3b8;margin-top:4px;}"
".btn{background:#0284c7;color:white;border:none;padding:10px 16px;border-radius:6px;font-weight:bold;cursor:pointer;}"
".btn:hover{background:#0369a1;}"
"</style></head><body>"
"<h1>🎙️ ESP32-S3 Voice Master & Power Hub</h1>"
"<div class=\"card\"><h2>⚡ Live Power Telemetry (from WROOM Slave)</h2>"
"<div class=\"grid\">"
"<div class=\"metric\"><div class=\"val\" id=\"v\">-- V</div><div class=\"lbl\">VOLTAGE</div></div>"
"<div class=\"metric\"><div class=\"val\" id=\"a\">-- A</div><div class=\"lbl\">CURRENT</div></div>"
"<div class=\"metric\"><div class=\"val\" id=\"w\">-- W</div><div class=\"lbl\">POWER</div></div>"
"<div class=\"metric\"><div class=\"val\" id=\"kwh\">-- kWh</div><div class=\"lbl\">ENERGY</div></div>"
"</div></div>"
"<div class=\"card\"><h2>🚀 Web OTA Firmware Update</h2>"
"<form method=\"POST\" action=\"/update\" enctype=\"multipart/form-data\">"
"<input type=\"file\" name=\"update\" accept=\".bin\" style=\"margin-bottom:12px;\"><br>"
"<button type=\"submit\" class=\"btn\">Upload & Flash Firmware (.bin)</button>"
"</form></div>"
"<script>"
"setInterval(async () => {"
"  try {"
"    let r = await fetch('/api/status');"
"    let d = await r.json();"
"    document.getElementById('v').innerText = d.voltage.toFixed(1) + ' V';"
"    document.getElementById('a').innerText = d.current.toFixed(2) + ' A';"
"    document.getElementById('w').innerText = d.power.toFixed(1) + ' W';"
"    document.getElementById('kwh').innerText = d.energy.toFixed(2) + ' kWh';"
"  }catch(e){}"
"}, 1000);"
"</script></body></html>";

static esp_err_t index_get_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, index_html, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t api_status_get_handler(httpd_req_t *req)
{
    char json_resp[256];
    snprintf(json_resp, sizeof(json_resp),
             "{\"voltage\":%.2f,\"current\":%.3f,\"power\":%.2f,\"energy\":%.3f,\"frequency\":%.1f,\"pf\":%.2f,\"wakenet\":\"Hi ESP\"}",
             live_voltage, live_current, live_power, live_energy, live_freq, live_pf);
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, json_resp, HTTPD_RESP_USE_STRLEN);
}

// Web OTA Handler
static esp_err_t update_post_handler(httpd_req_t *req)
{
    esp_ota_handle_t ota_handle;
    const esp_partition_t *update_partition = esp_ota_get_next_update_partition(NULL);
    if (!update_partition) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Starting Web OTA Update onto partition: %s", update_partition->label);
    esp_err_t err = esp_ota_begin(update_partition, OTA_WITH_SEQUENTIAL_WRITES, &ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_begin failed: %s", esp_err_to_name(err));
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    char buf[1024];
    int remaining = req->content_len;
    while (remaining > 0) {
        int recv_len = httpd_req_recv(req, buf, MIN(remaining, sizeof(buf)));
        if (recv_len <= 0) {
            if (recv_len == HTTPD_SOCK_ERR_TIMEOUT) continue;
            esp_ota_abort(ota_handle);
            httpd_resp_send_500(req);
            return ESP_FAIL;
        }
        err = esp_ota_write(ota_handle, buf, recv_len);
        if (err != ESP_OK) {
            esp_ota_abort(ota_handle);
            httpd_resp_send_500(req);
            return ESP_FAIL;
        }
        remaining -= recv_len;
    }

    err = esp_ota_end(ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_end failed: %s", esp_err_to_name(err));
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    err = esp_ota_set_boot_partition(update_partition);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_set_boot_partition failed: %s", esp_err_to_name(err));
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "OTA Update Successful! Rebooting ESP32-S3 in 1 second...");
    httpd_resp_sendstr(req, "<h1>OTA Firmware Update Successful! Rebooting...</h1>");
    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();
    return ESP_OK;
}

static httpd_handle_t start_web_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.stack_size = 8192;
    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t index_uri = { .uri = "/", .method = HTTP_GET, .handler = index_get_handler };
        httpd_register_uri_handler(server, &index_uri);

        httpd_uri_t api_uri = { .uri = "/api/status", .method = HTTP_GET, .handler = api_status_get_handler };
        httpd_register_uri_handler(server, &api_uri);

        httpd_uri_t update_uri = { .uri = "/update", .method = HTTP_POST, .handler = update_post_handler };
        httpd_register_uri_handler(server, &update_uri);

        ESP_LOGI(TAG, "Web Server & Web OTA Handlers registered on port 80");
    }
    return server;
}


/**
 * @brief ESP-NOW Data Send Callback
 */
static void esp_now_send_callback(const uint8_t *mac_addr, esp_now_send_status_t status)
{
    if (status == ESP_NOW_SEND_SUCCESS) {
        ESP_LOGI(TAG, ">>> ESP-NOW Packet Transmitted SUCCESSFULLY! <<<");
    } else {
        ESP_LOGE(TAG, ">>> ESP-NOW Packet Transmission FAILED! (Check Wi-Fi Channel match!) <<<");
    }
}

/**
 * @brief Initialize Wi-Fi in STA mode & ESP-NOW protocol
 */
static esp_err_t init_esp_now_master(void)
{
    ESP_LOGI(TAG, "Initializing ESP-NOW Wireless Communication (STA Mode, Channel 11)...");

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(11, WIFI_SECOND_CHAN_NONE));

    uint8_t s3_mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, s3_mac);
    ESP_LOGI(TAG, "ESP32-S3 Master STA MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             s3_mac[0], s3_mac[1], s3_mac[2], s3_mac[3], s3_mac[4], s3_mac[5]);

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_send_cb(esp_now_send_callback));
    ESP_ERROR_CHECK(esp_now_register_recv_cb(esp_now_recv_callback));

    // Register Broadcast Peer on WIFI_IF_STA Channel 11
    esp_now_peer_info_t peer_info = {0};
    memcpy(peer_info.peer_addr, broadcast_mac, 6);
    peer_info.channel = 11;
    peer_info.ifidx = WIFI_IF_STA; // Mandatory interface definition in ESP-IDF 5.x
    peer_info.encrypt = false;


    
    esp_err_t add_err = esp_now_add_peer(&peer_info);
    if (add_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add broadcast peer: %s", esp_err_to_name(add_err));
    }

    ESP_LOGI(TAG, "ESP-NOW Wireless Master successfully initialized!");
    return ESP_OK;
}




/**
 * @brief Transmit ESP-NOW Request to query live power metrics from WROOM Slave
 */
static void send_esp_now_request_power(void)
{
    ESP_LOGI(TAG, "📡 Sending ESP-NOW REQ_POWER_STATUS to ESP32 WROOM Energy Slave...");
    esp_now_packet_t pkt = {0};
    pkt.msg_type = MSG_TYPE_REQ_POWER_STATUS;
    pkt.device_id = 1; // Master ID
    pkt.timestamp_ms = (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS);

    esp_err_t err = esp_now_send(broadcast_mac, (const uint8_t *)&pkt, sizeof(pkt));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send ESP-NOW packet: 0x%x (%s)", err, esp_err_to_name(err));
    }
}


/**
 * @brief Initialize I2S Speaker Channel (16kHz, 16-bit Mono)
 */

static esp_err_t init_i2s_speaker(void)
{
    ESP_LOGI(TAG, "Initializing I2S Speaker DAC (BCLK:%d, WS:%d, DOUT:%d)...",
             SPK_I2S_GPIO_BCLK, SPK_I2S_GPIO_WS, SPK_I2S_GPIO_DOUT);

    i2s_chan_config_t chan_cfg = {
        .id = SPK_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear = true,
    };
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &tx_handle, NULL));

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = SPK_I2S_GPIO_BCLK,
            .ws   = SPK_I2S_GPIO_WS,
            .dout = SPK_I2S_GPIO_DOUT,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx_handle, &std_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(tx_handle));
    ESP_LOGI(TAG, "I2S Speaker DAC successfully initialized!");
    return ESP_OK;
}

/**
 * @brief Audio Feed Task: Reads raw 32-bit I2S audio samples from INMP441, converts to 16-bit & feeds into ESP-SR AFE
 */
static void audio_feed_task(void *arg)
{
    esp_afe_sr_data_t *afe_data = (esp_afe_sr_data_t *)arg;
    int audio_chunksize = afe_handle->get_feed_chunksize(afe_data);
    int nch = afe_handle->get_channel_num(afe_data);
    int feed_size = audio_chunksize * nch * sizeof(int16_t);

    // Alloc 32-bit stereo buffer for raw INMP441 DMA read
    int raw_buff_size = audio_chunksize * 2 * sizeof(int32_t);
    int32_t *raw_buff = (int32_t *)heap_caps_malloc(raw_buff_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!raw_buff) {
        raw_buff = (int32_t *)malloc(raw_buff_size);
    }

    int16_t *i2s_buff = (int16_t *)heap_caps_malloc(feed_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!i2s_buff) {
        i2s_buff = (int16_t *)malloc(feed_size);
    }

    if (!raw_buff || !i2s_buff) {
        ESP_LOGE(TAG, "Failed to allocate audio feed buffers!");
        vTaskDelete(NULL);
        return;
    }

    size_t bytes_read = 0;
    int frame_count = 0;
    ESP_LOGI(TAG, "Audio Feed Task started (chunk size: %d, INMP441 32-bit Stereo Decoding)", audio_chunksize);

    while (1) {
        esp_err_t ret = i2s_channel_read(rx_handle, raw_buff, raw_buff_size, &bytes_read, 100 / portTICK_PERIOD_MS);
        if (ret == ESP_OK && bytes_read > 0) {
            int samples_read = bytes_read / sizeof(int32_t);
            int mono_samples = samples_read / 2;
            if (mono_samples > audio_chunksize) mono_samples = audio_chunksize;

            // Convert Left Channel 24-bit PCM (in 32-bit slot) to 16-bit PCM for ESP-SR
            for (int i = 0; i < mono_samples; i++) {
                int32_t left_sample = raw_buff[i * 2]; // INMP441 L/R=GND is Left channel
                i2s_buff[i] = (int16_t)(left_sample >> 14); // Scale to 16-bit PCM
            }

            afe_handle->feed(afe_data, i2s_buff);

            // Log Mic Live Audio Level every ~0.5 seconds
            frame_count++;
            if (frame_count >= 50) {
                frame_count = 0;
                int64_t sum = 0;
                for (int i = 0; i < mono_samples; i++) {
                    sum += abs(i2s_buff[i]);
                }
                int avg_amp = mono_samples > 0 ? (int)(sum / mono_samples) : 0;

                char bar[21] = {0};
                int level = avg_amp / 150;
                if (level > 20) level = 20;
                for (int i = 0; i < 20; i++) {
                    bar[i] = (i < level) ? '#' : '-';
                }
                ESP_LOGI(TAG, "INMP441 Real Audio Level: %5d | [%s]", avg_amp, bar);
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }

    free(raw_buff);
    free(i2s_buff);
    vTaskDelete(NULL);
}


/**
 * @brief Audio Detect Task: Gets AFE results (WakeNet wake word detection / Voice activity)
 */
static void audio_detect_task(void *arg)
{
    esp_afe_sr_data_t *afe_data = (esp_afe_sr_data_t *)arg;
    int afe_chunksize = afe_handle->get_fetch_chunksize(afe_data);
    ESP_LOGI(TAG, "Audio Detect Task started (fetch chunk size: %d)", afe_chunksize);

    while (1) {
        afe_fetch_result_t *res = afe_handle->fetch(afe_data);
        if (!res || res->ret_value < 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        if (res->wakeup_state == WAKENET_DETECTED) {
            ESP_LOGW(TAG, ">>> [WAKENET DETECTED] Wake Word Triggered! (Wake Word Index: %d, Model Index: %d) <<<", 
                     res->wake_word_index, res->wakenet_model_index);
            is_listening = true;
            
            // Turn WS2812 RGB LED Bright Green on "Hi ESP" detection!
            set_rgb_led_color(0, 255, 0);

            // Trigger ESP-NOW request to ESP32 WROOM Energy Slave for power status
            send_esp_now_request_power();
        }

        if (res->vad_state == AFE_VAD_SPEECH && is_listening) {
            ESP_LOGD(TAG, "Voice Activity Detected (Speech in progress)...");
        }
    }

    vTaskDelete(NULL);
}

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(1000)); // Allow serial monitor to connect
    ESP_LOGI(TAG, "=================================================");
    ESP_LOGI(TAG, "   DTV ENERGY - ESP32-S3 N16R8 VOICE MASTER    ");
    ESP_LOGI(TAG, "=================================================");

    // 0. Initialize WS2812 RGB LED Indicator (Blue on Boot)
    init_rgb_led();
    set_rgb_led_color(0, 0, 150);

    // 1. Initialize NVS Flash
    esp_err_t ret = nvs_flash_init();

    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS flash due to version mismatch...");
        nvs_flash_erase();
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS Flash Init failed: %s", esp_err_to_name(ret));
    }

    // 2. Initialize ESP-NOW Master Protocol & HTTP Web Server with Web OTA
    init_esp_now_master();
    start_web_server();




    // 3. Check & Log Memory Status (Octal PSRAM 8MB)
    size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    size_t psram_free    = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);

    ESP_LOGI(TAG, "Free Internal RAM : %d KB", (int)(internal_free / 1024));
    ESP_LOGI(TAG, "Free Octal PSRAM  : %d KB (%d MB)", (int)(psram_free / 1024), (int)(psram_free / (1024 * 1024)));

    if (psram_free < 1024 * 1024) {
        ESP_LOGW(TAG, "WARNING: Octal PSRAM is less than 1MB or not initialized!");
    }

    // 3. Initialize Audio Hardware
    esp_err_t mic_err = init_i2s_microphone();
    if (mic_err != ESP_OK) {
        ESP_LOGE(TAG, "Microphone Init Failed: %s", esp_err_to_name(mic_err));
    }

    esp_err_t spk_err = init_i2s_speaker();
    if (spk_err != ESP_OK) {
        ESP_LOGW(TAG, "Speaker Init Warning (optional): %s", esp_err_to_name(spk_err));
    }

    // 4. Configure ESP-SR Audio Front-End (AFE)
    srmodel_list_t *models = esp_srmodel_init("model");
    if (!models) {
        ESP_LOGE(TAG, "CRITICAL: Failed to load speech recognition models from 'model' partition!");
    } else {
        ESP_LOGI(TAG, "Successfully loaded %d speech recognition models from flash!", models->num);
    }

    afe_config_t afe_config = AFE_CONFIG_DEFAULT();
    afe_config.aec_init = false;  // AEC requires ref_num > 0. Disable for 1-mic setup.
    afe_config.se_init = true;   // Speech enhancement (noise suppression)
    afe_config.vad_init = true;  // Voice activity detection
    afe_config.wakenet_init = true;
    afe_config.wakenet_model_name = "wn9_hiesp";
    afe_config.wakenet_mode = DET_MODE_2CH_90;

    afe_config.afe_mode = SR_MODE_LOW_COST;
    afe_config.memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_PSRAM;
    afe_config.pcm_config.total_ch_num = 1;
    afe_config.pcm_config.mic_num = 1;
    afe_config.pcm_config.ref_num = 0;

    afe_data = afe_handle->create_from_config(&afe_config);

    if (!afe_data) {
        ESP_LOGE(TAG, "CRITICAL ERROR: Failed to create ESP-SR AFE Engine! Check PSRAM!");
        return;
    }

    ESP_LOGI(TAG, "ESP-SR AFE Engine & WakeNet Pipeline successfully created!");

    // 5. Create Audio Tasks
    xTaskCreatePinnedToCore(audio_feed_task, "audio_feed_task", 8 * 1024, afe_data, 5, NULL, 0);
    xTaskCreatePinnedToCore(audio_detect_task, "audio_detect_task", 8 * 1024, afe_data, 5, NULL, 1);

    ESP_LOGI(TAG, "System ready. Say 'Hi ESP' to wake up the system.");
}