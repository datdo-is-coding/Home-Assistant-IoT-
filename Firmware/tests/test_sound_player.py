"""Compile real SoundPlayer and model its I2S backlog at amplifier shutdown."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'


class SoundPlayerTest(unittest.TestCase):
    def test_pcm_stream_reports_writes_and_drains_before_amp_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'host.h').write_text(r'''#pragma once
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
using esp_err_t = int;
constexpr int ESP_OK = 0, ESP_ERR_NO_MEM = -1;
inline const char* esp_err_to_name(int) { return "test error"; }
#define ESP_LOGI(...)
#define ESP_LOGW(...)
#define ESP_LOGE(...)
#define BOARD_PIN_SPEAKER_BCLK 1
#define BOARD_PIN_SPEAKER_LRC 2
#define BOARD_PIN_SPEAKER_DOUT 3
#define BOARD_PIN_SPEAKER_SD 4
#define SUBBOX_AUDIO_SAMPLE_RATE 16000
#define pdMS_TO_TICKS(ms) ((ms) / 10)
constexpr int pdTRUE = 1, pdPASS = 1, configMAX_PRIORITIES = 25;
using BaseType_t = int;
using TaskHandle_t = void*;
using QueueHandle_t = void*;
using SemaphoreHandle_t = void*;
inline bool mutex_available = true, amplifier_on = false, speech_cut_off = false;
inline std::deque<int16_t> pending;
inline size_t dma_capacity = 0, played_speech = 0;
inline size_t next_write_limit = std::numeric_limits<size_t>::max();
inline int next_write_error = ESP_OK, sample_rate = 0;
inline unsigned last_write_timeout = 0;
inline void transmit(size_t samples) {
    while (samples-- && !pending.empty()) {
        if (pending.front() != 0) {
            if (amplifier_on) ++played_speech;
            else speech_cut_off = true;
        }
        pending.pop_front();
    }
}
inline void vTaskDelay(unsigned ticks) { transmit(size_t(sample_rate) * ticks * 10 / 1000); }
inline void vTaskDelete(TaskHandle_t) {}
inline int xTaskCreatePinnedToCore(void (*)(void*), const char*, unsigned, void*,
                                   unsigned, TaskHandle_t* task, int) {
    *task = reinterpret_cast<void*>(1); return pdPASS;
}
inline QueueHandle_t xQueueCreate(unsigned, unsigned) { return reinterpret_cast<void*>(1); }
inline int xQueueSend(QueueHandle_t, const void*, unsigned) { return pdTRUE; }
inline int xQueueReceive(QueueHandle_t, void*, unsigned) { return 0; }
inline void vQueueDelete(QueueHandle_t) {}
inline SemaphoreHandle_t xSemaphoreCreateMutex() { return reinterpret_cast<void*>(1); }
inline int xSemaphoreTake(SemaphoreHandle_t, unsigned) { return mutex_available; }
inline int xSemaphoreGive(SemaphoreHandle_t) { return pdTRUE; }
inline void vSemaphoreDelete(SemaphoreHandle_t) {}
inline int64_t esp_timer_get_time() { return 1; }
constexpr int GPIO_INTR_DISABLE = 0, GPIO_MODE_OUTPUT = 1;
constexpr int GPIO_PULLDOWN_DISABLE = 0, GPIO_PULLUP_DISABLE = 0;
struct gpio_config_t {
    int intr_type, mode;
    uint64_t pin_bit_mask;
    int pull_down_en, pull_up_en;
};
inline int gpio_config(const gpio_config_t*) { return ESP_OK; }
inline int gpio_set_level(int, int enabled) {
    if (!enabled && amplifier_on) {
        speech_cut_off |= std::any_of(pending.begin(), pending.end(),
                                      [](int16_t sample) { return sample != 0; });
    }
    amplifier_on = enabled; return ESP_OK;
}
using i2s_chan_handle_t = void*;
constexpr int I2S_NUM_1 = 1, I2S_ROLE_MASTER = 1, I2S_GPIO_UNUSED = -1;
constexpr int I2S_DATA_BIT_WIDTH_16BIT = 16, I2S_SLOT_MODE_MONO = 1, I2S_STD_SLOT_BOTH = 3;
struct i2s_chan_config_t { int id, role, dma_desc_num, dma_frame_num; bool auto_clear; };
struct ClockConfig { int sample_rate; };
struct SlotConfig { int width, mode, slot_mask; };
#define I2S_STD_CLK_DEFAULT_CONFIG(rate) ClockConfig{rate}
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(width, mode) SlotConfig{width, mode, 0}
struct i2s_std_config_t {
    ClockConfig clk_cfg;
    SlotConfig slot_cfg;
    struct {
        int mclk, bclk, ws, dout, din;
        struct { bool mclk_inv, bclk_inv, ws_inv; } invert_flags;
    } gpio_cfg;
};
inline int i2s_new_channel(const i2s_chan_config_t* cfg, i2s_chan_handle_t* tx, void*) {
    dma_capacity = cfg->dma_desc_num * cfg->dma_frame_num;
    *tx = reinterpret_cast<void*>(1); return ESP_OK;
}
inline int i2s_channel_init_std_mode(i2s_chan_handle_t, const i2s_std_config_t* cfg) {
    sample_rate = cfg->clk_cfg.sample_rate; return ESP_OK;
}
inline int i2s_channel_enable(i2s_chan_handle_t) { return ESP_OK; }
inline int i2s_channel_disable(i2s_chan_handle_t) { return ESP_OK; }
inline int i2s_del_channel(i2s_chan_handle_t) { return ESP_OK; }
inline int i2s_channel_write(i2s_chan_handle_t, const void* data, size_t bytes,
                             size_t* written, unsigned timeout_ms) {
    last_write_timeout = timeout_ms;
    const int error = next_write_error;
    next_write_error = ESP_OK;
    *written = error == ESP_OK ? std::min(bytes, next_write_limit) : 0;
    next_write_limit = std::numeric_limits<size_t>::max();
    const auto* pcm = static_cast<const int16_t*>(data);
    const size_t samples = *written / sizeof(int16_t);
    // A blocking write transmits old samples when the configured DMA queue fills.
    pending.insert(pending.end(), pcm, pcm + samples);
    if (pending.size() > dma_capacity) transmit(pending.size() - dma_capacity);
    return error;
}
''')
            for name in (
                'esp_err.h', 'esp_log.h', 'esp_timer.h', 'board_pins.h',
                'config/subbox_config.h', 'freertos/FreeRTOS.h', 'freertos/task.h',
                'freertos/queue.h', 'freertos/semphr.h', 'driver/gpio.h', 'driver/i2s_std.h',
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "host.h"\n')
            (root / 'check.cpp').write_text(r'''
#include "audio/audio_output/sound_player.h"
#include "host.h"
int main() {
    auto& player = SoundPlayer::instance();
    assert(!player.finishPcmStream());
    assert(!player.startPcmStream());
    assert(!player.isPlaying() && !amplifier_on);
    assert(player.init() == ESP_OK);
    mutex_available = false;
    assert(!player.startPcmStream());
    assert(!player.isPlaying() && !amplifier_on);
    mutex_available = true;
    assert(player.startPcmStream());
    assert(player.isPlaying() && amplifier_on);

    int16_t speech[256];
    std::fill(std::begin(speech), std::end(speech), 1234);
    next_write_limit = sizeof(speech) / 2;
    assert(!player.streamPcmChunk(speech, 256));
    assert(last_write_timeout == 500);
    next_write_error = -1;
    assert(!player.streamPcmChunk(speech, 256));
    for (int i = 0; i < 4; ++i) assert(player.streamPcmChunk(speech, 256));
    const size_t accepted_speech = 128 + 4 * 256;
    assert(pending.size() == dma_capacity && played_speech < accepted_speech);
    assert(player.finishPcmStream());
    assert(last_write_timeout == 100);
    assert(played_speech == accepted_speech && !speech_cut_off);
    assert(!amplifier_on && !player.isPlaying());
    assert(player.startPcmStream());
    next_write_limit = 0;
    assert(!player.finishPcmStream());
    assert(!amplifier_on && !player.isPlaying());
    assert(player.startPcmStream());
    next_write_error = -1;
    assert(!player.finishPcmStream());
    assert(player.startPcmStream());
    mutex_available = false;
    assert(!player.finishPcmStream());
    assert(!amplifier_on && !player.isPlaying());
}
''')
            subprocess.run([
                'g++', '-std=c++17', '-I', str(root), '-I', str(SRC),
                str(root / 'check.cpp'), str(SRC / 'audio/audio_output/sound_player.cpp'),
                '-o', str(root / 'check'),
            ], check=True, timeout=30)
            subprocess.run([str(root / 'check')], check=True, timeout=5)
