"""Run SubBox's real C++ NLU without hardware: python Firmware/tests/test_nlu_native.py.

Requires a host g++/c++ compiler (not the Xtensa cross-compiler).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'firmware_esp/SubBox/src'
COMPILER = shutil.which('g++') or shutil.which('c++')


@unittest.skipUnless(COMPILER, 'Host C++ compiler unavailable; use g++ on a development host')
class SubBoxNLU(unittest.TestCase):
    def test_commands_negation_utf8_and_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'esp_log.h').write_text('#define ESP_LOGI(...)\n#define ESP_LOGD(...)\n#define ESP_LOGW(...)\n')
            (root / 'esp_timer.h').write_text('#include <cstdint>\nextern int64_t test_time;\ninline int64_t esp_timer_get_time() { return test_time; }\n')
            (root / 'check.cpp').write_text(r'''
#include <cassert>
#include "nlu/normalizer/vietnamese_normalizer.h"
#include "nlu/intent/intent_parser.h"
#include "nlu/context/context_manager.h"
int64_t test_time = 0;
int main() {
    auto normalize = VietnameseNormalizer::normalize;
    assert(normalize("  MỞ\tđèn! ") == "bật đèn");
    assert(normalize("ngắt quạt") == "tắt quạt");
    assert(IntentParser::parse(normalize("mở đèn")) == IntentType::TURN_ON);
    assert(IntentParser::parse(normalize("ngắt quạt")) == IntentType::TURN_OFF);
    for (const char* text : {"đừng bật đèn", "không bật quạt", "đèn đang bật không", "chưa tắt quạt"})
        assert(IntentParser::parse(normalize(text)) == IntentType::UNKNOWN);
    assert(IntentParser::parse("đèn đang bật") == IntentType::QUERY_STATE);
    ContextManager context;
    ParsedEntities entities{};
    entities.device = DeviceType::LIGHT;
    entities.room = RoomType::LIVING_ROOM;
    auto command = context.resolve("bật đèn", "A", IntentType::TURN_ON, entities);
    context.commitResolution(command);
    entities.device = DeviceType::NONE;
    entities.room = RoomType::UNSPECIFIED;
    assert(context.resolve("tắt nó", "A", IntentType::TURN_OFF, entities).is_valid);
    assert(!context.resolve("tắt nó", "B", IntentType::TURN_OFF, entities).is_valid);
    test_time = 31000000;
    assert(!context.resolve("tắt nó", "A", IntentType::TURN_OFF, entities).is_valid);
}
''', encoding='utf-8')
            executable = root / 'check.exe'
            subprocess.run([COMPILER, '-std=c++17', '-pthread', '-I', str(root), '-I', str(SOURCE),
                            str(root / 'check.cpp'), str(SOURCE / 'nlu/normalizer/vietnamese_normalizer.cpp'),
                            str(SOURCE / 'nlu/intent/intent_parser.cpp'), str(SOURCE / 'nlu/context/context_manager.cpp'),
                            '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    unittest.main()
