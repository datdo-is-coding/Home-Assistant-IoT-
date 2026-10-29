"""Run the real SubBox PCM buffer/manager on the host without ESP hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'


class AudioRelayTest(unittest.TestCase):
    def test_pcm_is_forwarded_and_final_utterance_emitted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'freertos').mkdir()
            (root / 'audio_output').mkdir()
            stubs = {
                'audio_output/sound_player.h': '#pragma once\nenum class SoundType { WAKE, SUCCESS, ERROR, BOOTUP };\ninline int wake_sounds=0;\nclass SoundPlayer { public: static SoundPlayer& instance() { static SoundPlayer s; return s; } bool play(SoundType t) { if(t==SoundType::WAKE) ++wake_sounds; return true; } };\n',
                'esp_heap_caps.h': '#pragma once\n#include <cstdlib>\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\ninline void* heap_caps_malloc(size_t n, int) { return malloc(n); }\n',
                'esp_log.h': '#pragma once\n#define ESP_LOGI(...)\n#define ESP_LOGW(...)\n#define ESP_LOGE(...)\n',
                'esp_timer.h': '#pragma once\n#include <cstdint>\ninline int64_t audio_test_time = 1000000; inline int64_t esp_timer_get_time() { return audio_test_time; }\n',
                'freertos/FreeRTOS.h': '#pragma once\n#define pdMS_TO_TICKS(n) (n)\n',
                'freertos/task.h': '#pragma once\ninline void vTaskDelay(int) {}\ninline void taskYIELD() {}\n',
            }
            for name, content in stubs.items():
                (root / name).write_text(content)
            (root / 'check.cpp').write_text(r'''
#include <cassert>
#include <cstring>
#include <vector>
#include "esp_timer.h"
#include "audio_output/sound_player.h"
#include "audio/audio_manager/audio_manager.h"

class Remote : public ASREngine {
public:
    bool available = true;
    bool accept_pcm = true;
    bool final = false;
    int starts = 0, stops = 0, cancels = 0;
    std::string source, result = "bật đèn";
    std::vector<int16_t> received;
    bool init() override { return true; }
    bool start() override { ++starts; final = false; result = "bật đèn"; return available; }
    void setSourceNodeId(const char* id) override { source = id; }
    void stop() override { ++stops; final = true; }
    void cancel() override { ++cancels; reset(); result = "__KWS_AUDIO_ERROR__"; }
    bool feedAudio(const int16_t* p, size_t n) override {
        if (!accept_pcm) return false;
        received.insert(received.end(), p, p+n); return true;
    }
    bool hasPartialResult() const override { return false; }
    bool hasFinalResult() const override { return final; }
    const char* getPartialResult() const override { return ""; }
    const char* getFinalResult() const override { return result.c_str(); }
    void reset() override { final = false; }
};

int main() {
    auto remote = std::make_shared<Remote>();
    AudioManager manager(nullptr, remote);
    manager.init();
    int local_commands = 0;
    std::string utterance_source, utterance_text;
    manager.registerUtteranceCallback([&](const auto& origin, const auto& text) {
        ++local_commands; utterance_source = origin; utterance_text = text;
    });
    AudioPacket packet{};
    strcpy(packet.source_node_id, "AB123");
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_START;
    manager.ingestAudioPacket(packet);
    manager.ingestAudioPacket(packet); // repeated START must not discard/restart
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK;
    packet.sequence_num = 1;
    int16_t pcm[200];
    for (int i=0; i<200; ++i) pcm[i] = i+2000;
    packet.payload_len = sizeof(pcm);
    memcpy(packet.payload, pcm, sizeof(pcm));
    manager.ingestAudioPacket(packet);
    strcpy(packet.source_node_id, "AB_OTHER");
    manager.ingestAudioPacket(packet); // another mic heard the same wake word
    strcpy(packet.source_node_id, "AB123");
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_END;
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(remote->starts == 1 && remote->stops == 1);
    assert(remote->source == "AB123");
    assert(remote->received == std::vector<int16_t>(pcm, pcm+200));
    assert(local_commands == 1 && utterance_source == "AB123" && utterance_text == "bật đèn");
    assert(manager.getActiveSourceNodeId().empty());
    manager.process();
    assert(remote->starts == 1); // no stale buffered speech replay

    remote->available = false;
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_START;
    packet.payload_len = 0;
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(manager.getActiveSourceNodeId().empty());
    assert(local_commands == 1); // start failure must not fabricate an utterance

    remote->available = true;
    remote->accept_pcm = false;
    manager.ingestAudioPacket(packet);
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK;
    packet.sequence_num = 1;
    packet.payload_len = sizeof(pcm);
    manager.ingestAudioPacket(packet);
    manager.process();
    assert(local_commands == 2 && utterance_text == "__KWS_AUDIO_ERROR__");
    assert(manager.getActiveSourceNodeId().empty());
    assert(remote->cancels == 1 && remote->stops == 1);
    remote->accept_pcm = true;
    auto start = [&] {
        packet.msg_type = AUDIO_MSG_TYPE_STREAM_START; packet.payload_len = 0; packet.sequence_num = 0;
        manager.ingestAudioPacket(packet);
        packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK; packet.payload_len = sizeof(pcm);
    };
    auto end = [&] {
        packet.msg_type = AUDIO_MSG_TYPE_STREAM_END; packet.payload_len = 0;
        manager.ingestAudioPacket(packet); manager.process();
    };
    // Dropping a room suffix must cancel the whole sentence, not use its prefix.
    start(); packet.sequence_num = 1; manager.ingestAudioPacket(packet);
    packet.sequence_num = 3; manager.ingestAudioPacket(packet); end();
    assert(utterance_text == "__KWS_AUDIO_ERROR__" && remote->stops == 1);
    // Missing final chunk is detectable from STREAM_END's last chunk sequence.
    start(); packet.sequence_num = 1; manager.ingestAudioPacket(packet);
    packet.sequence_num = 2; end();
    assert(utterance_text == "__KWS_AUDIO_ERROR__");
    // Buffer full and missing END both fail closed.
    start();
    for (int i=1; i<=340; ++i) { packet.sequence_num = i & 255; manager.ingestAudioPacket(packet); }
    end(); assert(utterance_text == "__KWS_AUDIO_ERROR__");
    start(); packet.sequence_num = 1; manager.ingestAudioPacket(packet);
    audio_test_time += 1300000; manager.process();
    assert(utterance_text == "__KWS_AUDIO_ERROR__");
    // An ordinary eight-bit sequence wrap must remain valid.
    start();
    for (int i=1; i<=260; ++i) {
        packet.sequence_num = i & 255; manager.ingestAudioPacket(packet); manager.process();
    }
    end(); assert(utterance_text == "bật đèn");
    const int count = local_commands;
    packet.msg_type = AUDIO_MSG_TYPE_STREAM_CHUNK; packet.payload_len = sizeof(pcm);
    manager.ingestAudioPacket(packet); manager.process();
    assert(local_commands == count); // no wake/start, no execution

    auto buffered = std::make_shared<Remote>();
    AudioManager deferred(nullptr, buffered, true);deferred.init();
    const int before_wake = wake_sounds;
    strcpy(packet.source_node_id,"AB_BUFFERED");packet.msg_type=AUDIO_MSG_TYPE_WAKE;
    deferred.ingestAudioPacket(packet);deferred.ingestAudioPacket(packet);deferred.process();
    assert(wake_sounds==before_wake+1 && buffered->starts==0);
    audio_test_time+=2000000;deferred.process();
    assert(deferred.getActiveSourceNodeId().empty()); // Wake alone never starts the PCM timeout.
    strcpy(packet.source_node_id,"AB_BUFFERED");packet.msg_type=AUDIO_MSG_TYPE_STREAM_START;
    packet.sequence_num=0;packet.payload_len=0;deferred.ingestAudioPacket(packet);deferred.process();
    assert(buffered->starts==0);
    assert(wake_sounds==before_wake+1); // No second chime at speech onset.
    packet.msg_type=AUDIO_MSG_TYPE_STREAM_CHUNK;packet.payload_len=sizeof(pcm);
    for(int i=1;i<=400;++i){
        packet.sequence_num=i&255;deferred.ingestAudioPacket(packet);deferred.process();
        assert(buffered->starts==0 && buffered->received.empty());
    }
    packet.msg_type=AUDIO_MSG_TYPE_STREAM_END;packet.payload_len=0;
    deferred.ingestAudioPacket(packet);deferred.process();
    assert(buffered->starts==1 && buffered->stops==1 && buffered->received.size()==80000);
    assert(buffered->source=="AB_BUFFERED");
    // Lost data must never start an upload or decode a partial command.
    packet.msg_type=AUDIO_MSG_TYPE_STREAM_START;packet.sequence_num=0;
    deferred.ingestAudioPacket(packet);
    packet.msg_type=AUDIO_MSG_TYPE_STREAM_CHUNK;packet.payload_len=sizeof(pcm);packet.sequence_num=1;
    deferred.ingestAudioPacket(packet);packet.sequence_num=3;deferred.ingestAudioPacket(packet);
    deferred.process();assert(buffered->starts==1 && buffered->cancels==1);

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
