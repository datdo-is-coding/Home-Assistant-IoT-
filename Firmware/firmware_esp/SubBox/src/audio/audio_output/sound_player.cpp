/**
 * @file sound_player.cpp
 * @brief Zero-Latency Acoustic Feedback & I2S Speaker Driver for SubBox Implementation
 */

#include "sound_player.h"
#include "board_pins.h"
#include "config/subbox_config.h"

#include <cmath>
#include <cstring>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/i2s_std.h"

static const char* TAG = "SOUND_PLAYER";

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define SOUND_SAMPLE_RATE       SUBBOX_AUDIO_SAMPLE_RATE /* 16000 Hz */
#define SOUND_DMA_FRAME_SAMPLES 256

SoundPlayer& SoundPlayer::instance() {
    static SoundPlayer s_instance;
    return s_instance;
}

SoundPlayer::SoundPlayer()
    : m_initialized(false),
      m_playing(false),
      m_i2s_handle(nullptr),
      m_queue(nullptr),
      m_task_handle(nullptr),
      m_mutex(nullptr) {
}

SoundPlayer::~SoundPlayer() {
    stop();
    if (m_task_handle) {
        vTaskDelete(static_cast<TaskHandle_t>(m_task_handle));
        m_task_handle = nullptr;
    }
    if (m_queue) {
        vQueueDelete(static_cast<QueueHandle_t>(m_queue));
        m_queue = nullptr;
    }
    if (m_i2s_handle) {
        auto handle = static_cast<i2s_chan_handle_t>(m_i2s_handle);
        i2s_channel_disable(handle);
        i2s_del_channel(handle);
        m_i2s_handle = nullptr;
    }
    if (m_mutex) {
        vSemaphoreDelete(static_cast<SemaphoreHandle_t>(m_mutex));
        m_mutex = nullptr;
    }
}

esp_err_t SoundPlayer::init() {
    if (m_initialized) return ESP_OK;

    ESP_LOGI(TAG, "Initializing SubBox I2S Speaker Driver on Pins: BCLK=%d, LRC=%d, DOUT=%d, SD=%d",
             BOARD_PIN_SPEAKER_BCLK, BOARD_PIN_SPEAKER_LRC, BOARD_PIN_SPEAKER_DOUT, BOARD_PIN_SPEAKER_SD);

    m_mutex = xSemaphoreCreateMutex();
    if (!m_mutex) return ESP_ERR_NO_MEM;

    // 1. Configure Amplifier Shutdown (SD) Pin
    gpio_config_t io_conf = {};
    io_conf.intr_type = GPIO_INTR_DISABLE;
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pin_bit_mask = (1ULL << BOARD_PIN_SPEAKER_SD);
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure SD GPIO: %s", esp_err_to_name(err));
        return err;
    }
    enableAmp(false); // Default mute to prevent idle hiss

    // 2. Configure I2S Channel for MAX98357A
    i2s_chan_config_t chan_cfg = {
        .id = I2S_NUM_1,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 4,
        .dma_frame_num = SOUND_DMA_FRAME_SAMPLES,
        .auto_clear = true,
    };

    i2s_chan_handle_t tx_handle = nullptr;
    err = i2s_new_channel(&chan_cfg, &tx_handle, nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to allocate I2S TX channel: %s", esp_err_to_name(err));
        return err;
    }
    m_i2s_handle = tx_handle;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(SOUND_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = BOARD_PIN_SPEAKER_BCLK,
            .ws   = BOARD_PIN_SPEAKER_LRC,
            .dout = BOARD_PIN_SPEAKER_DOUT,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    // Duplicate mono audio to both left & right slots so MAX98357A receives audio regardless of SD pin resistor
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH;

    err = i2s_channel_init_std_mode(tx_handle, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize I2S standard mode: %s", esp_err_to_name(err));
        return err;
    }

    err = i2s_channel_enable(tx_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable I2S channel: %s", esp_err_to_name(err));
        return err;
    }

    // 3. Create Asynchronous Playback Queue & Worker Task
    m_queue = xQueueCreate(4, sizeof(SoundType));
    if (!m_queue) {
        ESP_LOGE(TAG, "Failed to allocate sound player queue");
        return ESP_ERR_NO_MEM;
    }

    BaseType_t res = xTaskCreatePinnedToCore(
        playbackTask, "sound_player_task", 4096, this,
        configMAX_PRIORITIES - 3, (TaskHandle_t*)&m_task_handle, 1
    );
    if (res != pdPASS) {
        ESP_LOGE(TAG, "Failed to spawn sound player worker task");
        return ESP_ERR_NO_MEM;
    }

    m_initialized = true;
    ESP_LOGI(TAG, "SubBox Sound Player initialized successfully (Acoustic feedback active).");
    return ESP_OK;
}

void SoundPlayer::enableAmp(bool enable) {
    // MAX98357A SD_MODE: Active LOW shutdown. High = Enabled, Low = Mute/Shutdown
    gpio_set_level(BOARD_PIN_SPEAKER_SD, enable ? 1 : 0);
}

