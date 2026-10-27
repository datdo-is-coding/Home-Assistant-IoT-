"""Firebase commissioning requests retain the local lifecycle's ownership checks."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))

from device_lifecycle import DeviceLifecycleManager
from registry_manager import RegistryManager


class RecordingMqtt:
    def __init__(self):
        self.messages = []
        self.node_identities = {'AB001122334455': {'config_version': 1}}
        self.session_id = 1

    def subbox_route(self, node_id):
        return 'SB001122334466' if node_id in self.node_identities else None

    async def publish(self, topic, payload, **kwargs):
        self.messages.append((topic, payload))
        return True


class CommissioningRpcTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            from commissioning_rpc import CommissioningRpc
        except ModuleNotFoundError:
            self.fail('The Firebase commissioning dispatcher is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1700000000.0
        self.registry = RegistryManager(db_path=str(Path(self.temp.name) / 'registry.db'))
        self.mqtt = RecordingMqtt()
        self.lifecycle = DeviceLifecycleManager(
            db_path=self.registry.db_path, registry=self.registry, mqtt=self.mqtt)
        self.gateway = SimpleNamespace(lifecycle=self.lifecycle)
        self.rpc = CommissioningRpc(self.gateway, {'owner', 'other'}, clock=lambda: self.now)
        self.lifecycle.add_candidate({
            'device_uid': 'AB001122334455', 'subbox_id': 'SB001122334466',
            'setup_proof': 'secret-physical-proof', 'setup_session': 123,
            'channel_count': 3, 'protocol_version': 3,
        }, now_sec=self.now)

    async def asyncTearDown(self):
        for task in getattr(getattr(self, 'lifecycle', None), '_claim_tasks', {}).values():
            task.cancel()
        await asyncio.sleep(0)

    def envelope(self, request_id='request_1', method='GET', path='/api/commissioning/candidates', body=None):
        return {'request_id': request_id, 'method': method, 'path': path,
                'body': {} if body is None else body,
                'created_at': self.now * 1000, 'expires_at': self.now * 1000 + 15000}

    def claim(self, request_id='claim_1', **fields):
        body = {'candidate_id': 'AB001122334455', 'subbox_id': 'SB001122334466',
                'room_id': 'livingroom', 'name': 'Main lights',
                'setup_proof': 'secret-physical-proof',
                'channels': {'ch1': {'type': 'light', 'name': 'Desk', 'aliases': ['desk lamp']}},
                **fields}
        return self.envelope(request_id, 'POST', '/api/commissioning/claims', body)

    async def test_candidate_list_never_exports_physical_proof(self):
        response = await self.rpc.dispatch('owner', 'request_1', self.envelope())
        self.assertEqual(response['status_code'], 200)
        self.assertEqual(response['body']['candidates'][0]['device_uid'], 'AB001122334455')
        self.assertNotIn('secret-physical-proof', json.dumps(response))
        self.now += 31
        response = await self.rpc.dispatch('owner', 'next', self.envelope('next'))
        self.assertEqual(response['body']['candidates'], [])

    async def test_get_request_accepts_firebase_omitting_empty_body(self):
        request = self.envelope()
        del request['body']
        response = await self.rpc.dispatch('owner', 'request_1', request)
        self.assertEqual(response['status_code'], 200)

    async def test_oversized_numeric_deadline_fails_without_exception(self):
        request = self.claim()
        request['created_at'] = 10 ** 400
        response = await self.rpc.dispatch('owner', 'claim_1', request)
        self.assertEqual(response['status_code'], 400)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_claim_uses_same_lifecycle_and_waits_for_authenticated_device_apply(self):
        response = await self.rpc.dispatch('owner', 'claim_1', self.claim())
        self.assertEqual(response['status_code'], 202)
        operation = response['body']['operation']
        self.assertEqual(operation['requested_by'], 'firebase:owner')
        self.assertEqual(operation['state'], 'accepted')
        self.assertNotIn('secret-physical-proof', json.dumps(response))
        self.assertNotIn('AB001122334455', self.registry.data['nodes'])
        await asyncio.sleep(0)
        self.assertEqual(self.mqtt.messages[0][0], 'home/subbox/SB001122334466/command')
        self.assertEqual(self.mqtt.messages[0][1]['cmd'], 'claim')
        self.assertEqual(self.mqtt.messages[0][1]['op_id'], operation['operation_id'])

    async def test_mailbox_claim_confirmation_then_firebase_inventory_projection(self):
        from firebase_commissioning import FirebaseCommissioningBridge
        from test_firebase_commissioning import Store
        uid = 'AB001122334455'
        self.registry.data['pending'][uid] = {'device_id': uid, 'hardware': 'ActionBox',
            'mac': '00:11:22:33:44:55', 'rl': [0, 0, 0], 'subbox_id': 'SB001122334466'}
        self.gateway.registry = self.registry
        store = Store()
        worker = FirebaseCommissioningBridge(self.gateway, store,
            {'gateway_id': 'gw1', 'installer_uids': ['owner'], 'mqtt_host': '192.168.1.2',
             'mqtt_port': 8883}, dispatcher=self.rpc, clock=lambda: self.now)
        request = self.claim()
        store.data['gateway_rpc/gw1/requests'] = {'owner': {'claim_1': request}}
        await worker.tick()
        accepted = store.data['gateway_rpc/gw1/responses/owner/claim_1']['body']['operation']
        self.assertNotIn('devices/' + uid, store.data)
        self.assertEqual(accepted['state'], 'accepted')
        self.assertIsNone(await self.lifecycle.on_device_applied(uid,
            operation_id=accepted['operation_id'], config_revision=1,
            now_sec=self.now + 1, confirmed_subbox='WRONG_SUBBOX'))
        await self.lifecycle.on_device_applied(uid, operation_id=accepted['operation_id'],
            config_revision=1, now_sec=self.now + 1, confirmed_subbox='SB001122334466')
        self.now += 4
        poll = self.envelope('poll', path='/api/operations/' + accepted['operation_id'])
        store.data['gateway_rpc/gw1/requests'] = {'owner': {'poll': poll}}
        await worker.tick()
        response = store.data['gateway_rpc/gw1/responses/owner/poll']
        self.assertEqual(response['body']['operation']['state'], 'succeeded')
        self.assertEqual(store.data['devices/' + uid]['name'], 'Main lights')
        self.assertEqual(store.data['devices/' + uid]['channels']['ch1']['name'], 'Desk')
        self.assertNotIn('secret-physical-proof', json.dumps(store.data))

    async def test_uid_allowlist_and_body_role_cannot_grant_admin(self):
        response = await self.rpc.dispatch('intruder', 'claim_1', self.claim())
        self.assertEqual(response['status_code'], 403)
        response = await self.rpc.dispatch('owner', 'claim_2', self.claim('claim_2', role='admin'))
        self.assertEqual(response['status_code'], 400)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_expired_and_invalid_timestamps_never_create_an_operation(self):
        cases = [({'created_at': self.now * 1000 - 20000, 'expires_at': self.now * 1000 - 1}, 408),
                 ({'created_at': self.now * 1000 + 5001}, 400),
                 ({'expires_at': self.now * 1000 + 30001}, 400),
                 ({'created_at': True}, 400), ({'expires_at': float('nan')}, 400)]
        for index, (updates, status) in enumerate(cases):
            request_id = 'invalid_' + str(index)
            envelope = self.claim(request_id)
            envelope.update(updates)
            with self.subTest(updates=updates):
                response = await self.rpc.dispatch('owner', request_id, envelope)
                self.assertEqual(response['status_code'], status)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_request_key_must_match_envelope_and_unknown_fields_fail(self):
        for index, updates in enumerate(({'request_id': 'another'}, {'user': {'role': 'admin'}}, {'body': []})):
            request_id = 'bad_' + str(index)
            envelope = self.claim(request_id)
            envelope.update(updates)
            response = await self.rpc.dispatch('owner', request_id, envelope)
            self.assertEqual(response['status_code'], 400)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_resets_removal_relay_and_arbitrary_paths_cannot_dispatch(self):
        routes = [('/api/devices/AB001122334455/operations', {'kind': 'factory_reset', 'confirmation': True}),
                  ('/api/devices/AB001122334455/remove', {}), ('/api/relay', {}),
                  ('/api/ota/upload', {}), ('/api/nodes', {})]
        for index, (path, body) in enumerate(routes):
            request_id = 'denied_' + str(index)
            envelope = self.envelope(request_id, 'POST', path, body)
            response = await self.rpc.dispatch('owner', request_id, envelope)
            self.assertEqual(response['status_code'], 403)
        self.assertEqual(self.mqtt.messages, [])

    async def test_only_requesting_uid_can_poll_its_operation(self):
        accepted = await self.rpc.dispatch('owner', 'claim_1', self.claim())
        op_id = accepted['body']['operation']['operation_id']
        for uid, status in [('owner', 200), ('other', 404)]:
            request = self.envelope('poll_' + uid, path='/api/operations/' + op_id)
            response = await self.rpc.dispatch(uid, request['request_id'], request)
            self.assertEqual(response['status_code'], status)

    async def test_logical_retry_survives_new_request_id_and_dispatcher_restart(self):
        accepted = await self.rpc.dispatch('owner', 'claim_1', self.claim(idempotency_key='logical_retry'))
        from commissioning_rpc import CommissioningRpc
        restarted = CommissioningRpc(self.gateway, {'owner', 'other'}, clock=lambda: self.now)
        response = await restarted.dispatch('owner', 'claim_2', self.claim('claim_2', idempotency_key='logical_retry'))
        self.assertEqual(response['status_code'], 202)
        self.assertEqual(response['body']['operation']['operation_id'], accepted['body']['operation']['operation_id'])
        other = await restarted.dispatch('other', 'claim_3', self.claim('claim_3', idempotency_key='logical_retry'))
        self.assertEqual(other['status_code'], 409)
        self.assertEqual(other['body']['error_code'], 'CLAIM_IN_PROGRESS')

    async def test_transport_replay_returns_same_result_and_rejects_changed_payload(self):
        request = self.claim()
        accepted = await self.rpc.dispatch('owner', 'claim_1', request)
        replay = await self.rpc.dispatch('owner', 'claim_1', request)
        self.assertEqual(replay, accepted)
        changed = copy.deepcopy(request)
        changed['body']['name'] = 'Changed lights'
        conflict = await self.rpc.dispatch('owner', 'claim_1', changed)
        self.assertEqual(conflict['status_code'], 409)
        self.assertEqual(len(self.lifecycle.list_operations(now_sec=self.now)), 1)

    async def test_expired_request_id_cannot_be_replaced_with_fresh_claim(self):
        expired = self.claim()
        expired.update(created_at=self.now * 1000 - 20000, expires_at=self.now * 1000 - 1)
        self.assertEqual((await self.rpc.dispatch('owner', 'claim_1', expired))['status_code'], 408)
        self.assertEqual((await self.rpc.dispatch('owner', 'claim_1', self.claim()))['status_code'], 409)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_invalid_claim_fields_rejected_before_lifecycle_mutates(self):
        for index, fields in enumerate(({'config_revision': 'oops'}, {'room_id': []},
                                        {'channels': {'ch4': {'type': 'light'}}},
                                        {'channels': {'ch1': {'aliases': 'not-a-list'}}})):
            request_id = 'bad_claim_' + str(index)
            response = await self.rpc.dispatch('owner', request_id, self.claim(request_id, **fields))
            self.assertEqual(response['status_code'], 400)
        self.assertEqual(self.lifecycle.list_operations(now_sec=self.now), [])

    async def test_identify_uses_existing_operation_without_changing_relays(self):
        self.registry.data['nodes']['AB001122334455'] = {'channels': {'ch1': {'state': True}}}
        request = self.envelope('identify_1', 'POST', '/api/devices/AB001122334455/operations', {'kind': 'identify'})
        response = await self.rpc.dispatch('owner', 'identify_1', request)
        self.assertEqual(response['status_code'], 202)
        self.assertEqual(response['body']['operation']['kind'], 'identify')
        self.assertTrue(self.registry.data['nodes']['AB001122334455']['channels']['ch1']['state'])
        await asyncio.sleep(0)
        self.assertEqual(self.mqtt.messages[0][1]['cmd'], 'IDENTIFY')


if __name__ == '__main__':
    unittest.main()
