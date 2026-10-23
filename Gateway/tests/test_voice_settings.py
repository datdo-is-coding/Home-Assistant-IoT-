"""A saved voice choice must survive a Gateway restart."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

class VoiceSettingsTests(unittest.TestCase):
    def test_saved_voice_overrides_environment_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            shutil.copyfile(Path(__file__).resolve().parents[1]/'gateway/config.py', root/'config.py')
            (root/'local_config.json').write_text(json.dumps({'VIENEU_VOICE':'Trúc Ly','TTS_PROVIDER':'vieneu','TTS_RATE':'+0%','TTS_PITCH':'+3Hz'}))
            env=dict(os.environ,VIENEU_VOICE='Ái Hân',TTS_PROVIDER='edgetts',TTS_RATE='-4%',TTS_PITCH='+2Hz')
            result=subprocess.run([sys.executable,'-c','import config,json; print(json.dumps([config.VIENEU_VOICE,config.TTS_PROVIDER,config.TTS_RATE,config.TTS_PITCH]))'],cwd=root,env=env,capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout),['Trúc Ly','vieneu','+0%','+3Hz'])