void SoundPlayer::generateTone(std::vector<int16_t>& out, float freq_hz, float duration_s, float volume, float decay) {
    size_t samples = static_cast<size_t>(duration_s * SOUND_SAMPLE_RATE);
    if (samples == 0) return;

    size_t start_idx = out.size();
    out.resize(start_idx + samples);

    float angular_freq = 2.0f * (float)M_PI * freq_hz / (float)SOUND_SAMPLE_RATE;
    float decay_rate = decay / (float)samples;
    float max_ampl = volume * 28000.0f; // Scale to ~85% peak without clipping

    // Smooth 5ms attack to eliminate clicks
    size_t attack_samples = static_cast<size_t>(0.005f * SOUND_SAMPLE_RATE);
    if (attack_samples == 0) attack_samples = 1;

    for (size_t i = 0; i < samples; ++i) {
        float attack = (i < attack_samples) ? ((float)i / (float)attack_samples) : 1.0f;
        float env = attack * expf(-decay_rate * (float)i);
        float wave = sinf(angular_freq * (float)i);
        out[start_idx + i] = static_cast<int16_t>(wave * env * max_ampl);
    }
}

void SoundPlayer::generateSilence(std::vector<int16_t>& out, float duration_s) {
    size_t samples = static_cast<size_t>(duration_s * SOUND_SAMPLE_RATE);
    size_t start_idx = out.size();
    out.resize(start_idx + samples, 0);
}

bool SoundPlayer::play(SoundType type) {
    if (!m_initialized || !m_queue) return false;
    return (xQueueSend(static_cast<QueueHandle_t>(m_queue), &type, 0) == pdTRUE);
}

bool SoundPlayer::isPlaying() const {
    return m_playing;
}

void SoundPlayer::stop() {
    m_playing = false;
    enableAmp(false);
}

void SoundPlayer::playRawInternal(const int16_t* pcm, size_t samples) {
    if (!pcm || samples == 0 || !m_i2s_handle) return;

    auto tx_handle = static_cast<i2s_chan_handle_t>(m_i2s_handle);

    m_playing = true;
    enableAmp(true);
    vTaskDelay(pdMS_TO_TICKS(10)); // Allow amp to wake cleanly

    size_t bytes_to_write = samples * sizeof(int16_t);
    size_t bytes_written = 0;

    i2s_channel_write(tx_handle, pcm, bytes_to_write, &bytes_written, pdMS_TO_TICKS(2000));

    // Pad with brief silence to let DMA ringbuffer drain completely
    int16_t silence_buf[SOUND_DMA_FRAME_SAMPLES] = {0};
    size_t pad_written = 0;
    i2s_channel_write(tx_handle, silence_buf, sizeof(silence_buf), &pad_written, pdMS_TO_TICKS(100));

    vTaskDelay(pdMS_TO_TICKS(30)); // Settle time before muting amp
    enableAmp(false);
    m_playing = false;
}

bool SoundPlayer::playPcm(const int16_t* pcm, size_t samples) {
    if (!m_initialized || !pcm || samples == 0) return false;

    auto mutex = static_cast<SemaphoreHandle_t>(m_mutex);
    if (xSemaphoreTake(mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }

    playRawInternal(pcm, samples);
    xSemaphoreGive(mutex);
    return true;
}

void SoundPlayer::playbackTask(void* pvParameters) {
    auto* self = static_cast<SoundPlayer*>(pvParameters);
    SoundType type;
    std::vector<int16_t> buffer;
    buffer.reserve(SOUND_SAMPLE_RATE); // 1s buffer

    ESP_LOGI(TAG, "SubBox Sound Player Task started on Core 1.");

    while (1) {
        if (xQueueReceive(static_cast<QueueHandle_t>(self->m_queue), &type, portMAX_DELAY) == pdTRUE) {
            auto mutex = static_cast<SemaphoreHandle_t>(self->m_mutex);
            if (xSemaphoreTake(mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
                continue;
            }

            buffer.clear();

            switch (type) {
                case SoundType::WAKE: {
                    // "Hi ESP" wake sound: crisp, harmonic, bright double-tone (A5 -> E6)
                    self->generateTone(buffer, 880.0f,  0.060f, 0.45f, 4.0f);
                    self->generateTone(buffer, 1318.5f, 0.090f, 0.50f, 3.5f);
                    break;
                }

                case SoundType::SUCCESS: {
                    // Command confirmed: pleasant ascending major triad (D5 -> G5 -> D6)
                    self->generateTone(buffer, 587.33f,  0.075f, 0.45f, 3.5f);
                    self->generateTone(buffer, 783.99f,  0.080f, 0.48f, 3.2f);
                    self->generateTone(buffer, 1174.66f, 0.160f, 0.52f, 2.5f);
                    break;
                }

                case SoundType::ERROR: {
                    // Command unrecognized or failed: polite descending double blip (A4 -> E4)
                    self->generateTone(buffer, 440.0f, 0.080f, 0.45f, 4.0f);
                    self->generateSilence(buffer, 0.035f);
                    self->generateTone(buffer, 329.63f, 0.140f, 0.45f, 3.2f);
                    break;
                }

                case SoundType::BOOTUP: {
                    // Boot ready chime: welcoming C-major chord progression
                    self->generateTone(buffer, 523.25f,  0.090f, 0.40f, 3.0f);
                    self->generateTone(buffer, 659.25f,  0.090f, 0.42f, 3.0f);
                    self->generateTone(buffer, 783.99f,  0.100f, 0.45f, 2.8f);
                    self->generateTone(buffer, 1046.50f, 0.220f, 0.50f, 2.0f);
                    break;
                }
            }

            if (!buffer.empty()) {
                self->playRawInternal(buffer.data(), buffer.size());
            }

            xSemaphoreGive(mutex);
        }
    }
}
