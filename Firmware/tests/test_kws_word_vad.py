"""Exercise actual LocalKws segmentation; observe windows before MFCC/model."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'Firmware/firmware_esp/SubBox/src/audio/kws'
COMMON = ROOT / 'Firmware/firmware_esp/common/kws'


class WordVadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        (folder / 'probe.h').write_text(r'''#pragma once
#include <vector>
#include <utility>
inline std::vector<std::vector<float>> windows;
inline std::vector<std::pair<int,float>> predictions;
inline bool bad_probabilities=false;
inline bool init_ok=true;
''')
        (folder / 'kws_mfcc.h').write_text(r'''#pragma once
#include "probe.h"
#include "kws_config.h"
#include <cstring>
class MFCCExtractor {public:bool init(){return init_ok;}
void extract(const float* audio,float* out){windows.emplace_back(audio,audio+TOTAL_SAMPLES);memset(out,0,NUM_FRAMES*NUM_MFCC_COEFFS*sizeof(float));}};
''')
        (folder / 'kws_model_quantized.h').write_text(r'''#pragma once
#include "probe.h"
#include "kws_config.h"
#include <cstring>
#include <limits>
inline void kws_run_inference_quantized(const float*,float* out,float*,float*){
 memset(out,0,NUM_CLASSES*sizeof(float));
 auto p=predictions.empty()?std::make_pair(CLASS_NOISE,1.f):predictions.front();
 if(!predictions.empty())predictions.erase(predictions.begin());out[p.first]=p.second;
 if(bad_probabilities)out[CLASS_NOISE]=std::numeric_limits<float>::quiet_NaN();
}
''')
        (folder / 'runner.cpp').write_text(r'''
#include "local_kws.h"
#include "probe.h"
#include <cassert>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>
void samples(std::vector<int16_t>& out,int ms,int16_t value){out.insert(out.end(),ms*16,value);}
bool feed(LocalKws& kws,const std::vector<int16_t>& pcm,size_t chunk=120){
 for(size_t at=0;at<pcm.size();at+=chunk)
  if(!kws.feedAudio(pcm.data()+at,std::min(chunk,pcm.size()-at)))return false;
 return true;
}
void centered(const std::vector<float>& window,int ms,int16_t value){
 assert(window.size()==16000);size_t length=ms*16,start=(16000-length)/2;
 for(size_t i=0;i<window.size();i++)assert(window[i]==(i>=start&&i<start+length?value/32768.f:0.f));
}
int main(int argc,char**argv){
 assert(argc==2);std::string test=argv[1];LocalKws kws;
 if(test=="init_failure"){
  assert(!kws.start());init_ok=false;assert(!kws.init());assert(!kws.start());
  init_ok=true;assert(kws.init());assert(kws.start());return 0;
 }
 assert(kws.init());assert(kws.start());
 std::vector<int16_t> pcm;
 if(test=="short100"||test=="short200"){
  int ms=test=="short100"?100:200;predictions={{CLASS_BAT,.95f}};
  samples(pcm,100,0);samples(pcm,ms,1600);samples(pcm,100,0);assert(feed(kws,pcm));
  assert(windows.size()==1);centered(windows[0],ms,1600);assert(!kws.hasFinalResult());
  kws.stop();assert(windows.size()==1);assert(std::string(kws.getFinalResult())=="bật");
 }else if(test=="short_noise"){
  samples(pcm,100,0);samples(pcm,50,1600);samples(pcm,200,0);assert(feed(kws,pcm));kws.stop();
  assert(windows.empty());assert(std::string(kws.getFinalResult())=="__KWS_EMPTY__");
 }else if(test=="stream_end"){
  predictions={{CLASS_DEN,.95f}};samples(pcm,125,1600);assert(feed(kws,pcm,7));
  assert(windows.empty());kws.stop();assert(windows.size()==1);centered(windows[0],125,1600);
  assert(std::string(kws.getFinalResult())=="đèn");
 }else if(test=="word_gap"){
  predictions={{CLASS_BAT,.95f},{CLASS_DEN,.95f}};
  samples(pcm,100,1600);samples(pcm,100,0);samples(pcm,200,2400);samples(pcm,100,0);
  assert(feed(kws,pcm,160));assert(windows.size()==2);centered(windows[0],100,1600);centered(windows[1],200,2400);
  assert(std::string(kws.getPartialResult())=="bật đèn");assert(!kws.hasFinalResult());
  kws.stop();assert(windows.size()==2);assert(std::string(kws.getFinalResult())=="bật đèn");
 }else if(test=="brief_gap"){
  samples(pcm,100,1600);samples(pcm,50,0);samples(pcm,100,2400);samples(pcm,100,0);
  assert(feed(kws,pcm));kws.stop();assert(windows.size()==1);
  assert(std::count(windows[0].begin(),windows[0].end(),1600/32768.f)==1600);
  assert(std::count(windows[0].begin(),windows[0].end(),2400/32768.f)==1600);
 }else if(test=="long_word"){
  samples(pcm,2500,1600);assert(feed(kws,pcm));assert(!kws.hasFinalResult());assert(kws.isActive());
  assert(windows.size()==2);centered(windows[0],1000,1600);centered(windows[1],1000,1600);
  kws.stop();assert(windows.size()==3);centered(windows[2],500,1600);
  assert(std::string(kws.getFinalResult())=="__KWS_EMPTY__");
 }else if(test=="max_word"){
  samples(pcm,1000,1600);assert(feed(kws,pcm));kws.stop();assert(windows.size()==1);centered(windows[0],1000,1600);
 }else if(test=="cancel_restart"){
  samples(pcm,200,1600);assert(feed(kws,pcm));kws.cancel();assert(windows.empty());
  assert(std::string(kws.getFinalResult())=="__KWS_AUDIO_ERROR__");
  assert(kws.start());pcm.clear();samples(pcm,100,2400);samples(pcm,100,0);
  assert(feed(kws,pcm));kws.stop();assert(windows.size()==1);centered(windows[0],100,2400);
 }else if(test=="background"){
  samples(pcm,2000,300);assert(feed(kws,pcm));kws.stop();assert(windows.empty());
 }else if(test=="packet_boundaries"){
  std::vector<float> reference;
  for(size_t chunk:{1,7,120,160,480,4000}){
   windows.clear();assert(kws.start());pcm.clear();samples(pcm,100,0);samples(pcm,175,1600);samples(pcm,150,0);
   assert(feed(kws,pcm,chunk));kws.stop();assert(windows.size()==1);
   if(reference.empty())reference=windows[0];else assert(reference==windows[0]);
  }
 }else if(test=="bad_model"){
  bad_probabilities=true;predictions={{CLASS_BAT,.95f}};samples(pcm,100,1600);samples(pcm,100,0);
  assert(!feed(kws,pcm));kws.stop();assert(std::string(kws.getFinalResult())=="__KWS_AUDIO_ERROR__");
 }else if(test=="bad_input"){
  assert(!kws.feedAudio(nullptr,1));kws.stop();assert(std::string(kws.getFinalResult())=="__KWS_AUDIO_ERROR__");
 }else if(test=="prefix_then_failure"){
  predictions={{CLASS_BAT,.95f},{CLASS_DEN,.95f}};
  samples(pcm,100,1600);samples(pcm,100,0);samples(pcm,100,2400);samples(pcm,100,0);
  assert(feed(kws,pcm));assert(std::string(kws.getPartialResult())=="bật đèn");
  bad_probabilities=true;pcm.clear();samples(pcm,100,1600);samples(pcm,100,0);
  assert(!feed(kws,pcm));assert(!kws.hasPartialResult());
  kws.stop();assert(std::string(kws.getFinalResult())=="__KWS_AUDIO_ERROR__");assert(windows.size()==3);
 }else if(test=="long_sentence"){
  predictions={{CLASS_BAT,.95f},{CLASS_DEN,.95f},{CLASS_PHONG,.95f},{CLASS_NGU,.95f}};
  samples(pcm,4500,1600);assert(feed(kws,pcm));assert(kws.isActive());assert(!kws.hasFinalResult());
  assert(windows.size()==4);assert(std::string(kws.getPartialResult())=="bật đèn phòng ngủ");
  kws.stop();assert(windows.size()==5);assert(std::string(kws.getFinalResult())=="bật đèn phòng ngủ");
 }else if(test=="elevated_background"){
  predictions={{CLASS_BAT,.95f},{CLASS_DEN,.95f}};
  samples(pcm,700,550);assert(feed(kws,pcm));assert(windows.empty());pcm.clear();
  samples(pcm,100,1600);samples(pcm,80,550);samples(pcm,200,2400);samples(pcm,200,550);
  assert(feed(kws,pcm));assert(windows.size()==2);assert(!kws.hasFinalResult());
  assert(std::count(windows[0].begin(),windows[0].end(),1600/32768.f)==1600);
  assert(std::count(windows[1].begin(),windows[1].end(),2400/32768.f)==3200);
  kws.stop();assert(std::string(kws.getFinalResult())=="bật đèn");
 }else if(test=="short_pause"){
  predictions={{CLASS_BAT,.95f},{CLASS_DEN,.95f}};
  samples(pcm,100,1600);samples(pcm,80,0);samples(pcm,200,2400);samples(pcm,100,0);
  assert(feed(kws,pcm));assert(windows.size()==2);centered(windows[0],100,1600);centered(windows[1],200,2400);
  kws.stop();assert(std::string(kws.getFinalResult())=="bật đèn");
 }else return 2;
}
''')
        cls.binary = folder / 'runner'
        result = subprocess.run([
            'g++', '-std=c++17', '-O2', '-Wall', '-Wextra',
            '-I'+str(folder), '-I'+str(LOCAL),
            '-I'+str(LOCAL.parent / 'asr'), '-I'+str(COMMON),
            str(folder / 'runner.cpp'), str(LOCAL / 'local_kws.cpp'),
            '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_segmentation_and_lifecycle(self):
        for case in ('short100', 'short200', 'short_noise', 'stream_end', 'word_gap',
                     'brief_gap', 'long_word', 'max_word', 'cancel_restart',
                     'background', 'packet_boundaries', 'bad_model', 'bad_input',
                     'init_failure', 'prefix_then_failure', 'long_sentence',
                     'elevated_background', 'short_pause'):
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), case], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
