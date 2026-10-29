"""Malformed IR waveforms must never reach the RMT transmitter."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class InfraredLimitsTests(unittest.TestCase):
    def test_bounded_modulated_wave(self):
        root=Path(__file__).resolve().parents[1]
        source='''#include <cassert>
#include "ir_limits.h"
int main() {
 uint16_t wave[]={900,450,56,169,56,4000};
 assert(ir_valid_wave(wave,6,38000));
 assert(!ir_valid_wave(wave,6,0));
 assert(!ir_valid_wave(wave,6,100000));
 assert(!ir_valid_wave(wave,3,38000));
 wave[2]=2001; assert(!ir_valid_wave(wave,6,38000));
 wave[2]=0; assert(!ir_valid_wave(wave,6,38000));
 uint16_t longwave[1024]; for(auto &v:longwave)v=2000;
 assert(!ir_valid_wave(longwave,1024,38000));
}'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'check.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-Wall','-Werror','-I',str(root/'firmware_esp/SubBox/src/infrared'),str(p/'check.cpp'),'-o',str(p/'check')],check=True,capture_output=True)
            subprocess.run([str(p/'check')],check=True)
