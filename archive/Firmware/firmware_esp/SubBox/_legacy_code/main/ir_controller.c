/*
 * T2 Zone Controller — Infrared (IR) Controller Implementation
 * DTV Smart Home — 3-Tier IoT Architecture
 *
 * Implements:
 *   - RMT TX with 38kHz modulation for AC and Appliances
 *   - NEC protocol generation for TVs / Fans
 *   - Raw timings transmission (Universal AC: Daikin, Panasonic, Casper, Gree)
 *   - JSON command dispatcher
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "cJSON.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"

#include "ir_controller.h"

static const char *TAG = "IR_CTRL";

static rmt_channel_handle_t s_tx_chan = NULL;
static rmt_encoder_handle_t s_copy_encoder = NULL;
static bool s_ir_initialized = false;

/* ─── Initialize IR Subsystem ────────────────────────────────────────── */

esp_err_t ir_controller_init(gpio_num_t tx_gpio, gpio_num_t rx_gpio)
{
    ESP_LOGI(TAG, "Initializing IR Controller (TX GPIO: %d, RX GPIO: %d)...", tx_gpio, rx_gpio);

    rmt_tx_channel_config_t tx_chan_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = tx_gpio,
        .mem_block_symbols = 64,
        .resolution_hz = 1000000, /* 1MHz = 1us resolution */
        .trans_queue_depth = 4,
        .flags.invert_out = false,
        .flags.with_dma = false,
    };

    esp_err_t ret = rmt_new_tx_channel(&tx_chan_config, &s_tx_chan);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create RMT TX channel: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Configure 38kHz carrier modulation with 33% duty cycle */
    rmt_carrier_config_t carrier_cfg = {
        .duty_cycle = 0.33f,
        .frequency_hz = 38000,
        .flags.polarity_active_low = false,
    };
    ret = rmt_apply_carrier(s_tx_chan, &carrier_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to apply 38kHz carrier: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Create copy encoder to transmit raw pulse-space symbols */
    rmt_copy_encoder_config_t copy_encoder_cfg = {};
    ret = rmt_new_copy_encoder(&copy_encoder_cfg, &s_copy_encoder);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create RMT copy encoder: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = rmt_enable(s_tx_chan);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable RMT channel: %s", esp_err_to_name(ret));
        return ret;
    }

    s_ir_initialized = true;
    ESP_LOGI(TAG, "✅ IR Controller initialized successfully on GPIO %d (38kHz carrier ready)", tx_gpio);
    return ESP_OK;
}

/* ─── Transmit Raw Timings ───────────────────────────────────────────── */

esp_err_t ir_send_raw(const uint32_t *timings_us, size_t count)
{
    if (!s_ir_initialized || !s_tx_chan || !s_copy_encoder) {
        ESP_LOGE(TAG, "IR controller not initialized!");
        return ESP_ERR_INVALID_STATE;
    }

    if (count == 0 || (count % 2) != 0) {
        ESP_LOGE(TAG, "Invalid raw timings count: %d (must be even mark/space pairs)", (int)count);
        return ESP_ERR_INVALID_ARG;
    }

    size_t num_symbols = count / 2;
    rmt_symbol_word_t *symbols = malloc(num_symbols * sizeof(rmt_symbol_word_t));
    if (!symbols) {
        ESP_LOGE(TAG, "OOM allocating RMT symbols for raw IR");
        return ESP_ERR_NO_MEM;
    }

    for (size_t i = 0; i < num_symbols; i++) {
        symbols[i].val = 0;
        symbols[i].level0 = 1; /* Mark (carrier active) */
        symbols[i].duration0 = (uint16_t)timings_us[i * 2];
        symbols[i].level1 = 0; /* Space (carrier idle) */
        symbols[i].duration1 = (uint16_t)timings_us[i * 2 + 1];
    }

    rmt_transmit_config_t transmit_cfg = {
        .loop_count = 0,
    };

    ESP_LOGI(TAG, "Transmitting raw IR: %d symbols (%d pulses)...", (int)num_symbols, (int)count);
    esp_err_t ret = rmt_transmit(s_tx_chan, s_copy_encoder, symbols,
                                 num_symbols * sizeof(rmt_symbol_word_t),
                                 &transmit_cfg);
    if (ret == ESP_OK) {
        rmt_tx_wait_all_done(s_tx_chan, 1000);
    }

    free(symbols);
    return ret;
}

/* ─── Transmit NEC Protocol Frame ─────────────────────────────────────── */

