from pathlib import Path
import sys, tempfile, time, unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from device_lifecycle import DeviceLifecycleManager, OperationState
from mqtt_handler import MQTTHandler
from registry_manager import RegistryManager
from main import SmartHomeGateway

class MaintenanceTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.registry=RegistryManager(db_path=str(Path(tmp.name)/'db'),registry_path=str(Path(tmp.name)/'absent'))
        self.uid='AB28848533DDF8'; self.sb='SB288485350B54'
        self.registry.data['nodes']={self.uid:{'status':'online','owner_epoch':6,'subbox_id':self.sb,'security':{'state':'READY'},'channels':{}},self.sb:{'status':'online','owner_epoch':1,'channels':{}}}
        self.mqtt=MQTTHandler(); self.mqtt.publish=AsyncMock(return_value=True)
        self.mqtt.node_identities[self.uid]={'hardware_uid':self.uid[2:],'protocol_version':3,'config_version':1}
        self.mqtt.node_routes[self.uid]=(self.sb,time.monotonic())
        self.auth=Mock();self.events=Mock()
        self.manager=DeviceLifecycleManager(db_path=str(Path(tmp.name)/'ops'),registry=self.registry,mqtt=self.mqtt,auth=self.auth,broadcaster=self.events)
        self.user={'role':'admin','username':'test'}
    async def start(self,kind,uid=None):
        import asyncio
        op=self.manager.start_operation(self.user,uid or self.uid,kind,confirmation=True)
        await asyncio.sleep(.01)
        return op
    async def test_wire_envelope_matches_real_firmware(self):
        op=await self.start('identify')
        topic,payload=self.mqtt.publish.call_args.args[:2]
        self.assertEqual(topic,f'home/subbox/{self.sb}/command')
        for key in ['protocol_version','hardware_uid','config_version','request_id','session_id','operation_id','owner_epoch']:
            self.assertIn(key,payload)
        self.assertEqual(payload['cmd'],'IDENTIFY')
        self.assertEqual(payload['operation_id'],op.operation_id)
        self.assertEqual(self.mqtt.publish.call_count,1)
    async def test_factory_reset_waits_for_matching_ack_and_preserves_on_failure(self):
        op=await self.start('factory_reset')
        self.assertEqual(self.registry.data['nodes'][self.uid]['owner_epoch'],6)
        self.auth.revoke_device_grants.assert_not_called()
        self.assertIsNone(self.manager.on_operation_ack(self.sb,op.operation_id))
        self.manager.on_operation_ack(self.uid,op.operation_id,status='failed')
        self.assertEqual(self.registry.data['nodes'][self.uid]['owner_epoch'],6)
        self.assertIsNone(self.manager.on_operation_ack(self.uid,op.operation_id,status='ok'))
        self.auth.revoke_device_grants.assert_not_called()
    async def test_successful_reset_commits_once(self):
        op=await self.start('factory_reset')
        self.manager.on_operation_ack(self.uid,op.operation_id,status='ok')
        self.assertEqual(self.registry.data['nodes'][self.uid]['owner_epoch'],7)
        self.assertEqual(self.registry.data['nodes'][self.uid]['status'],'unclaimed')
        self.assertIsNone(self.manager.on_operation_ack(self.uid,op.operation_id,status='ok'))
        self.auth.revoke_device_grants.assert_called_once_with(self.uid)
    async def test_failed_publish_reports_failure_without_waiting_for_timeout(self):
        self.mqtt.publish.return_value=False
        op=await self.start('identify')
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.FAILED)
    async def test_subbox_uses_own_command_topic(self):
        await self.start('identify',self.sb)
        self.assertEqual(self.mqtt.publish.call_args.args[0],f'home/subbox/{self.sb}/command')
    async def test_ack_is_bound_to_route_request_and_session(self):
        op=await self.start('identify')
        sent=self.mqtt.publish.call_args.args[1]
        gateway=SmartHomeGateway.__new__(SmartHomeGateway);gateway.lifecycle=self.manager
        ack={**sent,'status':'OK','device_uid':self.uid}
        handler=gateway._on_subbox_operation_ack
        topic=f'home/subbox/{self.sb}/event/operation'
        await handler(topic,{**ack,'session_id':0})
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.RUNNING)
        await handler(topic.replace(self.sb,'SBother'),ack)
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.RUNNING)
        await handler(topic,ack)
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.SUCCEEDED)
    async def test_reset_timeout_does_not_mark_device_unclaimed(self):
        op=await self.start('factory_reset')
        self.manager.get_operation(op.operation_id, now_sec=op.expires_at+1)
        self.assertEqual(self.registry.data['nodes'][self.uid]['status'],'online')
        self.assertEqual(self.registry.data['nodes'][self.uid]['owner_epoch'],6)

    async def test_reboot_without_route_fails_immediately(self):
        self.mqtt.node_routes.clear()
        op=await self.start('reboot')
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.FAILED)

    async def test_malformed_receipts_do_not_crash_or_complete_operation(self):
        op=await self.start('identify')
        sent=self.mqtt.publish.call_args.args[1]
        gateway=SmartHomeGateway.__new__(SmartHomeGateway);gateway.lifecycle=self.manager
        topic=f'home/subbox/{self.sb}/event/operation'
        await gateway._on_subbox_operation_ack(topic,{**sent,'status':True})
        await gateway._on_subbox_operation_ack(topic,{**sent,'operation_id':[],'status':'OK'})
        self.assertEqual(self.manager.get_operation(op.operation_id).state,OperationState.RUNNING)

    async def test_unpaired_telemetry_does_not_restore_online_after_reset(self):
        gateway=SmartHomeGateway.__new__(SmartHomeGateway);gateway.registry=self.registry
        self.registry.data['nodes'][self.uid]['state']='reconnecting'
        payload={'node_id':self.uid,'channels':[],'owner_epoch':6,'claimed':False}
        await gateway._on_subbox_actionbox(f'home/subbox/{self.sb}/event/actionbox',payload)
        self.assertEqual(self.registry.data['nodes'][self.uid]['status'],'offline')
        self.assertEqual(self.registry.data['nodes'][self.uid]['state'],'reconnecting')
        await gateway._on_subbox_actionbox(f'home/subbox/{self.sb}/event/actionbox',{**payload,'claimed':True})
        self.assertEqual(self.registry.data['nodes'][self.uid]['status'],'online')
