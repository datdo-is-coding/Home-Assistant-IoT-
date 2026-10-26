from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'firmware_esp/SubBox/src'
CJSON=SRC.parent/'managed_components/espressif__cjson/cJSON'
class KwsControlTest(unittest.TestCase):
    def test_real_control(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'check'
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(SRC),'-I',str(CJSON),str(ROOT/'tests/kws_control_host/check.cpp'),str(SRC/'audio/kws/kws_control.cpp'),str(CJSON/'cJSON.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
if __name__=='__main__': unittest.main()
