/*
 * AETHERIA OS — ESP32-S3 Robust OTA Firmware Updater
 *
 * Implements high-reliability HTTP Pull OTA with:
 * - Anti-brick dual partition switching (ota_0 <-> ota_1)
 * - Automatic rollback cancellation upon confirmed healthy boot
 * - ESP image magic byte (0xE9) header verification
 * - MD5 checksum verification
 * - Real-time progress reporting (0-100%) via MQTT and WebSocket
 * - Dedicated FreeRTOS task with watchdog yielding and hardware status LEDs
 */

#include "ota_updater.h"
#include "esp_ota_ops.h"
#include "esp_http_client.h"
#include "esp_app_format.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/md5.h"
#include "audio_feedback.h"
#include "mqtt_relay.h"
#include "ws_audio_client.h"

#include <string.h>
#include <stdio.h>

static const char *TAG = "OTA_UPDATER";

#define OTA_BUF_SIZE         (4096)
#define OTA_TASK_STACK_SIZE  (8192)
#define OTA_TASK_PRIORITY    (5)

#ifndef ESP_IMAGE_MAGIC
#define ESP_IMAGE_MAGIC      (0xE9)
#endif

extern void led1_set(bool on);
extern void led2_set(bool on);

typedef struct {
    char url[256];
    size_t expected_size;
    char expected_md5[36];
} ota_task_param_t;

static volatile bool s_ota_in_progress = false;
static TaskHandle_t s_ota_task_handle = NULL;

/* ─── Initialization & Rollback Confirmation ─────────────────────────── */

esp_err_t ota_updater_init(void)
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (!running) {
        ESP_LOGE(TAG, "Cannot get running partition!");
        return ESP_FAIL;
    }

    const esp_partition_t *next_update = esp_ota_get_next_update_partition(NULL);
    ESP_LOGI(TAG, "🟢 Running partition: '%s' (0x%08lX, %lu KB)",
             running->label, (unsigned long)running->address, (unsigned long)running->size / 1024);
    if (next_update) {
        ESP_LOGI(TAG, "🔄 Next OTA target: '%s' (0x%08lX, %lu KB)",
                 next_update->label, (unsigned long)next_update->address, (unsigned long)next_update->size / 1024);
    }

    /* Check if current image is in pending verify state (first boot after OTA) */
    esp_ota_img_states_t ota_state;
    if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK) {
        if (ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
            ESP_LOGW(TAG, "✨ First boot on new OTA partition! Validating and cancelling rollback...");
            esp_err_t err = esp_ota_mark_app_valid_cancel_rollback();
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "✅ App marked valid: Rollback cancelled. New firmware confirmed stable!");
            } else {
                ESP_LOGE(TAG, "❌ Failed to mark app valid: %s", esp_err_to_name(err));
            }
        } else if (ota_state == ESP_OTA_IMG_VALID) {
            ESP_LOGI(TAG, "Current firmware status: VALID");
        }
    }

    return ESP_OK;
}

bool ota_updater_is_in_progress(void)
{
    return s_ota_in_progress;
}

/* ─── Dedicated OTA Background Task ──────────────────────────────────── */

