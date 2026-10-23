"""Actual protocol-3 discovery and claim receipts, without fake device success."""
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from main import SmartHomeGateway
from registry_manager import RegistryManager
from device_lifecycle import DeviceLifecycleManager, OperationState

class RegistrationBridgeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.gw = SmartHomeGateway.__new__(SmartHomeGateway)
        self.gw.registry = RegistryManager(str(root/'r.json'), str(root/'r.db'))
        self.gw.mqtt = SimpleNamespace(publish=AsyncMock(return_value=True), node_identities={}, node_routes={}, conflicting_nodes=set())
        self.gw.discovery = SimpleNamespace(publish_ha_discovery_for_node=AsyncMock())
        self.gw.broadcast_event = Mock()
        self.gw.lifecycle = DeviceLifecycleManager(str(root/'r.db'), self.gw.registry, self.gw.mqtt, self.gw.discovery, self.gw.broadcast_event)
        self.uid = 'AB28848533DDF8'
        self.hello = dict(type='SETUP', protocol_version=3, hardware_uid='28848533DDF8', node_id=self.uid,
                          config_version=1, setup_session=123, setup_remaining_ms=170000, channel_count=3)
        self.topic = 'home/subbox/SB01/event/actionbox'

    async def discover(self):
        await self.gw._on_subbox_actionbox(self.topic, self.hello)

    def claim(self):
        return self.gw.lifecycle.start_claim({'role':'admin'}, {'candidate_id':self.uid, 'room_id':'livingroom',
            'channels':{'ch1':{'type':'light','name':'Đèn chính','aliases':['đèn']},
                        'ch2':{'type':'fan','name':'Quạt'},'ch3':{'type':'switch','name':'Ổ cắm'}}}, time.time())

    async def test_real_setup_event_reaches_candidate_and_pending(self):
        await self.discover()
        candidate = self.gw.lifecycle.get_candidate(self.uid)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.subbox_id, 'SB01')
        self.assertIn(self.uid, self.gw.registry.get_pending())
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())

    async def test_claim_only_succeeds_on_matching_subbox_commit(self):
        await self.discover()
        op = self.claim()
        await asyncio.sleep(0)
        receipt = dict(type='CLAIM_APPLIED', node_id=self.uid, hardware_uid='28848533DDF8',
                       protocol_version=3, operation_id=op.operation_id, config_version=op.desired_revision, owner_epoch=1)
        await self.gw._on_subbox_actionbox('home/subbox/WRONG/event/actionbox', receipt)
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())
        await self.gw._on_subbox_actionbox(self.topic, {**receipt, 'operation_id':'stale'})
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())
        await self.gw._on_subbox_actionbox(self.topic, {**receipt, 'config_version':0})
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())
        await self.gw._on_subbox_actionbox(self.topic, receipt)
        self.assertEqual(self.gw.lifecycle.get_operation(op.operation_id).state, OperationState.SUCCEEDED)
        node = self.gw.registry.get_all_nodes()[self.uid]
        self.assertEqual(node['channels']['ch1']['name'], 'Đèn chính')
        self.assertEqual(node['channels']['ch1']['device_type'], 'light')
        self.assertIsNone(self.gw.lifecycle.get_candidate(self.uid))

    async def test_broker_failure_is_reported_without_false_success(self):
        await self.discover()
        self.gw.mqtt.publish.return_value = False
        op = self.claim()
        await asyncio.sleep(0)
        self.assertEqual(self.gw.lifecycle.get_operation(op.operation_id).state, OperationState.FAILED)
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())

    async def test_new_physical_session_reopens_expired_candidate(self):
        await self.discover()
        self.gw.lifecycle.candidates[self.uid].setup_window_expires_at = time.time()-1
        await self.gw._on_subbox_actionbox(self.topic, {**self.hello, 'setup_session':124})
        self.assertIsNotNone(self.gw.lifecycle.get_candidate(self.uid))

    async def test_plain_device_ack_cannot_bypass_subbox_durable_commit(self):
        await self.discover()
        op = self.claim()
        await asyncio.sleep(0)
        await self.gw.lifecycle.on_device_applied(self.uid, operation_id=op.operation_id)
        self.assertNotIn(self.uid, self.gw.registry.get_all_nodes())

    async def test_subbox_capacity_reserves_inflight_claims(self):
        for index in range(4):
            uid=f'AB28848533000{index}'
            self.gw.lifecycle.add_candidate({'device_uid':uid,'subbox_id':'SB01'})
            self.gw.lifecycle.start_claim({'role':'admin'}, {'candidate_id':uid}, time.time())
        await self.discover()
        from device_lifecycle import ClaimError
        with self.assertRaises(ClaimError) as error:
            self.claim()
        self.assertEqual(error.exception.error_code, 'SUBBOX_FULL')

    async def test_gateway_restart_resumes_same_operation_when_subbox_returns(self):
        await self.discover()
        op = self.claim()
        await asyncio.sleep(0)
        restored = DeviceLifecycleManager(self.gw.lifecycle.db_path, self.gw.registry,
            self.gw.mqtt, self.gw.discovery, self.gw.broadcast_event)
        self.gw.mqtt.publish.reset_mock()
        restored.resume_claims('SB01')
        restored.resume_claims('SB01')
        await asyncio.sleep(0)
        self.assertEqual(self.gw.mqtt.publish.await_count, 1)
        self.assertEqual(self.gw.mqtt.publish.call_args.args[1]['op_id'], op.operation_id)
        self.assertEqual(self.gw.mqtt.publish.call_args.args[1]['setup_session'], 123)

    async def test_physical_setup_can_reclaim_existing_record_without_auto_relink(self):
        self.gw.registry.data['nodes'][self.uid] = {'device_id':self.uid, 'room':'oldroom',
            'status':'offline','owner_epoch':1,'mac':'28:84:85:33:DD:F8','channels':{}}
        await self.discover()
        self.assertIsNotNone(self.gw.lifecycle.get_candidate(self.uid))
        self.assertEqual(self.gw.registry.data['nodes'][self.uid]['status'], 'offline')
        op = self.claim()
        await asyncio.sleep(0)
        await self.gw._on_subbox_actionbox(self.topic, dict(type='CLAIM_APPLIED', node_id=self.uid,
            hardware_uid='28848533DDF8',protocol_version=3,operation_id=op.operation_id,
            config_version=op.desired_revision,owner_epoch=2))
        self.assertEqual(self.gw.registry.data['nodes'][self.uid]['room'], 'livingroom')
        self.assertEqual(self.gw.registry.data['nodes'][self.uid]['owner_epoch'], 2)

    async def test_radio_dispatch_keeps_display_names_and_aliases_on_gateway(self):
        await self.discover()
        op = self.gw.lifecycle.start_claim({'role':'admin'}, {'candidate_id':self.uid,
            'room_id':'livingroom','name':'Nhà của tôi',
            'channels':{'ch1':{'type':'light','name':'Đèn phòng khách', 'aliases':['đèn rất dài '*30]*20}}}, time.time())
        await asyncio.sleep(0)
        payload = self.gw.mqtt.publish.call_args.args[1]
        import json
        self.assertLess(len(json.dumps(payload, ensure_ascii=False).encode()), 768)
        self.assertNotIn('aliases', payload['channels']['ch1'])
        self.assertEqual(self.gw.lifecycle.get_operation(op.operation_id).metadata['channels']['ch1']['name'], 'Đèn phòng khách')
