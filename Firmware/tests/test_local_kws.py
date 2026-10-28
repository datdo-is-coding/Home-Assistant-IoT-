"""Compile real KWS sentence assembly without ESP hardware."""
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

class LocalKwsTests(unittest.TestCase):
    def test_sentence_boundaries_and_conflicts(self):
        source = r'''
#include "kws_command.h"
#include <cassert>
int main() {
 KwsCommand c;
 assert(c.text() == "__KWS_EMPTY__");
 c.add(CLASS_BAT, .9f); c.add(CLASS_DEN, .9f);
 assert(c.text() == "bật đèn");
 c.add(CLASS_PHONG, .9f);
 assert(c.text() == "bật đèn phòng");
 c.add(CLASS_NGU, .9f); c.add(CLASS_NGU, .95f);
 assert(c.text() == "bật đèn phòng ngủ");
 c.add(CLASS_TAT, .95f);
 assert(c.text() == "__KWS_INVALID__");
 c.reset(); c.add(CLASS_NOISE, .99f); c.add(CLASS_UNKNOWN, .99f);
 c.add(CLASS_DEN, .4f); assert(c.text() == "__KWS_EMPTY__");
 c.add(CLASS_QUAT, .95f); assert(c.text() == "quạt");
 c.add(CLASS_DEN, .95f); assert(c.text() == "__KWS_INVALID__");
 c.reset(); c.add(CLASS_TAT, .9f); c.add(CLASS_QUAT, .9f); c.add(CLASS_BEP, .9f);
 assert(c.text() == "tắt quạt bếp");
 c.add(CLASS_KHACH, .9f); assert(c.text() == "__KWS_INVALID__");
 c.reset(); c.add(CLASS_BAT, .9f); c.add(CLASS_BAT, .9f);
 assert(c.text() == "bật");
 c.add(-1, 1.f); c.add(100, 1.f); assert(c.text() == "__KWS_INVALID__");
}
'''
        with tempfile.TemporaryDirectory() as td:
            cpp = Path(td)/'test.cpp'; cpp.write_text(source)
            exe = Path(td)/'test'
            cmd = ['g++','-std=c++17','-Wall','-Wextra','-Werror',
                   '-I'+str(ROOT/'Firmware/firmware_esp/SubBox/src/audio/kws'),
                   '-I'+str(ROOT/'Firmware/firmware_esp/common/kws'),str(cpp),'-o',str(exe)]
            result = subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(exe)],check=True)

    def test_local_engine_emits_once_after_end(self):
        dataset = ROOT / 'Firmware/tests/fixtures/kws/dataset'
        words = ['bật/100.wav', 'đèn/100.wav', 'phòng/100.wav', 'ngủ/100.wav']
        paths = [dataset / word for word in words]
        if not all(path.is_file() for path in paths):
            self.skipTest('KWS audio samples unavailable')
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / 'sentence.raw'
            frames = bytearray()
            for path in paths:
                with wave.open(str(path), 'rb') as wav:
                    frames += wav.readframes(wav.getnframes())
                frames += b'\0\0' * 1600
            raw.write_bytes(frames)
            runner = r'''
#include "local_kws.h"
#include <algorithm>
#include <cstdio>
#include <vector>
int main(int argc,char**argv) {
    LocalKws kws;
    if (!kws.init()) return 2;
    kws.start();
    for (int i=0;i<16000;i+=480) {
        std::vector<int16_t> silence(480,0);
        if (!kws.feedAudio(silence.data(),silence.size())) return 3;
        if (kws.hasFinalResult()) return 4;
    }
    kws.stop();
    if (std::string(kws.getFinalResult())!="__KWS_EMPTY__") return 5;

    FILE* f=fopen(argv[1],"rb");
    if (!f) return 6;
    std::vector<int16_t> pcm; int16_t value;
    while (fread(&value,sizeof(value),1,f)==1) pcm.push_back(value);
    fclose(f);
    if (!kws.start()) return 7;
    for (size_t i=0;i<pcm.size();i+=480) {
        size_t count=std::min<size_t>(480,pcm.size()-i);
        if (!kws.feedAudio(pcm.data()+i,count)) return 8;
        if (kws.hasFinalResult()) return 9;
    }
    kws.stop();
    if (std::string(kws.getFinalResult())!="bật đèn phòng ngủ") return 10;
    return 0;
}
'''
            cpp = Path(td)/'runner.cpp'; cpp.write_text(runner)
            exe = Path(td)/'runner'
            cmd = ['g++','-std=c++17','-O2','-Wall','-Wextra',
                   '-I'+str(ROOT/'Firmware/firmware_esp/SubBox/src'),
                   '-I'+str(ROOT/'Firmware/firmware_esp/SubBox/src/audio/asr'),
                   '-I'+str(ROOT/'Firmware/firmware_esp/SubBox/src/audio/kws'),
                   '-I'+str(ROOT/'Firmware/firmware_esp/common/kws'),
                   str(cpp),
                   str(ROOT/'Firmware/firmware_esp/SubBox/src/audio/kws/local_kws.cpp'),
                   str(ROOT/'Firmware/firmware_esp/common/kws/kws_mfcc.cpp'),
                   '-o',str(exe)]
            build = subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run = subprocess.run([str(exe),str(raw)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,f'{run.stdout}\n{run.stderr}')

if __name__ == '__main__': unittest.main()
