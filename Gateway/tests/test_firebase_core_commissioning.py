"""Cloud commissioning must use the same Core registry as the radio coordinator."""
import hashlib
import hmac
import struct
from pathlib import Path
import tempfile
import unittest

from gateway.core_v1.registry import Registry, CoreError
from gateway.core_v1.firebase_commissioning import CoreCommissioning


class FirebaseCoreCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Registry(Path(self.tmp.name)/'core.db', b'k'*32)
        self.owner, _ = self.r.create_user('Factory operator')
        self.home = self.r.create_home(self.owner, 'Home')
        self.room = self.r.create_room(self.owner, self.home, 'Bedroom')
        self.factory = 'HC-001122334401'
        self.secret = b's'*32
        self.r.add_factory_device(self.factory,'SUB_BOX','HC-S1',self.secret,'unique-setup-code')
        self.c = CoreCommissioning(self.r, {'home_id':self.home,'channel':11,
            'mqtt_uri':'mqtts://broker:8883','ota_pubkey':'04'+'22'*64,'parents':{}}, ['owner'])

    def tearDown(self):
        self.r.close();self.tmp.cleanup()

    def claim(self, key='logical-claim'):
        return self.c.request('owner','POST','/api/v1/nodes/claim', {
            'factory_id':self.factory,'setup_code':'unique-setup-code',
            'room_id':self.room,'idempotency_key':key})

    def test_context_uses_existing_home_and_does_not_export_factory_credentials(self):
        result = self.c.context('owner')
        self.assertEqual(result['profile'],'core-v1')
        self.assertEqual(result['snapshot']['home_id'],self.home)
        self.assertEqual(result['defaults']['channel'],11)
        self.assertNotIn('unique-setup-code',str(result))

    def test_claim_is_durable_and_only_device_receipt_registers(self):
        claim = self.claim()
        restarted = CoreCommissioning(self.r,self.c.config,['owner'])
        self.assertEqual(restarted.request('owner','POST','/api/v1/nodes/claim',{
            'factory_id':self.factory,'setup_code':'unique-setup-code','room_id':self.room,
            'idempotency_key':'logical-claim'})['claim_id'],claim['claim_id'])
        request={'claim_id':claim['claim_id'],'challenge':'11'*32,
                 'radio_mac':'001122334401','wifi_ssid':'Home WiFi','wifi_password':'private-pass'}
        first = self.c.request('owner','POST','/api/v1/provisioning/prepare',request)
        second = restarted.request('owner','POST','/api/v1/provisioning/prepare',request)
        self.assertEqual(first['packet'],second['packet'])
        self.assertEqual(self.c.request('owner','GET','/api/v1/provisioning/'+claim['claim_id'],{})['status'],'PAIRING')
        key=hmac.digest(self.secret,b'HC-OPERATING-V1\0'+bytes.fromhex(claim['nonce']),'sha256')
        body=struct.pack('<4s32sIIBB',b'HCA1',bytes.fromhex(claim['nonce']),claim['node_id'],0,0,3)
        self.c.provisioning.accept_receipt(body+hmac.digest(key,body,'sha256'))
        self.assertEqual(self.c.request('owner','GET','/api/v1/provisioning/'+claim['claim_id'],{})['status'],'REGISTERED')

    def test_unknown_uid_wrong_home_or_dangerous_route_is_denied(self):
        for uid,method,path,body in [('other','GET','/api/v1/states/snapshot',{}),
                ('owner','POST','/api/v1/nodes/1/unpair',{}),
                ('owner','GET','/api/v1/states/snapshot?home_id=another',{})]:
            with self.subTest(path=path),self.assertRaises(CoreError):
                self.c.request(uid,method,path,body)

    def test_changed_retry_and_forged_ota_key_are_denied(self):
        claim=self.claim()
        with self.assertRaises(CoreError):
            self.c.request('owner','POST','/api/v1/nodes/claim',{
                'factory_id':self.factory,'setup_code':'wrong','room_id':self.room,
                'idempotency_key':'logical-claim'})
        request={'claim_id':claim['claim_id'],'challenge':'11'*32,'radio_mac':'001122334401',
                 'wifi_ssid':'Home WiFi','wifi_password':'password','ota_pubkey':'04'+'33'*64}
        with self.assertRaises(CoreError):
            self.c.request('owner','POST','/api/v1/provisioning/prepare',request)


if __name__=='__main__': unittest.main()
