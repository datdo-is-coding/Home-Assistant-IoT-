import unittest
from cryptography.hazmat.primitives.asymmetric import ec
from gateway.fleet_ota.sign_target import sign
from gateway.fleet_ota.manifest import verify_target


class OfflineSigner(unittest.TestCase):
    def test_signed_packet_binds_image_identity_and_counter(self):
        key=ec.generate_private_key(ec.SECP256R1())
        image=bytearray(512);image[0]=0xe9;image[1]=1;image[12]=9
        image[32:36]=(0xabcd5432).to_bytes(4,'little');image[48:54]=b'1.0.1\0'
        packet,m=sign(bytes(image),key,'ab'*32,2,7)
        self.assertEqual(len(packet),176)
        self.assertEqual(verify_target(packet,key.public_key(),compatibility_id='ab'*32,role=2,image=bytes(image)),m)
        with self.assertRaises(ValueError):verify_target(packet,key.public_key(),compatibility_id='cd'*32,role=2)
        with self.assertRaises(ValueError):verify_target(packet,key.public_key(),compatibility_id='ab'*32,role=2,confirmed_counter=7)
        for bad in (b'bad image',bytes(image)+b'HCF2'):
            with self.assertRaises(ValueError):sign(bad,key,'ab'*32,2,8)
        with self.assertRaises(ValueError):sign(bytes(image),ec.generate_private_key(ec.SECP384R1()),'ab'*32,2,8)
