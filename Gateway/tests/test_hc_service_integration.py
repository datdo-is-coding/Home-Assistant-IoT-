"""Integration tests for Core V1 HTTP/WebSocket services and Voice ingress (INT-01, INT-02, LOG-05)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import hashlib
import hmac
import tempfile
import unittest

try:
    from aiohttp.test_utils import TestClient, TestServer
    from gateway.core_v1.api import create_app
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False
    TestClient = TestServer = None
    create_app = None

from gateway.core_v1.registry import Registry, canonical
from gateway.core_v1.voice import CoreVoice

class MockASR:
    def __init__(self, text='bật đèn', confidence=0.95):
        self.text = text
        self.confidence = confidence

    def transcribe_with_confidence(self, samples, sample_rate):
        return (self.text, self.confidence)

@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp not installed")
class ServiceIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'service.db'
        self.master_key = b'k' * 32
        self.registry = Registry(self.db_path, self.master_key)

        self.owner, self.owner_token = self.registry.create_user('Owner')
        self.home = self.registry.create_home(self.owner, 'Main Home')
        self.room = self.registry.create_room(self.owner, self.home, 'Living Room')
        self.keys = {}

        self.sub = self.enroll('HC-001122334401', 'SUB_BOX')
        self.action = self.enroll('HC-001122334402', 'ACTION_BOX', self.sub)

        self.device = self.registry.create_device(
            self.owner, self.home, 'Light', 'light', 'HC-001122334402:CH1'
        )

        self.online(self.sub, 200)
        self.online(self.action, 100)
        self.report(self.action)

        self.member, self.member_token = self.registry.create_user('SubBox Member')
        self.registry.db.execute(
            'INSERT INTO home_members VALUES(?,?,?)', (self.home, self.member, 'Member')
        )

        self.asr = MockASR('bật đèn', 0.95)
        self.voice = CoreVoice(self.registry, {self.sub: self.member}, asr=self.asr)

        self.app = create_app(self.registry, voice=self.voice)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

        self.owner_headers = {'Authorization': f'Bearer {self.owner_token}'}
        self.member_headers = {'Authorization': f'Bearer {self.member_token}'}

    async def asyncTearDown(self):
        await self.client.close()
        self.registry.close()
        self.tmp.cleanup()

    def enroll(self, factory, kind, parent=None):
        secret = hashlib.sha256(factory.encode()).digest()
        self.registry.add_factory_device(
            factory, kind, 'HC-S1' if kind == 'SUB_BOX' else 'HC-A1', secret, 'setup-' + factory
        )
        claim = self.registry.claim(self.owner, factory, 'setup-' + factory, self.room, parent)
        proof = hmac.digest(
            secret,
            canonical(dict(claim=claim, stored=True, peer_confirmed=True, channels=3 if parent else 0)),
            'sha256'
        ).hex()
        node = self.registry.confirm_claim(
            claim['claim_id'], proof, stored=True, peer_confirmed=True, channels=3 if parent else 0
        )
        self.keys[node['node_id']] = self.registry.node_key(node['node_id'])
        return node['node_id']

    def online(self, node, boot=100):
        challenge = self.registry.session_challenge(node, boot)
        proof = hmac.digest(self.keys[node], canonical(challenge), 'sha256').hex()
        self.registry.admit_session(node, challenge['nonce'], proof)

    def report(self, node=None, seq=1, boot=100, state=False, valid=True, current=.3):
        node = node or self.action
        rev = self.registry.get_node(self.owner, node)['config_rev']
        payload = dict(
            node_id=node,
            boot_id=boot,
            state_seq=seq,
            config_rev=rev,
            channels=[dict(number=i, relay_state=state, ct_valid=valid,
                           current_rms_a=current if valid else None, fault_flags=0) for i in (1, 2, 3)]
        )
        return self.registry.report_state(node, payload)

    async def test_int01_health_auth_and_routes(self):

        resp = await self.client.get('/api/v1/health')
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data['product'], 'Home Competition')
        self.assertEqual(data['api_version'], 1)
        self.assertTrue(data['database'])

        resp = await self.client.get('/api/v1/homes')
        self.assertEqual(resp.status, 401)

        resp = await self.client.get('/api/v1/homes', headers=self.owner_headers)
        self.assertEqual(resp.status, 200)
        homes = (await resp.json())['items']
        self.assertEqual(len(homes), 1)
        self.assertEqual(homes[0]['home_id'], self.home)

        resp = await self.client.get(f'/api/v1/states/snapshot?home_id={self.home}', headers=self.owner_headers)
        self.assertEqual(resp.status, 200)
        snapshot = await resp.json()
        self.assertEqual(snapshot['home_id'], self.home)
        self.assertEqual(len(snapshot['rooms']), 1)
        self.assertEqual(len(snapshot['devices']), 1)
        self.assertEqual(snapshot['devices'][0]['device_id'], self.device['device_id'])

        cmd_payload = {'state': True, 'idempotency_key': '0' * 32, 'ttl': 5}
        resp = await self.client.post(
            f'/api/v1/devices/{self.device["device_id"]}/command',
            headers=self.owner_headers,
            json=cmd_payload
        )
        self.assertEqual(resp.status, 202)
        cmd_res = await resp.json()
        self.assertEqual(cmd_res['status'], 'ACCEPTED')
        cmd_id = cmd_res['command_id']

        resp = await self.client.get(f'/api/v1/commands/{cmd_id}', headers=self.owner_headers)
        self.assertEqual(resp.status, 200)
        cmd_info = await resp.json()
        self.assertEqual(cmd_info['status'], 'ACCEPTED')
        self.assertEqual(cmd_info['desired'], 1)

        resp = await self.client.get('/api/v1/openapi.json', headers=self.owner_headers)
        self.assertEqual(resp.status, 200)
        spec = await resp.json()
        self.assertIn('/api/v1/voice/ws', spec['paths'])

    async def test_int01_voice_websocket_end_to_end(self):
        ws_headers = {
            'Authorization': f'Bearer {self.member_token}',
            'X-Device-ID': str(self.sub),
        }
        async with self.client.ws_connect('/api/v1/voice/ws', headers=ws_headers) as ws:
            req_id = 'a' * 32
            await ws.send_json({
                'type': 'start',
                'codec': 'pcm',
                'sample_rate': 16000,
                'source_node_id': self.action,
                'request_id': req_id,
            })

            msg = await ws.receive_json(timeout=5)
            self.assertEqual(msg['type'], 'status')
            self.assertEqual(msg['state'], 'recording')

            await ws.send_bytes(bytes(320))
            await ws.send_json({'type': 'stop'})

            transcript = await ws.receive_json(timeout=5)
            self.assertEqual(transcript['type'], 'transcript')
            self.assertEqual(transcript['text'], 'bật đèn')
            self.assertAlmostEqual(transcript['confidence'], 0.95)
            self.assertTrue(transcript['accepted'])

            commands = []
            for _ in range(50):
                commands = self.registry.rows(
                    'SELECT * FROM commands WHERE device_id=? AND idempotency_key=?',
                    (self.device['device_id'], f'voice:{self.sub}:{req_id}')
                )
                if commands:
                    break
                await asyncio.sleep(0.02)

            self.assertEqual(len(commands), 1)
            cmd = commands[0]
            self.assertEqual(cmd['status'], 'ACCEPTED')
            self.assertEqual(cmd['channel_id'], 'HC-001122334402:CH1')
            self.assertEqual(cmd['desired'], 1)

            self.registry.ack(self.action, cmd['command_id'], 'APPLIED', cmd['config_rev'], True)

            result = await ws.receive_json(timeout=5)
            self.assertEqual(result['type'], 'command_result')
            self.assertEqual(result['verify'], 'success')
            self.assertEqual(result['status'], 'APPLIED')
            self.assertEqual(result['command_id'], cmd['command_id'])

    async def test_int01_voice_unconfigured_or_unauthorized(self):

        app_no_voice = create_app(self.registry, voice=None)
        client_no_voice = TestClient(TestServer(app_no_voice))
        await client_no_voice.start_server()
        try:
            resp = await client_no_voice.get(
                '/api/v1/voice/ws',
                headers={'Authorization': f'Bearer {self.member_token}', 'X-Device-ID': str(self.sub)}
            )
            self.assertEqual(resp.status, 503)
            err = await resp.json()
            self.assertEqual(err['error']['code'], 'voice_not_configured')
        finally:
            await client_no_voice.close()

        resp = await self.client.get(
            '/api/v1/voice/ws',
            headers={'Authorization': 'Bearer wrong_token', 'X-Device-ID': str(self.sub)}
        )
        self.assertEqual(resp.status, 401)
        err = await resp.json()
        self.assertEqual(err['error']['code'], 'unauthorized')

        resp = await self.client.get(
            '/api/v1/voice/ws',
            headers={'Authorization': f'Bearer {self.member_token}', 'X-Device-ID': '99999'}
        )
        self.assertEqual(resp.status, 403)
        err = await resp.json()
        self.assertEqual(err['error']['code'], 'voice_identity_denied')

        resp = await self.client.get(
            '/api/v1/voice/ws',
            headers={'Authorization': f'Bearer {self.member_token}', 'X-Device-ID': 'invalid_id'}
        )
        self.assertEqual(resp.status, 403)
        err = await resp.json()
        self.assertEqual(err['error']['code'], 'voice_identity_denied')

    async def test_int02_legacy_isolation_and_cross_home(self):

        other_user, other_token = self.registry.create_user('Other Owner')
        other_home = self.registry.create_home(other_user, 'Other Home')
        other_headers = {'Authorization': f'Bearer {other_token}'}

        resp = await self.client.get(f'/api/v1/states/snapshot?home_id={self.home}', headers=other_headers)
        self.assertEqual(resp.status, 403)

        resp = await self.client.post(
            f'/api/v1/devices/{self.device["device_id"]}/command',
            headers=other_headers,
            json={'state': True, 'idempotency_key': 'x' * 32, 'ttl': 5}
        )
        self.assertEqual(resp.status, 403)

        resp = await self.client.get(
            '/api/v1/voice/ws',
            headers={'Authorization': f'Bearer {other_token}', 'X-Device-ID': str(self.sub)}
        )
        self.assertEqual(resp.status, 403)

        resp = await self.client.post(
            f'/api/v1/devices/{self.device["device_id"]}/command',
            headers=self.owner_headers,
            json={'state': 'invalid_bool', 'idempotency_key': 'y' * 32}
        )
        self.assertEqual(resp.status, 400)

        resp = await self.client.post(
            f'/api/v1/devices/{self.device["device_id"]}/command',
            headers=self.owner_headers,
            json={}
        )
        self.assertEqual(resp.status, 400)

        resp = await self.client.post(
            f'/api/v1/devices/{self.device["device_id"]}/command',
            headers=self.owner_headers,
            data='not json'
        )
        self.assertEqual(resp.status, 400)

        resp = await self.client.post(
            '/api/v1/devices/DEV-nonexistent/command',
            headers=self.owner_headers,
            json={'state': True, 'idempotency_key': 'z' * 32}
        )
        self.assertEqual(resp.status, 404)

if __name__ == '__main__':
    unittest.main()