static void ota_task(void *pvParameter)
{
    ota_task_param_t *param = (ota_task_param_t *)pvParameter;
    char *ota_buf = malloc(OTA_BUF_SIZE);
    if (!ota_buf) {
        ESP_LOGE(TAG, "Failed to allocate %d bytes for OTA buffer", OTA_BUF_SIZE);
        mqtt_relay_publish_ota_progress(0, "failed", "Out of memory allocating OTA buffer");
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "🚀 [OTA Task] Initiating HTTP Pull from: %s", param->url);

    /* 1. Hardware LED & Audio indicator (LED1=IO48, LED2=IO47) */
    led1_set(true);
    led2_set(true);
    audio_feedback_play(AUDIO_FB_TING);

    mqtt_relay_publish_ota_progress(0, "downloading", "Ket noi toi Gateway OTA...");

    /* 2. Configure HTTP Client */
    esp_http_client_config_t http_cfg = {
        .url = param->url,
        .timeout_ms = 15000,
        .keep_alive_enable = true,
        .buffer_size = 4096,
        .buffer_size_tx = 1024,
    };

    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        ESP_LOGE(TAG, "Failed to initialize HTTP client");
        mqtt_relay_publish_ota_progress(0, "failed", "HTTP client init failed");
        free(ota_buf);
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open HTTP connection: %s", esp_err_to_name(err));
        mqtt_relay_publish_ota_progress(0, "failed", "Khong the ket noi toi Gateway HTTP");
        esp_http_client_cleanup(client);
        free(ota_buf);
        s_ota_in_progress = false;
        led1_set(false);
        led2_set(false);
        audio_feedback_play(AUDIO_FB_ERROR);
        vTaskDelete(NULL);
        return;
    }

    int content_length = esp_http_client_fetch_headers(client);
    int status_code = esp_http_client_get_status_code(client);
    ESP_LOGI(TAG, "HTTP response status = %d, content_length = %d bytes", status_code, content_length);

    if (status_code != 200) {
        ESP_LOGE(TAG, "HTTP error status: %d (expected 200 OK)", status_code);
        char err_msg[64];
        snprintf(err_msg, sizeof(err_msg), "HTTP error %d", status_code);
        mqtt_relay_publish_ota_progress(0, "failed", err_msg);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        free(ota_buf);
        s_ota_in_progress = false;
        led1_set(false);
        led2_set(false);
        audio_feedback_play(AUDIO_FB_ERROR);
        vTaskDelete(NULL);
        return;
    }

    /* 3. Determine target OTA partition */
    const esp_partition_t *update_partition = esp_ota_get_next_update_partition(NULL);
    if (!update_partition) {
        ESP_LOGE(TAG, "Passive OTA partition not found!");
        mqtt_relay_publish_ota_progress(0, "failed", "Passive OTA partition not found");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        free(ota_buf);
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    if (content_length > 0 && content_length > update_partition->size) {
        ESP_LOGE(TAG, "Firmware size (%d B) exceeds partition capacity (%lu B)!",
                 content_length, (unsigned long)update_partition->size);
        mqtt_relay_publish_ota_progress(0, "failed", "Firmware size exceeds partition");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        free(ota_buf);
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    /* 4. Begin OTA session */
    esp_ota_handle_t ota_handle = 0;
    err = esp_ota_begin(update_partition, OTA_WITH_SEQUENTIAL_WRITES, &ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_begin failed: %s", esp_err_to_name(err));
        mqtt_relay_publish_ota_progress(0, "failed", "esp_ota_begin failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        free(ota_buf);
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Writing firmware to partition '%s' (0x%08lX)...",
             update_partition->label, (unsigned long)update_partition->address);

    /* 5. Initialize MD5 context for on-the-fly checksum verification */
    mbedtls_md5_context md5_ctx;
    mbedtls_md5_init(&md5_ctx);
    mbedtls_md5_starts(&md5_ctx);

    /* 6. Download & Flash Loop */
    int binary_file_len = 0;
    int last_reported_percent = -1;
    bool image_header_checked = false;
    bool flash_error = false;

    while (1) {
        int data_read = esp_http_client_read(client, ota_buf, OTA_BUF_SIZE);
        if (data_read < 0) {
            ESP_LOGE(TAG, "Error reading HTTP stream (code: %d)", data_read);
            flash_error = true;
            break;
        } else if (data_read > 0) {
            /* Verify ESP32 Image Header Magic Byte on first chunk */
            if (!image_header_checked) {
                if ((uint8_t)ota_buf[0] != ESP_IMAGE_MAGIC) {
                    ESP_LOGE(TAG, "❌ Invalid ESP image magic byte: 0x%02X (expected 0x%02X)",
                             (uint8_t)ota_buf[0], ESP_IMAGE_MAGIC);
                    mqtt_relay_publish_ota_progress(0, "failed", "Invalid ESP image magic byte (not a valid .bin)");
                    flash_error = true;
                    break;
                }
                image_header_checked = true;
                ESP_LOGI(TAG, "✅ ESP32 image magic byte verified (0x%02X)", ESP_IMAGE_MAGIC);
            }

            err = esp_ota_write(ota_handle, (const void *)ota_buf, data_read);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "esp_ota_write failed: %s", esp_err_to_name(err));
                flash_error = true;
                break;
            }

            mbedtls_md5_update(&md5_ctx, (const unsigned char *)ota_buf, data_read);
            binary_file_len += data_read;

            /* Calculate progress */
            int total = (content_length > 0) ? content_length : (int)param->expected_size;
            int cur_percent = (total > 0) ? ((binary_file_len * 100) / total) : 0;
            if (cur_percent > 100) cur_percent = 100;

            if (cur_percent != last_reported_percent && (cur_percent % 5 == 0 || cur_percent == 100)) {
                last_reported_percent = cur_percent;
                ESP_LOGI(TAG, "📊 OTA Progress: %d%% (%d / %d KB)",
                         cur_percent, binary_file_len / 1024, total / 1024);
                mqtt_relay_publish_ota_progress(cur_percent, "downloading", NULL);
            }

            /* Blink LED2 (GPIO 47) during flashing activity */
            static int s_chunk_cnt = 0;
            led2_set((++s_chunk_cnt % 16) < 8);

            /* Yield CPU to allow FreeRTOS IDLE and WiFi tasks to run smoothly */
            vTaskDelay(pdMS_TO_TICKS(1));
        } else {
            /* data_read == 0 -> EOF */
            ESP_LOGI(TAG, "HTTP stream read finished. Total downloaded: %d bytes", binary_file_len);
            break;
        }
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    free(ota_buf);

    if (flash_error) {
        mbedtls_md5_free(&md5_ctx);
        esp_ota_abort(ota_handle);
        mqtt_relay_publish_ota_progress(0, "failed", "Lỗi trong quá trình ghi Flash");
        s_ota_in_progress = false;
        led1_set(false);
        led2_set(false);
        audio_feedback_play(AUDIO_FB_ERROR);
        vTaskDelete(NULL);
        return;
    }

    /* 7. Verify MD5 Checksum */
    unsigned char md5_bytes[16];
    mbedtls_md5_finish(&md5_ctx, md5_bytes);
    mbedtls_md5_free(&md5_ctx);

    char computed_md5[33];
    for (int i = 0; i < 16; i++) {
        snprintf(&computed_md5[i * 2], 3, "%02x", md5_bytes[i]);
    }
    ESP_LOGI(TAG, "Computed MD5: %s", computed_md5);

    if (param->expected_md5[0] != '\0') {
        if (strcasecmp(computed_md5, param->expected_md5) != 0) {
            ESP_LOGE(TAG, "❌ MD5 Mismatch! Computed: %s vs Expected: %s",
                     computed_md5, param->expected_md5);
            esp_ota_abort(ota_handle);
            mqtt_relay_publish_ota_progress(0, "failed", "MD5 checksum mismatch");
            s_ota_in_progress = false;
            led1_set(false);
            led2_set(false);
            audio_feedback_play(AUDIO_FB_ERROR);
            vTaskDelete(NULL);
            return;
        }
        ESP_LOGI(TAG, "✅ MD5 Checksum verified successfully!");
    }

    /* 8. End OTA and switch boot partition */
    err = esp_ota_end(ota_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_end failed: %s", esp_err_to_name(err));
        mqtt_relay_publish_ota_progress(0, "failed", "esp_ota_end failed");
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    err = esp_ota_set_boot_partition(update_partition);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_set_boot_partition failed: %s", esp_err_to_name(err));
        mqtt_relay_publish_ota_progress(0, "failed", "esp_ota_set_boot_partition failed");
        s_ota_in_progress = false;
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "🎉 ===========================================================");
    ESP_LOGI(TAG, "🎉 OTA Flash SUCCESS! Next boot partition: '%s'", update_partition->label);
    ESP_LOGI(TAG, "🎉 Rebooting ESP32-S3 in 1.5 seconds...");
    ESP_LOGI(TAG, "🎉 ===========================================================");

    mqtt_relay_publish_ota_progress(100, "success", "Nạp thành công! Đang khởi động lại...");
    audio_feedback_play(AUDIO_FB_SUCCESS);
    led1_set(true);
    led2_set(false);

    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();
}

esp_err_t ota_updater_start_http_pull(const char *download_url, size_t expected_size, const char *expected_md5)
{
    if (s_ota_in_progress) {
        ESP_LOGW(TAG, "OTA update is already in progress!");
        return ESP_ERR_INVALID_STATE;
    }

    if (!download_url || strlen(download_url) < 8) {
        ESP_LOGE(TAG, "Invalid OTA download URL: %s", download_url ? download_url : "NULL");
        return ESP_ERR_INVALID_ARG;
    }

    static ota_task_param_t s_param;
    memset(&s_param, 0, sizeof(s_param));
    strncpy(s_param.url, download_url, sizeof(s_param.url) - 1);
    s_param.expected_size = expected_size;
    if (expected_md5) {
        strncpy(s_param.expected_md5, expected_md5, sizeof(s_param.expected_md5) - 1);
    }

    s_ota_in_progress = true;

    BaseType_t ret = xTaskCreate(
        ota_task,
        "ota_task",
        OTA_TASK_STACK_SIZE,
        &s_param,
        OTA_TASK_PRIORITY,
        &s_ota_task_handle
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create FreeRTOS ota_task!");
        s_ota_in_progress = false;
        return ESP_ERR_NO_MEM;
    }

    return ESP_OK;
}
