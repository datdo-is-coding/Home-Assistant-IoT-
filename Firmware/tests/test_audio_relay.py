"""Run the real SubBox PCM buffer/manager on the host without ESP hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'


class AudioRelayTest(unittest.TestCase):
    def test_pcm_is_forwarded_without_local_transcript_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'freertos').mkdir()
            (root / 'audio_output').mkdir()
            stubs = {
                'audio_output/sound_player.h': '#pragma once\nenum class SoundType { WAKE, SUCCESS, ERROR, BOOTUP };\nclass SoundPlayer { public: static SoundPlayer& instance() { static SoundPlayer s; return s; } bool play(SoundType) { return true; } };\n',
                'esp_heap_caps.h': '#pragma once\n#include <cstdlib>\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\ninline void* heap_caps_malloc(size_t n, int) { return malloc(n); }\n',
                'esp_log.h': '#pragma once\n#define ESP_LOGI(...)\n#define ESP_LOGW(...)\n#define ESP_LOGE(...)\n',
                'esp_timer.h': '#pragma once\n#include <cstdint>\ninline int64_t esp_timer_get_time() { return 1000000; }\n',
                'freertos/FreeRTOS.h': '#pragma once\n#define pdMS_TO_TICKS(n) (n)\n',
                'freertos/task.h': '#pragma once\ninline void vTaskDelay(int) {}\ninline void taskYIELD() {}\n',
            }
            for name, content in stubs.items():
                (root / name).write_text(content)
            (root / 'check.cpp').write_text(r'''
#include <cassert>
#include <cstring>
#include <vector>
#include "audio/audio_manager/audio_manager.h"

class Remote : public ASREngine {
public:
    bool available = true;
    bool accept_pcm = true;
    bool final = false;
    int starts = 0, stops = 0, cancels = 0;
    std::string source;
    std::vector<int16_t> received;
    bool init() override { return true; }
    bool start() override { ++starts; final = false; return available; }
    void setSourceNodeId(const char* id) override { source = id; }
    void stop() override { ++stops; final = true; }
    void cancel() override { ++cancels; reset(); }
    bool feedAudio(const int16_t* p, size_t n) override {
        if (!accept_pcm) return false;
        received.insert(received.end(), p, p+n); return true;
    }
    bool hasPartialResult() const override { return false; }
    bool hasFinalResult() const override { return final; }
    const char* getPartialResult() const override { return ""; }
    const char* getFinalResult() const override { return "bật đèn"; }
    void reset() override { final = false; }
};

int main() {
    auto remote = std::make_shared<Remote>();
    AudioManager manager(nullptr, remote);
    manager.init();
    int local_commands = 0;
    manager.registerUtteranceCallback([&](const auto&, const auto&) { ++local_commands; });
    AudioPacket packet{};
    strcpy(packet.source_node_id, "AB123");
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_START;
    manager.ingestAudioPacket(packet);
    manager.ingestAudioPacket(packet); // repeated START must not discard/restart
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK;
    int16_t pcm[200];
    for (int i=0; i<200; ++i) pcm[i] = i+2000;
    packet.payload_len = sizeof(pcm);
    memcpy(packet.payload, pcm, sizeof(pcm));
    manager.ingestAudioPacket(packet);
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_END;
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(remote->starts == 1 && remote->stops == 1);
    assert(remote->source == "AB123");
    assert(remote->received == std::vector<int16_t>(pcm, pcm+200));
    assert(local_commands == 0 && "Gateway transcript must never execute locally");
    assert(manager.getActiveSourceNodeId().empty());
    manager.process();
    assert(remote->starts == 1); // no stale buffered speech replay

    remote->available = false;
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_START;
    packet.payload_len = 0;
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(manager.getActiveSourceNodeId().empty());
    assert(local_commands == 0); // disconnect must not fabricate a fallback command

    remote->available = true;
    remote->accept_pcm = false;
    manager.ingestAudioPacket(packet);
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK;
    packet.payload_len = sizeof(pcm);
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(local_commands == 0);
    assert(manager.getActiveSourceNodeId().empty());
    assert(remote->cancels == 1 && remote->stops == 1);
}
''')
            subprocess.run(['g++', '-std=c++17', '-pthread', '-I', str(root), '-I', str(SRC),
                            str(root / 'check.cpp'),
                            str(SRC / 'audio/audio_manager/audio_manager.cpp'),
                            str(SRC / 'audio/audio_buffer/audio_ring_buffer.cpp'),
                            '-o', str(root / 'check')], check=True)
            subprocess.run([str(root / 'check')], check=True)


if __name__ == '__main__':
    unittest.main()
