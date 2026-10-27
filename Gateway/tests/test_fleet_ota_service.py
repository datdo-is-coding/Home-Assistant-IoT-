import asyncio
import base64
import copy
import unittest
from datetime import datetime, timezone

from aiohttp import ClientSession
from aiohttp.test_utils import TestServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from gateway.fleet_ota.identity import FirebaseAuth, GrantSigner, Principal, canonical_json, verify_signed
from gateway.fleet_ota.service import create_app
from gateway.fleet_ota.store import MemoryStore, FirebaseStore


class FleetServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1793052000  # 2026-10-26 22:00 UTC
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.signer = GrantSigner(self.key, 'pilot-grant-1')
        self.device_key = ec.generate_private_key(ec.SECP256R1())
        self.store = MemoryStore()
        self.tokens = {
            'vendor': Principal('vendor', frozenset({'vendor_release_operator', 'vendor_release_approver'})),
            'operator': Principal('operator', frozenset({'vendor_release_operator'})),
            'owner': Principal('owner'), 'other': Principal('other'),
            'gateway': Principal('gw', gateway_id='gw', home_id='home', tenant_id='tenant', owner_epoch=1),
        }

        async def auth(token):
            if token not in self.tokens:
                raise ValueError('invalid token')
            return self.tokens[token]

        self.server = TestServer(create_app(self.store, auth, self.signer, clock=lambda: self.now))
        await self.server.start_server()
        self.client = ClientSession()
        self.pem = self.device_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        await self.request('POST', '/v1/homes/home/enrollment', {'tenant_id': 'tenant', 'gateway_id': 'gw', 'owner_uid': 'owner', 'public_key_pem': self.pem}, 'vendor')

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()

    async def request(self, method, path, body=None, token='owner', status=200):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        async with self.client.request(method, self.server.make_url(path), json=body, headers=headers) as response:
            data = await response.json()
            self.assertEqual(response.status, status, data)
            return data

    async def ready(self):
        artifact = dict(artifact_id='box-v2', sha256='a' * 64, size=1024, compatibility_id='b' * 64, version='2.0.0', storage_key='sha256/' + 'a' * 64, storage_generation='123', signing_key_id='release-1', signed_target='ab' * 176)
        await self.request('POST', '/v1/artifacts', artifact, 'operator')
        await self.request('POST', '/v1/releases', {'release_id': 'r2', 'artifacts': ['box-v2'], 'notes': 'OTA pilot', 'dependencies': {}}, 'operator')
        await self.request('POST', '/v1/releases/r2/approve', {'reason': 'lab tested'}, 'vendor')
        await self.request('POST', '/v1/campaigns', {'campaign_id': 'c2', 'release_id': 'r2', 'seed': 'stable', 'percentage': 100}, 'operator')
        await self.request('PUT', '/v1/homes/home/policy', {'revision': 0, 'consent': True, 'timezone': 'UTC', 'start_minute': 0, 'end_minute': 0, 'days': list(range(7)), 'excluded_targets': []})
        await self.request('PUT', '/v1/homes/home/inventory', {'targets': [{'target_id': 'box', 'compatibility_id': 'b' * 64, 'boot_id': 'boot-old', 'sha256': '0' * 64}]}, 'gateway')
        desired = await self.request('GET', '/v1/homes/home/desired', token='gateway')
        self.job = desired['jobs'][0]
        self.lease = await self.request('POST', '/v1/homes/home/lease', {'worker_id': 'worker'}, 'gateway')
        return artifact

    def binding(self):
        return {'worker_id': 'worker', 'lease_fence': self.lease['fence'], 'generation': self.job['generation']}

    async def grant(self, status=200, **extra):
        return await self.request('POST', '/v1/homes/home/jobs/' + self.job['job_id'] + '/grants', {**self.binding(), 'target_id': 'box', 'policy_revision': 1, **extra}, 'gateway', status)

    async def consume(self, grant, status=200):
        return await self.request('POST', '/v1/homes/home/grants/' + grant['payload']['nonce'] + '/consume', self.binding(), 'gateway', status)

    async def report(self, state, status=200, **extra):
        return await self.request('POST', '/v1/homes/home/jobs/' + self.job['job_id'] + '/reports', {**self.binding(), 'target_id': 'box', 'state': state, **extra}, 'gateway', status)

    async def test_authentication_and_tenant_isolation(self):
        await self.request('GET', '/v1/homes/home/policy', token='', status=401)
        await self.request('GET', '/v1/homes/home/policy', token='other', status=403)
        await self.request('POST', '/v1/artifacts', {}, status=403)
        await self.request('GET', '/v1/homes/another/desired', token='gateway', status=403)
        await self.request('PUT', '/v1/homes/home/policy', {'revision': 0, 'consent': True, 'roles': ['vendor_release_operator']}, status=400)

    async def test_gateway_cannot_change_customer_consent(self):
        await self.request('PUT', '/v1/homes/home/policy', {'revision': 0, 'consent': True, 'timezone': 'UTC', 'start_minute': 0, 'end_minute': 0, 'days': list(range(7)), 'excluded_targets': []}, 'gateway', 403)

    async def test_malformed_catalog_and_campaign_input_is_rejected(self):
        await self.request('POST', '/v1/releases', {'release_id': 'x', 'artifacts': [{}], 'dependencies': {}}, 'operator', 400)
        await self.request('POST', '/v1/campaigns/c2/state', {'state': [], 'reason': 'bad'}, 'operator', 400)

    async def test_download_only_assigned_artifact_and_storage_generation(self):
        await self.ready()
        # No storage signer is injected for this fixture: fail closed.
        await self.request('GET', '/v1/homes/home/artifacts/box-v2/download', token='gateway', status=503)
        await self.request('GET', '/v1/homes/home/artifacts/box-v2/download', token='owner', status=403)
        await self.request('GET', '/v1/homes/home/artifacts/unknown/download', token='gateway', status=403)

    async def test_immutable_catalog_and_approval_gate(self):
        artifact = await self.ready()
        await self.request('POST', '/v1/artifacts', artifact, 'operator')
        await self.request('POST', '/v1/artifacts', {**artifact, 'size': 2048}, 'operator', 409)
        await self.request('POST', '/v1/artifacts', {**artifact, 'artifact_id': 'unsigned', 'signed_target': ''}, 'operator', 400)
        await self.request('POST', '/v1/releases', {'release_id': 'unapproved', 'artifacts': ['box-v2'], 'dependencies': {}}, 'operator')
        await self.request('POST', '/v1/campaigns', {'campaign_id': 'bad', 'release_id': 'unapproved', 'seed': 's', 'percentage': 100}, 'operator', 409)
        await self.request('POST', '/v1/releases/unapproved/approve', {'reason': 'approve'}, 'operator', 403)

    async def test_signed_grant_is_bound_fresh_and_single_use(self):
        await self.ready()
        grant = await self.grant()
        payload = verify_signed(grant, self.key.public_key())
        self.assertEqual(payload['expires_at'] - payload['issued_at'], 120)
        self.assertEqual((payload['home_id'], payload['gateway_id'], payload['target_id'], payload['artifact_sha256'], payload['owner_epoch'], payload['generation']), ('home', 'gw', 'box', 'a' * 64, 1, self.job['generation']))
        await self.consume(grant)
        await self.consume(grant, 409)
        await self.grant(409)
        tampered = copy.deepcopy(grant)
        tampered['payload']['target_id'] = 'different'
        with self.assertRaises(ValueError):
            verify_signed(tampered, self.key.public_key())

    async def test_expired_grant_does_not_start_target(self):
        await self.ready()
        grant = await self.grant()
        self.now += 120
        self.lease = await self.request('POST', '/v1/homes/home/lease', {'worker_id': 'worker'}, 'gateway')
        await self.consume(grant, 409)
        self.assertNotEqual((await self.store.read('homes/home'))['jobs'][self.job['job_id']]['targets']['box']['state'], 'INSTALLING')

    async def test_paused_campaign_stale_policy_and_no_consent_block_grants(self):
        await self.ready()
        await self.grant(409, policy_revision=0)
        await self.request('POST', '/v1/campaigns/c2/state', {'state': 'PAUSED', 'reason': 'pause'}, 'operator')
        await self.grant(409)
        await self.request('POST', '/v1/campaigns/c2/state', {'state': 'ACTIVE', 'reason': 'resume'}, 'operator')
        await self.request('PUT', '/v1/homes/home/policy', {'revision': 1, 'consent': False, 'timezone': 'UTC', 'start_minute': 0, 'end_minute': 0, 'days': list(range(7)), 'excluded_targets': []})
        await self.grant(409, policy_revision=2)

    async def test_already_issued_grant_remains_valid_inside_revocation_bound(self):
        await self.ready()
        grant = await self.grant()
        await self.request('POST', '/v1/campaigns/c2/state', {'state': 'PAUSED', 'reason': 'stop new grants'}, 'operator')
        await self.consume(grant)

    async def test_policy_revision_window_and_exclusion(self):
        await self.ready()
        body = {'revision': 1, 'consent': True, 'timezone': 'Asia/Bangkok', 'start_minute': 0, 'end_minute': 0, 'days': list(range(7)), 'excluded_targets': ['box']}
        await self.request('PUT', '/v1/homes/home/policy', body)
        await self.grant(409, policy_revision=2)
        await self.request('PUT', '/v1/homes/home/policy', body, status=409)
        body.update(revision=2, timezone='invalid')
        await self.request('PUT', '/v1/homes/home/policy', body, status=400)

    async def test_reports_require_grant_transitions_and_boot_evidence(self):
        await self.ready()
        await self.report('SUCCEEDED', 409, boot_id='new', sha256='a' * 64, version='2.0.0', health=True)
        grant = await self.grant()
        await self.consume(grant)
        await self.report('REBOOTING')
        await self.report('LOCAL_VALIDATING')
        await self.report('SUCCEEDED', 409, boot_id='boot-old', sha256='a' * 64, version='2.0.0', health=True)
        await self.report('SUCCEEDED', boot_id='new', sha256='a' * 64, version='2.0.0', health=True)
        await self.report('SUCCEEDED', boot_id='new', sha256='a' * 64, version='2.0.0', health=True)
        await self.report('FAILED', 409)
        await self.request('POST', '/v1/homes/home/jobs/' + self.job['job_id'] + '/reports', {**self.binding(), 'target_id': 'box', 'state': 'SUCCEEDED'}, status=403)

    async def test_lease_fencing_and_inflight_reconciliation(self):
        await self.ready()
        await self.request('POST', '/v1/homes/home/lease', {'worker_id': 'competitor'}, 'gateway', 409)
        grant = await self.grant()
        await self.consume(grant)
        self.now += 121
        replacement = await self.request('POST', '/v1/homes/home/lease', {'worker_id': 'replacement'}, 'gateway')
        self.assertGreater(replacement['fence'], self.lease['fence'])
        await self.report('REBOOTING', 409)
        await self.request('POST', '/v1/homes/home/jobs/' + self.job['job_id'] + '/grants', {'worker_id': 'replacement', 'lease_fence': replacement['fence'], 'generation': self.job['generation'], 'target_id': 'box', 'policy_revision': 1}, 'gateway', 409)

    async def test_ownership_transfer_revokes_tokens_and_pending_jobs(self):
        await self.ready()
        grant = await self.grant()
        result = await self.request('POST', '/v1/homes/home/enrollment', {'tenant_id': 'tenant', 'gateway_id': 'gw', 'owner_uid': 'other', 'public_key_pem': self.pem}, 'vendor')
        self.assertEqual(result['owner_epoch'], 2)
        await self.request('GET', '/v1/homes/home/policy', token='owner', status=403)
        await self.request('GET', '/v1/homes/home/desired', token='gateway', status=403)
        home = await self.store.read('homes/home')
        self.assertEqual(home['jobs'][self.job['job_id']]['targets']['box']['state'], 'CANCELLED')
        self.assertFalse(home['policy']['consent'])

    async def test_inventory_identity_change_does_not_reuse_old_job(self):
        await self.ready()
        await self.request('PUT', '/v1/homes/home/inventory', {'targets': [{'target_id': 'box', 'compatibility_id': 'c' * 64, 'boot_id': 'other', 'sha256': '0' * 64}]}, 'gateway')
        await self.grant(409)

    async def test_simultaneous_consumers_only_one_wins(self):
        await self.ready()
        grant = await self.grant()
        path = '/v1/homes/home/grants/' + grant['payload']['nonce'] + '/consume'
        async def consume():
            async with self.client.post(self.server.make_url(path), json=self.binding(), headers={'Authorization': 'Bearer gateway'}) as response:
                return response.status
        self.assertEqual(sorted(await asyncio.gather(consume(), consume())), [200, 409])

    async def test_customer_can_read_only_own_updates(self):
        await self.ready()
        updates = await self.request('GET', '/v1/homes/home/updates')
        self.assertEqual(updates['jobs'][0]['job_id'], self.job['job_id'])
        await self.request('GET', '/v1/homes/home/updates', token='other', status=403)

    async def test_device_tokens_expire_and_reject_wrong_audience(self):
        auth = FirebaseAuth(None, self.signer, clock=lambda: self.now)
        identity = dict(gateway_id='gw', home_id='home', tenant_id='tenant', owner_epoch=1)
        token = self.signer.device_token(identity, self.now)
        self.assertEqual((await auth(token)).owner_epoch, 1)
        self.now += 900
        with self.assertRaises(ValueError):
            await auth(token)
        token = self.signer.device_token(identity, self.now)
        header, payload, signature = token.split('.')
        import json
        from gateway.fleet_ota.identity import b64, unb64
        claims = json.loads(unb64(payload)); claims['aud'] = 'different'
        payload = b64(canonical_json(claims))
        wrong = header + '.' + payload + '.' + self.signer.sign_bytes((header + '.' + payload).encode())
        with self.assertRaises(ValueError):
            await auth(wrong)

    async def test_failure_ratio_pauses_campaign_after_twenty_results(self):
        await self.ready()
        def seed_results(root):
            home = root['homes']['home']
            job = home['jobs'][self.job['job_id']]
            for index in range(19):
                job['targets']['completed' + str(index)] = {'artifact_id': 'box-v2', 'state': 'SUCCEEDED'}
        await self.store.transaction(seed_results)
        await self.report('FAILED', reason='write_failed')
        self.assertEqual((await self.store.read('campaigns/c2'))['state'], 'PAUSED')

    async def test_device_challenge_requires_proof_and_is_one_use(self):
        challenge = await self.request('POST', '/v1/device-challenges', {'gateway_id': 'gw'}, token='')
        signed = GrantSigner(self.device_key, 'device').sign_bytes(base64.urlsafe_b64decode(challenge['message'] + '=='))
        body = {'gateway_id': 'gw', 'nonce': challenge['nonce'], 'signature': signed}
        token = await self.request('POST', '/v1/device-token', body, token='')
        self.assertEqual(token['expires_in'], 900)
        await self.request('POST', '/v1/device-token', body, token='', status=409)
        challenge = await self.request('POST', '/v1/device-challenges', {'gateway_id': 'gw'}, token='')
        await self.request('POST', '/v1/device-token', {'gateway_id': 'gw', 'nonce': challenge['nonce'], 'signature': 'bad'}, token='', status=401)


class StoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_firebase_store_uses_transactions_and_isolates_callback_retries(self):
        class Reference:
            def __init__(self): self.value = None; self.calls = 0
            def transaction(self, callback):
                self.calls += 1
                callback(copy.deepcopy(self.value))
                self.value = callback(copy.deepcopy(self.value))
                return self.value
            def child(self, path): return self
            def get(self): return copy.deepcopy(self.value)
        reference = Reference()
        store = FirebaseStore(reference)
        def increment(root):
            root['count'] = root.get('count', 0) + 1
            return root['count']
        self.assertEqual(await store.transaction(increment), 1)
        self.assertEqual((await store.read())['count'], 1)
        self.assertEqual(reference.calls, 1)
