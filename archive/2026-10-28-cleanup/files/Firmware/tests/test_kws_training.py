"""Candidate export parity and whole-session split validation; needs torch."""
import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'Firmware/firmware_kws/scripts'
COMMON = ROOT / 'Firmware/firmware_esp/common/kws'

@unittest.skipUnless(importlib.util.find_spec('torch'), 'training environment requires torch')
class KwsTrainingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        import calibrate_model
        cls.calibration = calibrate_model

    def test_session_split_rejects_same_recording_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'train.wav').write_bytes(b'same audio')
            (p/'test.wav').write_bytes(b'same audio')
            manifest = p/'manifest.json'
            manifest.write_text(json.dumps([
                {'path':'train.wav','label':'bật','split':'train'},
                {'path':'test.wav','label':'bật','split':'test'},
            ]))
            with self.assertRaisesRegex(ValueError, 'recording reused'):
                self.calibration.load_manifest(manifest)

    def test_export_matches_pytorch_checkpoint(self):
        import numpy as np
        import torch
        torch.set_num_threads(2)
        model = self.calibration.load_model(ROOT/'Firmware/firmware_kws/models/kws_dscnn_best.pt')
        features = np.load(ROOT/'Firmware/firmware_kws/data/X_test.npy')
        features = ((features + 9.295776) / 35.392517).astype(np.float32)
        with torch.no_grad():
            reference = model(torch.from_numpy(features[:,None])).softmax(-1).numpy()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            self.calibration.export_header(model, COMMON/'kws_model_quantized.h', p/'candidate.h')
            (p/'run.cpp').write_text('#include "candidate.h"\nextern "C" void run(const float*x,float*y){kws_run_inference_quantized(x,y);}\n')
            subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC',f'-I{COMMON}',str(p/'run.cpp'),'-o',str(p/'run.so')],check=True)
            lib=ctypes.CDLL(str(p/'run.so')); ptr=ctypes.POINTER(ctypes.c_float)
            lib.run.argtypes=[ptr,ptr]
            actual=np.zeros_like(reference)
            for x,y in zip(features,actual):lib.run(x.ctypes.data_as(ptr),y.ctypes.data_as(ptr))
        self.assertGreaterEqual(float(np.mean(actual.argmax(1)==reference.argmax(1))),.99)
        self.assertLess(float(np.max(np.abs(actual-reference))),.04)

    def test_silent_recording_cannot_be_labeled_as_a_word(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'silence.wav'
            with wave.open(str(p),'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(bytes(32000))
            extractor = self.calibration.Features(td)
            with self.assertRaisesRegex(ValueError, 'no speech detected'):
                self.calibration.recording_features({'path':p,'label':'bật'},extractor)
            features, labels = self.calibration.recording_features({'path':p,'label':'noise'},extractor)
            self.assertEqual(features.shape, (4,99,13))
            self.assertTrue((labels == 4).all())

    def test_training_crops_do_not_change_validation_windows(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'word.wav'
            pcm = np.zeros(48000,dtype=np.int16)
            for start in (8000,20000,32000):
                pcm[start:start+4800] = (3000*np.sin(np.arange(4800)*.2)).astype(np.int16)
            with wave.open(str(p),'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(pcm.tobytes())
            extractor=self.calibration.Features(td)
            row={'path':p,'label':'bật'}
            original,_=self.calibration.recording_features(row,extractor)
            augmented,labels=self.calibration.recording_features(row,extractor,augment=True)
            repeated,_=self.calibration.recording_features(row,extractor)
            np.testing.assert_array_equal(original,repeated)
            self.assertGreater(len(augmented),len(original))
            self.assertTrue(np.isfinite(augmented).all())
            self.assertTrue((labels==0).all())

    def test_quiet_validation_session_is_not_dropped(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'quiet.wav'
            pcm=(100*np.sin(np.arange(32000)*.2)).astype(np.int16)
            with wave.open(str(p),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
                wav.writeframes(pcm.tobytes())
            features,labels=self.calibration.recording_features(
                {'path':p,'label':'khách','split':'val'},self.calibration.Features(td))
            self.assertEqual(features.shape,(1,99,13))
            self.assertEqual(labels.tolist(),[2])

if __name__=='__main__':unittest.main()
