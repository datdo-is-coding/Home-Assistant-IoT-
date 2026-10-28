from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'firmware_esp/SubBox/src'
CJSON=SRC.parent/'managed_components/espressif__cjson/cJSON'


class CoreKwsControlTest(unittest.TestCase):
    def test_real_controller_resolves_parent_room_and_emits_only_configured_target(self):
        packet=struct.pack('<BIBBBI',1,10,0,1,2,42)+struct.pack('<BBBIII',0,0,3,42,8,9)+struct.pack('<BBBIII',0,1,2,42,8,9)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            source=r'''
#include "audio/kws/core_kws_control.h"
#include <cassert>
int main(){
    std::vector<uint8_t> sent;uint64_t now=1700000000000ULL;int saves=0;bool save_ok=true;
    CoreKwsControl control([&](const uint8_t* p,size_t n){sent.assign(p,p+n);return true;},
        [&](const std::string&){++saves;return save_ok;},[&]{return now;});
    uint8_t snapshot[]={BYTES};
    assert(control.configure(snapshot,sizeof(snapshot))&&saves==1);
    assert(control.configure(snapshot,sizeof(snapshot))&&saves==1);
    assert(!control.utterance("99","bật đèn"));assert(sent.empty());
    assert(control.utterance("42","bật đèn"));
    assert(sent.size()==37&&sent[0]==1&&sent[9]==42&&sent[13]==42&&sent[17]==8&&sent[21]==10);
    assert(sent[25]==0&&sent[26]==0&&sent[27]==3&&sent[28]==1);
    assert(control.utterance("42","tắt quạt phòng ngủ"));assert(sent[27]==2&&sent[28]==0);
    assert(control.utterance("42","bật đèn phòng khách"));assert(sent.size()==22&&sent[13]==3);
    assert(control.utterance("42","bật tắt đèn"));assert(sent.size()==22&&sent[13]==1);
    assert(control.utterance("42","đèn"));assert(sent[13]==2);
    assert(control.utterance("42","bật đèn phòng"));assert(sent[13]==2);
    snapshot[1]=9;assert(!control.configure(snapshot,sizeof(snapshot)));
    snapshot[1]=11;save_ok=false;assert(!control.configure(snapshot,sizeof(snapshot)));
    assert(control.utterance("42","bật đèn"));assert(sent[21]==10);
    save_ok=true;snapshot[12+15+1]=0;assert(!control.configure(snapshot,sizeof(snapshot)));
    now=0;assert(!control.utterance("42","bật đèn"));
}
'''.replace('BYTES',','.join(str(b) for b in packet))
            (path/'check.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-I',str(SRC),'-I',str(CJSON),str(path/'check.cpp'),str(SRC/'audio/kws/core_kws_control.cpp'),str(SRC/'audio/kws/kws_control.cpp'),str(CJSON/'cJSON.c'),'-o',str(path/'check')],check=True)
            subprocess.run([str(path/'check')],check=True,timeout=5)
