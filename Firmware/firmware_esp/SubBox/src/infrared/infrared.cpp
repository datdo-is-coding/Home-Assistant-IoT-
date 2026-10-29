#include "infrared.h"
#include "ir_limits.h"
#include "config/board_pins.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_rx.h"
#include "driver/rmt_encoder.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "mbedtls/base64.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <atomic>
#include <cstring>
#include <cstdio>
#include <cmath>

namespace {
constexpr size_t kRxSymbols = 512;
StaticSemaphore_t callback_storage;
SemaphoreHandle_t callback_mutex;
StaticTask_t task_storage;
TaskHandle_t task_handle;
std::atomic<void*> active_owner{nullptr};
IrReply reply_callback;
std::atomic<uint32_t> session_generation{0};
std::atomic<bool> busy{false}, received{false};
std::atomic<size_t> received_symbols{0};
struct Job {
    void* owner;
    uint32_t generation;
    char id[28];
    bool learn;
    uint32_t frequency;
    uint16_t* ticks;
    size_t count;
    int64_t created, deadline;
} job{};
char prepared_id[28]{};
int64_t prepared_until = 0;

void direct_reply(void* owner, uint32_t generation, const char* id, const char* extra) {
    char text[220];
    snprintf(text, sizeof(text), "{\"type\":\"ir_result\",\"id\":\"%s\",%s}", id, extra);
    xSemaphoreTake(callback_mutex, portMAX_DELAY);
    if (active_owner.load() == owner && generation == session_generation.load() && reply_callback)
        reply_callback(owner, text, strlen(text));
    xSemaphoreGive(callback_mutex);
}
bool current() { return active_owner.load() == job.owner && job.generation == session_generation.load(); }
void respond(bool ok, const char* error, const uint16_t* ticks = nullptr, size_t count = 0) {
    auto* output = static_cast<char*>(heap_caps_malloc(3600, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!output) return;
    if (ok && ticks) {
        // Encode separately: the maximum learned message remains below 4 KiB.
        auto* b64 = static_cast<unsigned char*>(heap_caps_malloc(2736, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        size_t length = 0;
        if (!b64 || mbedtls_base64_encode(b64, 2736, &length,
                reinterpret_cast<const unsigned char*>(ticks), count * 2) != 0) {
            heap_caps_free(b64); heap_caps_free(output); return;
        }
        snprintf(output, 3600, "{\"type\":\"ir_result\",\"id\":\"%s\",\"ok\":true,\"data\":\"%s\"}", job.id, b64);
        heap_caps_free(b64);
    } else {
        snprintf(output, 3600, "{\"type\":\"ir_result\",\"id\":\"%s\",\"ok\":%s,\"error\":\"%s\"}",
                 job.id, ok ? "true" : "false", error ? error : "");
    }
    xSemaphoreTake(callback_mutex, portMAX_DELAY);
    if (active_owner == job.owner && reply_callback && current()) reply_callback(active_owner, output, strlen(output));
    xSemaphoreGive(callback_mutex);
    heap_caps_free(output);
}

esp_err_t transmit() {
    rmt_channel_handle_t channel = nullptr;
    rmt_encoder_handle_t encoder = nullptr;
    const size_t capacity = job.count * 4 + 2;
    auto* symbols = static_cast<rmt_symbol_word_t*>(heap_caps_calloc(capacity, sizeof(rmt_symbol_word_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!symbols) return ESP_ERR_NO_MEM;
    size_t halves = 0;
    for (size_t i = 0; i < job.count; ++i) {
        uint32_t remaining = uint32_t(job.ticks[i]) * 10;
        while (remaining) {
            const uint32_t part = remaining > 32767 ? 32767 : remaining;
            auto& symbol = symbols[halves / 2];
            if (halves % 2) { symbol.level1 = i % 2 ? 0 : 1; symbol.duration1 = part; }
            else { symbol.level0 = i % 2 ? 0 : 1; symbol.duration0 = part; }
            ++halves; remaining -= part;
        }
    }
    if (halves % 2) { symbols[halves / 2].level1 = 0; symbols[halves / 2].duration1 = 1; ++halves; }
    rmt_tx_channel_config_t cfg{};
    cfg.gpio_num = BOARD_PIN_IR_TX; cfg.clk_src = RMT_CLK_SRC_DEFAULT;
    cfg.resolution_hz = 1000000; cfg.mem_block_symbols = 48; cfg.trans_queue_depth = 1;
    esp_err_t error = rmt_new_tx_channel(&cfg, &channel);
    rmt_copy_encoder_config_t enc{};
    if (error == ESP_OK) error = rmt_new_copy_encoder(&enc, &encoder);
    rmt_carrier_config_t carrier{}; carrier.frequency_hz = job.frequency; carrier.duty_cycle = 0.25f;
    if (error == ESP_OK) error = rmt_apply_carrier(channel, &carrier);
    bool enabled = false;
    if (error == ESP_OK) { error = rmt_enable(channel); enabled = error == ESP_OK; }
    rmt_transmit_config_t tx{}; tx.flags.eot_level = 0;
    if (error == ESP_OK && (!current() || esp_timer_get_time() > job.deadline)) error = ESP_ERR_INVALID_STATE;
    if (error == ESP_OK) error = rmt_transmit(channel, encoder, symbols, halves / 2 * sizeof(rmt_symbol_word_t), &tx);
    if (error == ESP_OK) error = rmt_tx_wait_all_done(channel, 1500);
    if (enabled) rmt_disable(channel);
    if (encoder) rmt_del_encoder(encoder);
    if (channel) rmt_del_channel(channel);
    gpio_set_level(BOARD_PIN_IR_TX, 0);
    heap_caps_free(symbols);
    return error;
}

bool rx_done(rmt_channel_handle_t, const rmt_rx_done_event_data_t* data, void*) {
    received_symbols.store(data->num_symbols);
    received.store(true);
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(task_handle, &wake);
    return wake == pdTRUE;
}

void learn() {
    auto* symbols = static_cast<rmt_symbol_word_t*>(heap_caps_calloc(kRxSymbols, sizeof(rmt_symbol_word_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA));
    auto* ticks = static_cast<uint16_t*>(heap_caps_malloc(1024 * 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!symbols || !ticks) { heap_caps_free(symbols); heap_caps_free(ticks); respond(false, "no_memory"); return; }
    rmt_channel_handle_t channel = nullptr;
    rmt_rx_channel_config_t cfg{};
    cfg.gpio_num = BOARD_PIN_IR_RX; cfg.clk_src = RMT_CLK_SRC_DEFAULT;
    cfg.resolution_hz = 500000; cfg.mem_block_symbols = kRxSymbols; cfg.flags.with_dma = true;
    received.store(false); received_symbols.store(0);
    esp_err_t error = rmt_new_rx_channel(&cfg, &channel);
    rmt_rx_event_callbacks_t callbacks{}; callbacks.on_recv_done = rx_done;
    if (error == ESP_OK) error = rmt_rx_register_event_callbacks(channel, &callbacks, nullptr);
    bool enabled = false;
    if (error == ESP_OK) { error = rmt_enable(channel); enabled = error == ESP_OK; }
    gpio_pullup_en(BOARD_PIN_IR_RX);
    rmt_receive_config_t rx{}; rx.signal_range_min_ns = 80000; rx.signal_range_max_ns = 40000000;
    if (error == ESP_OK) error = rmt_receive(channel, symbols, kRxSymbols * sizeof(rmt_symbol_word_t), &rx);
    const int64_t deadline = esp_timer_get_time() + 8000000;
    while (error == ESP_OK && !received.load() && current() && esp_timer_get_time() < deadline)
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
    if (enabled) rmt_disable(channel);
    if (channel) rmt_del_channel(channel);
    size_t count = 0;
    bool started = false, valid = received.load() && current() && received_symbols.load() < kRxSymbols;
    for (size_t i = 0; valid && i < received_symbols.load(); ++i) {
        const uint32_t durations[2] = {symbols[i].duration0 * 2u, symbols[i].duration1 * 2u};
        const uint32_t levels[2] = {symbols[i].level0, symbols[i].level1};
        for (int h = 0; h < 2; ++h) {
            if (!durations[h]) continue;
            if (!started && levels[h] == 1) continue;
            started = true;
            if (count >= 1024 || levels[h] != (count % 2 ? 1u : 0u)) { valid = false; break; }
            ticks[count++] = (durations[h] + 5) / 10;
        }
    }
    heap_caps_free(symbols);
    valid = valid && ir_valid_wave(ticks, count, 38000);
    if (valid) respond(true, nullptr, ticks, count);
    else respond(false, error != ESP_OK ? "hardware" : (received.load() ? "invalid_capture" : "learn_timeout"));
    heap_caps_free(ticks);
}

void worker(void*) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (!busy.load()) continue;
        if (current() && esp_timer_get_time() <= job.deadline) {
            if (job.learn) learn();
            else { const esp_err_t error = transmit(); ESP_LOGI("SUBBOX_IR", "TX id=%s carrier=%lu pulses=%u result=%s", job.id, static_cast<unsigned long>(job.frequency), static_cast<unsigned>(job.count), esp_err_to_name(error)); respond(error == ESP_OK, error == ESP_OK ? nullptr : "transmit_failed"); }
        }
        heap_caps_free(job.ticks); job.ticks = nullptr;
        busy.store(false);
    }
}
}

bool infrared_bind(void* owner, IrReply callback) {
    if (!callback_mutex) callback_mutex = xSemaphoreCreateMutexStatic(&callback_storage);
    if (!task_handle) {
        auto* stack = static_cast<StackType_t*>(heap_caps_malloc(6144, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (!stack) return false;
        task_handle = xTaskCreateStaticPinnedToCore(worker, "subbox_ir", 6144, nullptr, 1, stack, &task_storage, 0);
        if (!task_handle) { heap_caps_free(stack); return false; }
    }
    xSemaphoreTake(callback_mutex, portMAX_DELAY);
    active_owner = owner; reply_callback = callback;
    xSemaphoreGive(callback_mutex);
    return true;
}
void infrared_session(void* owner, uint32_t generation) {
    if (!callback_mutex) return;
    xSemaphoreTake(callback_mutex, portMAX_DELAY);
    if (active_owner == owner) { session_generation.store(generation); prepared_id[0] = 0; }
    xSemaphoreGive(callback_mutex);
}
void infrared_unbind(void* owner) {
    if (!callback_mutex) return;
    xSemaphoreTake(callback_mutex, portMAX_DELAY);
    if (active_owner == owner) { active_owner = nullptr; reply_callback = nullptr; ++session_generation; }
    xSemaphoreGive(callback_mutex);
}
void infrared_submit(void* owner, uint32_t generation, const cJSON* message) {
    const char* id = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(message, "id"));
    const char* type = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(message, "type"));
    if (!id || strlen(id) != 27 || strncmp(id, "IR-", 3) || strspn(id + 3, "0123456789abcdef") != 24 || !type) return;
    if (active_owner.load() != owner || generation != session_generation.load()) return;
    const bool receiver_enabled = BOARD_IR_RX_ENABLED || cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(message,"receiver_enabled"));
    if (!strcmp(type, "ir_learn") && !receiver_enabled) { direct_reply(owner,generation,id,"\"ok\":false,\"error\":\"receiver_unavailable\""); return; }
    if (!strcmp(type, "ir_prepare")) {
        if (busy.load()) { direct_reply(owner,generation,id,"\"ok\":false,\"error\":\"busy\""); return; }
        memcpy(prepared_id,id,28);
        const int64_t mono = esp_timer_get_time() / 1000;
        prepared_until = mono + 2000;
        char extra[96]; snprintf(extra,sizeof(extra),"\"ok\":true,\"mono_ms\":%lld", static_cast<long long>(mono));
        direct_reply(owner,generation,id,extra); return;
    }
    const char* nonce = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(message,"prepare_id"));
    const cJSON* deadline = cJSON_GetObjectItemCaseSensitive(message,"deadline_ms");
    if (!nonce || strcmp(nonce,prepared_id) || !prepared_id[0] || !cJSON_IsNumber(deadline) ||
        deadline->valuedouble != static_cast<double>(prepared_until) || esp_timer_get_time()/1000 > prepared_until) {
        direct_reply(owner,generation,id,"\"ok\":false,\"error\":\"expired\""); return;
    }
    prepared_id[0] = 0;

    if (busy.exchange(true)) return; // Gateway serializes operations and times out without resending.
    job = {}; job.owner = owner; job.generation = generation; job.created = esp_timer_get_time(); job.deadline = prepared_until * 1000;
    memcpy(job.id, id, 28); job.learn = !strcmp(type, "ir_learn");
    if (!job.learn) {
        const cJSON* frequency = cJSON_GetObjectItemCaseSensitive(message, "frequency");
        const char* encoded = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(message, "data"));
        if (!cJSON_IsNumber(frequency) || !std::isfinite(frequency->valuedouble) || frequency->valuedouble != frequency->valueint || !encoded || strlen(encoded) > 2732) {
            respond(false, "invalid_code"); busy.store(false); return;
        }
        job.frequency = frequency->valueint;
        job.ticks = static_cast<uint16_t*>(heap_caps_malloc(2048, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        size_t bytes = 0;
        bool valid = job.ticks && !mbedtls_base64_decode(reinterpret_cast<unsigned char*>(job.ticks), 2048, &bytes,
            reinterpret_cast<const unsigned char*>(encoded), strlen(encoded)) && bytes % 2 == 0;
        job.count = bytes / 2;
        valid = valid && ir_valid_wave(job.ticks, job.count, job.frequency);
        if (!valid) { respond(false, "invalid_code"); heap_caps_free(job.ticks); job.ticks = nullptr; busy.store(false); return; }
    }
    xTaskNotifyGive(task_handle);
}