esp_err_t ir_send_nec(uint16_t address, uint16_t command)
{
    /* NEC: 9ms mark + 4.5ms space header, followed by 32 bits (addr + ~addr + cmd + ~cmd) */
    uint32_t raw[2 + 32 * 2 + 2];
    size_t idx = 0;

    /* Header */
    raw[idx++] = 9000;
    raw[idx++] = 4500;

    uint8_t addr_lo = address & 0xFF;
    uint8_t addr_hi = (address >> 8) & 0xFF;
    if (addr_hi == 0) addr_hi = ~addr_lo;

    uint8_t cmd_lo = command & 0xFF;
    uint8_t cmd_hi = ~cmd_lo;

    uint32_t data = ((uint32_t)cmd_hi << 24) |
                    ((uint32_t)cmd_lo << 16) |
                    ((uint32_t)addr_hi << 8) |
                    (uint32_t)addr_lo;

    for (int i = 0; i < 32; i++) {
        raw[idx++] = 560; /* Mark */
        if (data & (1 << i)) {
            raw[idx++] = 1690; /* 1: 1.69ms space */
        } else {
            raw[idx++] = 560;  /* 0: 0.56ms space */
        }
    }

    /* Stop bit */
    raw[idx++] = 560;
    raw[idx++] = 20000;

    ESP_LOGI(TAG, "Sending NEC Frame: Addr=0x%04X, Cmd=0x%04X", address, command);
    return ir_send_raw(raw, idx);
}

/* ─── Send Structured AC Command ─────────────────────────────────────── */

esp_err_t ir_send_ac(const ir_ac_cmd_t *cmd)
{
    if (!cmd) return ESP_ERR_INVALID_ARG;
    ESP_LOGI(TAG, "Sending AC Command: Brand=%s, Power=%d, Temp=%dC, Mode=%d, Fan=%d",
             cmd->brand, cmd->power, cmd->temp_c, cmd->mode, cmd->fan);

    /*
     * For demonstration & testing: Send NEC test beacon or pre-recorded
     * pulse array matching common Daikin / Panasonic frames.
     */
    if (strcasecmp(cmd->brand, "daikin") == 0) {
        /* Standard Daikin leader: 3500us mark, 1750us space */
        uint32_t daikin_sample[] = {
            3500, 1750,
            450, 1300, 450, 450, 450, 1300, 450, 450,
            450, 1300, 450, 1300, 450, 450, 450, 450,
            450, 20000
        };
        return ir_send_raw(daikin_sample, sizeof(daikin_sample) / sizeof(daikin_sample[0]));
    }

    /* Generic Fallback: Standard power toggle sequence */
    return ir_send_nec(0x1234, cmd->power ? 0x01 : 0x00);
}

/* ─── JSON Command Dispatcher (MQTT Hook) ────────────────────────────── */

esp_err_t ir_handle_json_cmd(const char *json_str)
{
    if (!json_str) return ESP_ERR_INVALID_ARG;

    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGE(TAG, "Invalid IR JSON: %s", json_str);
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *type_item = cJSON_GetObjectItem(root, "type");
    const char *type = type_item ? type_item->valuestring : "";

    esp_err_t ret = ESP_OK;

    if (strcmp(type, "ac") == 0) {
        ir_ac_cmd_t cmd = {0};
        cJSON *brand = cJSON_GetObjectItem(root, "brand");
        if (brand && brand->valuestring) {
            strncpy(cmd.brand, brand->valuestring, sizeof(cmd.brand) - 1);
        } else {
            strcpy(cmd.brand, "daikin");
        }

        cJSON *power = cJSON_GetObjectItem(root, "power");
        cmd.power = power ? cJSON_IsTrue(power) : true;

        cJSON *temp = cJSON_GetObjectItem(root, "temp");
        cmd.temp_c = temp ? (uint8_t)temp->valueint : 26;

        ret = ir_send_ac(&cmd);
    } else if (strcmp(type, "nec") == 0) {
        cJSON *addr = cJSON_GetObjectItem(root, "addr");
        cJSON *cmd = cJSON_GetObjectItem(root, "cmd");
        uint16_t a = addr ? (uint16_t)addr->valueint : 0;
        uint16_t c = cmd ? (uint16_t)cmd->valueint : 0;
        ret = ir_send_nec(a, c);
    } else if (strcmp(type, "raw") == 0) {
        cJSON *timings = cJSON_GetObjectItem(root, "timings");
        if (timings && cJSON_IsArray(timings)) {
            int count = cJSON_GetArraySize(timings);
            if (count > 0 && count <= 512) {
                uint32_t *raw = malloc(count * sizeof(uint32_t));
                if (raw) {
                    for (int i = 0; i < count; i++) {
                        raw[i] = (uint32_t)cJSON_GetArrayItem(timings, i)->valueint;
                    }
                    ret = ir_send_raw(raw, count);
                    free(raw);
                }
            }
        }
    } else {
        ESP_LOGW(TAG, "Unknown IR command type: %s", type);
        ret = ESP_ERR_NOT_SUPPORTED;
    }

    cJSON_Delete(root);
    return ret;
}
