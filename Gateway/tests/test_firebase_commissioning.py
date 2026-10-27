"""The cloud worker must reuse the live lifecycle and never publish credentials."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from firebase_commissioning import FirebaseCommissioningBridge, device_projection


class Store:
    def __init__(self):
        self.data = {}

    async def read(self, path):
        return copy.deepcopy(self.data.get(path))

    async def write(self, path, value):
        self.data[path] = copy.deepcopy(value)

    async def patch(self, updates):
        self.data.update(copy.deepcopy(updates))

    async def rules(self):
        import json
        return json.loads((Path(__file__).resolve().parents[1] /
                           'firebase/commissioning.rules.json').read_text())


class FirebaseWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store()
        self.dispatcher = SimpleNamespace(dispatch=AsyncMock(return_value={
            'request_id': 'a' * 32, 'status_code': 202,
            'body': {'success': True, 'operation': {'state': 'running'}}}))
        self.gateway = SimpleNamespace(registry=SimpleNamespace(get_all_nodes=lambda: {}))
        self.config = {'gateway_id': 'gw-test', 'installer_uids': ['owner'],
                       'mqtt_host': '192.168.1.8', 'mqtt_port': 8883}
        self.worker = FirebaseCommissioningBridge(self.gateway, self.store, self.config,
                                                  dispatcher=self.dispatcher, clock=lambda: 1000)

    async def test_worker_dispatches_same_request_once_and_persists_response(self):
        rid = 'a' * 32
        self.store.data['gateway_rpc/gw-test/requests'] = {'owner': {rid: {
            'request_id': rid, 'method': 'GET', 'path': '/api/commissioning/candidates',
            'created_at': 999000, 'expires_at': 1005000}}}
        await self.worker.tick()
        await self.worker.tick()
        self.dispatcher.dispatch.assert_awaited_once()
        self.assertEqual(self.store.data[f'gateway_rpc/gw-test/responses/owner/{rid}']['status_code'], 202)
        self.assertTrue(self.store.data['gateway_access/owner/gw-test'])
        self.assertEqual(self.store.data['gateways/gw-test/status']['last_seen'], 1000000)

    async def test_failed_response_write_does_not_consume_request(self):
        rid = 'a' * 32
        self.store.data['gateway_rpc/gw-test/requests'] = {'owner': {rid: {
            'request_id': rid, 'method': 'POST', 'path': '/api/commissioning/claims',
            'body': {'idempotency_key': 'same-logical-claim'},
            'created_at': 999000, 'expires_at': 1005000}}}
        original = self.store.write
        async def fail_once(path, value):
            self.store.write = original
            raise OSError('connection lost')
        self.store.write = fail_once
        with self.assertRaises(OSError):
            await self.worker.tick()
        await self.worker.tick()
        self.assertEqual(self.dispatcher.dispatch.await_count, 2)
        self.assertIn(f'gateway_rpc/gw-test/responses/owner/{rid}', self.store.data)

    async def test_no_gateway_grants_for_unknown_user_or_unbounded_request(self):
        self.store.data['gateway_rpc/gw-test/requests'] = {
            'intruder': {'a' * 32: {}}, 'owner': {'b' * 32: {'body': {'x': 's' * 17000}}}}
        await self.worker.tick()
        self.dispatcher.dispatch.assert_not_awaited()
        self.assertNotIn('gateway_access/intruder/gw-test', self.store.data)

    async def test_current_registered_device_appears_without_pending_secret(self):
        self.gateway.registry.get_all_nodes = lambda: {
            'AB123': {'name': 'Kitchen', 'room': 'kitchen', 'status': 'online',
                      'last_seen': '1970-01-01T00:16:40+00:00', 'setup_proof': 'secret',
                      'channels': {'ch1': {'name': 'Lamp', 'state': True, 'setup': 'secret'}}}}
        await self.worker.tick()
        value = self.store.data['devices/AB123']
        self.assertEqual(value['channels']['ch1']['state'], True)
        self.assertEqual(value['last_updated'], 1000000)
        self.assertNotIn('secret', str(value))

    async def test_stop_marks_only_own_status_offline(self):
        await self.worker.close()
        self.assertFalse(self.store.data['gateways/gw-test/status']['online'])

    async def test_public_rules_never_grant_or_consume_requests(self):
        self.store.rules = AsyncMock(return_value={'rules': {'.write': True}})
        with self.assertRaises(ValueError):
            await self.worker.tick()
        self.assertEqual(self.store.data, {})
        self.dispatcher.dispatch.assert_not_awaited()


class ProjectionTests(unittest.TestCase):
    def test_local_timezone_is_converted_to_unix_time(self):
        value = device_projection('AB1', {'status': 'online',
            'last_seen': '2026-10-27T19:00:00+07:00', 'channels': None})
        self.assertEqual(value['last_updated'], 1793102400000)
        self.assertEqual(value['channels'], {})

    def test_missing_measurements_and_state_remain_unknown(self):
        value = device_projection('AB1', {'channels': {'ch1': {'name': 'Lamp'}}})
        self.assertNotIn('state', value['channels']['ch1'])
        self.assertNotIn('power', value['channels']['ch1'])
        self.assertFalse(value['online'])

    def test_invalid_rtdb_keys_and_unregistered_nodes_are_skipped(self):
        self.assertIsNone(device_projection('bad/id', {}))
        self.assertIsNone(device_projection('AB1', {'state': 'FACTORY_NEW'}))


class ConfigTests(unittest.TestCase):
    def test_disabled_by_default_and_private_explicit_configuration(self):
        from firebase_commissioning import configured_bridge, read_config
        from unittest.mock import patch
        with patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(configured_bridge(SimpleNamespace()))
        import json
        import os
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            data = {'database_url': 'https://test.firebasedatabase.app',
                    'gateway_id': 'gw1', 'installer_uids': ['owner'],
                    'mqtt_host': '192.168.1.1', 'mqtt_port': 8883}
            config.write_text(json.dumps(data))
            os.chmod(config, 0o600)
            self.assertEqual(read_config(config), data)
            os.chmod(config, 0o644)
            with self.assertRaises(ValueError):
                read_config(config)
            os.chmod(config, 0o600)
            for changes in ({'installer_uids': []}, {'database_url': 'http://test.firebasedatabase.app'},
                            {'mqtt_host': 'test.firebasedatabase.app'}, {'mqtt_port': True}):
                config.write_text(json.dumps(dict(data, **changes)))
                with self.assertRaises(ValueError):
                    read_config(config)


if __name__ == '__main__':
    unittest.main()
