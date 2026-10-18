import hashlib
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric import ec,utils
from cryptography.hazmat.primitives import hashes,serialization
from gateway.core_v1.registry import Registry,CoreError
from gateway.core_v1.ota import OtaManager,manifest_bytes

class OtaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.r=Registry(self.root/'core.db',b'k'*32)
        self.private=ec.generate_private_key(ec.SECP256R1())
        self.manager=OtaManager(self.r,self.root/'images',self.private.public_key())
        import struct
        image=bytearray(512)
        image[0]=0xe9;image[1]=1
        struct.pack_into('<H',image,12,9)
        struct.pack_into('<II',image,32,0xabcd5432,1)
        image[48:54]=b'1.0.1\0'
        self.image=bytes(image)
        self.manifest=dict(model='HC-A1',version='1.0.1',size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest())
        der=self.private.sign(manifest_bytes(self.manifest),ec.ECDSA(hashes.SHA256()))
        r,s=utils.decode_dss_signature(der)
        self.signature=(r.to_bytes(32,'big')+s.to_bytes(32,'big')).hex()
    def tearDown(self):self.r.close();self.tmp.cleanup()
    def test_signed_artifact_hash_and_bounds(self):
        a=self.manager.upload(self.manifest,self.signature,self.image)
        self.assertEqual(a['sha256'],self.manifest['sha256'])
        self.assertEqual(len(manifest_bytes(self.manifest)),68)
        self.assertEqual(self.manager.read_chunk(a['artifact_id'],0)[0:1],b'\xe9')
        with self.assertRaises(CoreError):self.manager.upload(self.manifest,self.signature,self.image+b'x')
        with self.assertRaises(CoreError):self.manager.upload(self.manifest,'00'*64,self.image)
        with self.assertRaises(CoreError):self.manager.upload({**self.manifest,'model':'HC-S1'},self.signature,self.image)
        with self.assertRaises(CoreError):self.manager.upload({**self.manifest,'size':0x300001},self.signature,self.image)
    def test_manifest_strict_and_no_path_injection(self):
        with self.assertRaises((ValueError,CoreError)):manifest_bytes({**self.manifest,'model':'../../bad'})
        with self.assertRaises((ValueError,CoreError)):manifest_bytes({**self.manifest,'version':'1'*17})

    def test_signed_wrong_target_and_image_version_rejected(self):
        for at,value in ((12,0),(48,ord('2')),(32,0)):
            bad=bytearray(self.image);bad[at]=value;bad=bytes(bad)
            manifest={**self.manifest,'sha256':hashlib.sha256(bad).hexdigest()}
            r,s=utils.decode_dss_signature(self.private.sign(manifest_bytes(manifest),ec.ECDSA(hashes.SHA256())))
            signature=(r.to_bytes(32,'big')+s.to_bytes(32,'big')).hex()
            with self.assertRaises(CoreError):self.manager.upload(manifest,signature,bad)
