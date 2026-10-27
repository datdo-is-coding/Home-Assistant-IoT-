"""Opt-in real RTDB Rules/normalization checks, isolated to a demo namespace."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from commissioning_rpc import CommissioningRpc
from device_lifecycle import DeviceLifecycleManager
from firebase_commissioning import FirebaseCommissioningBridge
from registry_manager import RegistryManager


def token(uid):
    # Unsigned demo token accepted only by the emulator, never a real Firebase project.
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    now = int(time.time())
    return encode({'alg': 'none', 'typ': 'JWT'}) + '.' + encode({
        'sub': uid, 'user_id': uid, 'iat': now, 'exp': now + 3600, 'auth_time': now,
        'aud': 'demo-homecompetition', 'iss': 'https://securetoken.google.com/demo-homecompetition',
        'firebase': {'sign_in_provider': 'custom'}}) + '.'


class EmulatorStore:
    def __init__(self, address):
        if address != '127.0.0.1:19000':
            raise ValueError('Tests require the isolated loopback emulator on port 19000')
        self.url = 'http://' + address

    def request(self, path, method='GET', value=None, uid=None):
        query = {'ns': 'demo-homecompetition'}
        if uid is not None:
            query['auth'] = token(uid)
        data = None if method == 'GET' else json.dumps(value).encode()
        request = Request(self.url + '/' + path + '.json?' + urlencode(query),
                          data=data, method=method,
                          headers={'Content-Type': 'application/json',
                                   **({'Authorization': 'Bearer owner'} if uid is None else {})})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            with response:
                return response.code, json.load(response)

    async def read(self, path):
        code, value = await asyncio.to_thread(self.request, path)
        if code != 200:
            raise RuntimeError('Emulator read failed')
        return value

    async def write(self, path, value):
        code, result = await asyncio.to_thread(self.request, path, 'PUT', value)
        if code != 200:
            raise RuntimeError('Emulator write failed: ' + str(result))

    async def patch(self, updates):
        code, _ = await asyncio.to_thread(self.request, '', 'PATCH', updates)
        if code != 200:
            raise RuntimeError('Emulator patch failed')

    async def rules(self):
        return await self.read('.settings/rules')


@unittest.skipUnless(os.environ.get('HC_TEST_RTDB_EMULATOR'), 'Explicit local emulator required')
class FirebaseCommissioningEmulatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = EmulatorStore(os.environ['HC_TEST_RTDB_EMULATOR'])
        await self.store.write('', None)
        rules = json.loads((Path(__file__).resolve().parents[1] /
                            'firebase/commissioning.rules.json').read_text())
        await self.store.write('.settings/rules', rules)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = RegistryManager(db_path=str(Path(self.temp.name) / 'registry.db'))
        self.lifecycle = DeviceLifecycleManager(db_path=self.registry.db_path, registry=self.registry)
        self.gateway = SimpleNamespace(registry=self.registry, lifecycle=self.lifecycle)
        self.worker = FirebaseCommissioningBridge(self.gateway, self.store,
            {'gateway_id': 'demo-gateway', 'installer_uids': ['installer'],
             'mqtt_host': '192.168.1.2', 'mqtt_port': 8883},
            dispatcher=CommissioningRpc(self.gateway, {'installer'}))
        await self.worker.tick()

    async def client(self, path, method='GET', value=None, uid='installer'):
        return await asyncio.to_thread(self.store.request, path, method, value, uid)

    def envelope(self, request_id, path='/api/commissioning/candidates', method='GET', body=None):
        now = int(time.time() * 1000)
        return {'request_id': request_id, 'method': method, 'path': path, 'body': body or {},
                'created_at': now, 'expires_at': now + 15000}

    async def test_real_rules_allow_only_assigned_uid_and_normalize_empty_body(self):
        code, access = await self.client('gateway_access/installer')
        self.assertEqual((code, access), (200, {'demo-gateway': True}))
        status_path = 'gateways/demo-gateway/status'
        self.assertEqual((await self.client(status_path))[0], 200)
        self.assertIn((await self.client(status_path, uid='intruder'))[0], (401, 403))
        rid = 'request1'
        path = 'gateway_rpc/demo-gateway/requests/installer/' + rid
        request = self.envelope(rid)
        self.assertEqual((await self.client(path, 'PUT', request))[0], 200)
        self.assertNotIn('body', await self.store.read(path))
        for denied_path, value, uid in ((path, request, 'installer'),
                ('gateway_rpc/demo-gateway/requests/installer/spoof', self.envelope('spoof'), 'intruder'),
                ('gateway_access/intruder/demo-gateway', True, 'intruder'),
                ('gateway_rpc/demo-gateway/responses/installer/forged', {'status_code': 200}, 'installer'),
                (status_path, {'online': True}, 'installer')):
            code, _ = await self.client(denied_path, 'PUT', value, uid)
            self.assertIn(code, (401, 403))
        self.assertIn((await self.client(path))[0], (401, 403))
        await self.worker.tick()
        response_path = 'gateway_rpc/demo-gateway/responses/installer/' + rid
        code, response = await self.client(response_path)
        self.assertEqual((code, response['status_code']), (200, 200))
        self.assertTrue(response['body']['success'])
        self.assertIn((await self.client(response_path, uid='intruder'))[0], (401, 403))

    async def test_request_validation_and_claim_to_verified_inventory(self):
        uid = 'AB001122334455'
        candidate = {'device_uid': uid, 'device_id': uid, 'subbox_id': 'SB001122334466',
                     'hardware': 'ActionBox', 'rl': [0, 0, 0], 'setup_session': 123,
                     'channel_count': 3, 'protocol_version': 3, 'setup_proof': 'private-test-proof'}
        self.lifecycle.add_candidate(candidate)
        self.registry.data['pending'][uid] = candidate
        root = 'gateway_rpc/demo-gateway/'
        for rid, changes in (('future', {'created_at': int(time.time() * 1000) + 10000}),
                              ('long', {'expires_at': int(time.time() * 1000) + 60000}),
                              ('unknown', {'user': {'role': 'admin'}})):
            request = self.envelope(rid)
            request.update(changes)
            self.assertIn((await self.client(root + 'requests/installer/' + rid, 'PUT', request))[0], (401, 403))
        request = self.envelope('claim', '/api/commissioning/claims', 'POST', {
            'candidate_id': uid, 'setup_proof': 'private-test-proof',
            'subbox_id': 'SB001122334466', 'room_id': 'kitchen', 'name': 'Kitchen lights',
            'idempotency_key': 'same-claim', 'channels': {'ch1': {'name': 'Desk', 'type': 'light'}}})
        self.assertEqual((await self.client(root + 'requests/installer/claim', 'PUT', request))[0], 200)
        await self.worker.tick()
        _, response = await self.client(root + 'responses/installer/claim')
        operation = response['body']['operation']
        self.assertEqual(operation['state'], 'accepted')
        self.assertIsNone(await self.store.read('devices/' + uid))
        self.assertNotIn('private-test-proof', json.dumps(response))
        await self.lifecycle.on_device_applied(uid, operation_id=operation['operation_id'],
            config_revision=1, confirmed_subbox='SB001122334466')
        self.worker._next_status = 0
        await self.worker.tick()
        self.assertEqual((await self.store.read('devices/' + uid))['name'], 'Kitchen lights')
        poll = self.envelope('poll', '/api/operations/' + operation['operation_id'])
        self.assertEqual((await self.client(root + 'requests/installer/poll', 'PUT', poll))[0], 200)
        await self.worker.tick()
        _, response = await self.client(root + 'responses/installer/poll')
        self.assertEqual(response['body']['operation']['state'], 'succeeded')

    async def test_core_context_and_secure_claim_use_same_firebase_mailbox(self):
        from gateway.core_v1.registry import Registry
        from gateway.core_v1.firebase_commissioning import CoreCommissioning
        registry=Registry(Path(self.temp.name)/'core.db',b'k'*32)
        self.addCleanup(registry.close)
        owner,_=registry.create_user('Factory operator')
        home=registry.create_home(owner,'Home')
        room=registry.create_room(owner,home,'Bedroom')
        registry.add_factory_device('HC-001122334401','SUB_BOX','HC-S1',b's'*32,'unique-setup-code')
        core=CoreCommissioning(registry,{'home_id':home,'channel':11,
            'mqtt_uri':'mqtts://broker','ota_pubkey':'04'+'22'*64,'parents':{}},['installer'])
        self.worker.core=core
        self.worker.dispatcher.core=core
        root='gateway_rpc/demo-gateway/'
        request=self.envelope('context','/api/commissioning/context')
        self.assertEqual((await self.client(root+'requests/installer/context','PUT',request))[0],200)
        await self.worker.tick()
        _,response=await self.client(root+'responses/installer/context')
        self.assertEqual(response['body']['profile'],'core-v1')
        self.assertNotIn('nodes',response['body']['snapshot'])
        request=self.envelope('coreclaim','/api/v1/nodes/claim','POST',{
            'factory_id':'HC-001122334401','setup_code':'unique-setup-code','room_id':room,
            'idempotency_key':'logical-core-claim'})
        self.assertEqual((await self.client(root+'requests/installer/coreclaim','PUT',request))[0],200)
        await self.worker.tick()
        _,response=await self.client(root+'responses/installer/coreclaim')
        self.assertEqual(response['status_code'],200)
        node_id=response['body']['node_id']
        self.assertEqual(registry.one('SELECT registration FROM registered_nodes WHERE node_id=?',(node_id,))['registration'],'PAIRING')
        self.assertIsNone(await self.store.read(root+'requests/installer/coreclaim'))
        self.assertIsNone(await self.store.read('devices/SB001122334401'))


if __name__ == '__main__':
    unittest.main()
