import hashlib
import json
import struct
import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from test_hc_registry import RegistryTest
from gateway.core_v1.kws import CoreKws, INTENT, SNAPSHOT
from gateway.core_v1.protocol import Frame, MessageType
from gateway.core_v1.registry import CoreError


class CoreKwsTest(unittest.TestCase):
    _Fixture = RegistryTest
    def setUp(self):
        self.fx = self._Fixture(); self.fx.setUp()
        self.r, self.owner, self.home = self.fx.r, self.fx.owner, self.fx.home
        self.sub, self.action = self.fx.sub, self.fx.action
        self.kws = CoreKws(self.r)
        for ch, kind in ((1, 'light'), (2, 'fan'), (3, 'light')):
            self.r.create_device(self.owner, self.home, f'Kênh {ch}', kind, f'HC-001122334402:CH{ch}')
        self.body = dict(revision=0, sources=[dict(node_id='SB001122334401', room='BEDROOM')],
                         bindings=[dict(node_id='AB001122334402', channel=ch, room='BEDROOM', device=role)
                                   for ch, role in ((1, 'LIGHT'), (2, 'FAN'))])
        self.kws.configure(self.owner, self.home, self.body)
        for node in (self.sub, self.action): self.fx.online(node)
        self.fx.report()

    def tearDown(self): self.fx.tearDown()

    def intent(self, **changes):
        values = dict(kind=1, request=1, source=self.action, target=self.action,
                      target_rev=self.r.get_node(self.owner,self.action)['config_rev'], revision=1,
                      room=0, role=0, channel=1, desired=1, expires=int(self.r.clock()*1000)+4000)
        values.update(changes)
        return Frame(MessageType.EVENT_REPORT, 1, self.sub, 0, 100, 1, 1, INTENT.pack(*values.values()))

    def test_room_belongs_to_subbox_and_complete_snapshot_is_bounded(self):
        cfg=self.kws.config(self.owner,self.home)
        self.assertEqual(cfg['sources'],self.body['sources'])
        self.assertEqual(self.r.get_node(self.owner,self.action)['room_id'],self.r.get_node(self.owner,self.sub)['room_id'])
        packet=self.kws.snapshot(self.sub)
        self.assertLessEqual(len(packet),196)
        self.assertEqual(SNAPSHOT.unpack_from(packet),(1,1,0,1,2))
        self.kws.receive(Frame(MessageType.EVENT_REPORT,2,self.sub,0,100,2,1,b'\2'+hashlib.sha256(packet).digest()[:16]))
        self.assertEqual(self.kws.config(self.owner,self.home)['sync']['SB001122334401']['status'],'applied')

    def test_intent_uses_core_command_queue_and_does_not_claim_success_before_ack(self):
        self.kws.receive(self.intent())
        commands=self.r.rows('SELECT * FROM commands')
        self.assertEqual(len(commands),1)
        command=commands[0]
        self.assertEqual((command['node_id'],command['channel_id'],command['status']),(self.action,'HC-001122334402:CH1','ACCEPTED'))
        self.kws.receive(self.intent())
        self.assertEqual(len(self.r.rows('SELECT * FROM commands')),1)
        self.r.ack(self.action,command['command_id'],'APPLIED',command['config_rev'],True)
        self.assertEqual(self.r.one('SELECT status FROM commands')['status'],'APPLIED')

    def test_expired_stale_or_forged_target_never_actuates(self):
        for changes in (dict(expires=1),dict(source=999),dict(channel=3),dict(revision=2),dict(target_rev=999)):
            with self.subTest(changes=changes):
                try:self.kws.receive(self.intent(**changes))
                except CoreError:pass
                self.assertEqual(self.r.rows('SELECT * FROM commands'),[])

    def test_cross_room_and_duplicate_targets_rejected_without_changing_config(self):
        for binding in ([{**self.body['bindings'][0],'room':'KITCHEN'}],self.body['bindings']+[self.body['bindings'][0]]):
            with self.assertRaises(CoreError):self.kws.configure(self.owner,self.home,{**self.body,'revision':1,'bindings':binding})
            self.assertEqual(self.kws.config(self.owner,self.home)['revision'],1)

    def test_channel_three_can_be_selected_without_changing_other_channels(self):
        body={**self.body,'revision':1,'bindings':[{**self.body['bindings'][0],'channel':3},self.body['bindings'][1]]}
        self.kws.configure(self.owner,self.home,body)
        self.kws.receive(self.intent(revision=2,channel=3))
        self.assertEqual(self.r.one('SELECT channel_id FROM commands')['channel_id'],'HC-001122334402:CH3')

    def test_firebase_channel_setup_and_manual_command_share_core_authority(self):
        from gateway.core_v1.firebase_commissioning import CoreCommissioning
        cloud=CoreCommissioning(self.r,{'home_id':self.home},['account'])
        cloud.request('account','POST','/api/device/update',{
            'device_id':'AB001122334402','room':'Phòng ngủ','ch1_name':'Đèn bàn','ch1_type':'light',
            'ch2_name':'Quạt','ch2_type':'fan','ch3_name':'Đèn phụ','ch3_type':'light'})
        with self.assertRaises(CoreError):cloud.request('account','POST','/api/device/update',{'device_id':'AB001122334402','room':'Bếp'})
        command=cloud.request('account','POST','/api/v1/channels/command',{
            'node_id':self.action,'channel':3,'on':True,'idempotency_key':'manual-3'})
        self.assertEqual(command['status'],'ACCEPTED')
        self.r.ack(self.action,command['command_id'],'APPLIED',command['config_rev'],True)
        self.assertEqual(cloud.request('account','GET','/api/v1/commands/'+command['command_id'],{})['status'],'APPLIED')
        projection=cloud.projections('account')['AB001122334402']
        self.assertEqual(projection['subbox_id'],'SB001122334401')
        self.assertEqual(projection['channels']['ch3']['name'],'Đèn phụ')
        self.assertFalse(projection['channels']['ch3']['state']) # ACK does not overwrite the last state report.
        self.assertNotIn('energy',projection['channels']['ch3'])

    def test_rtdb_omitted_empty_bindings_can_clear_voice_targets(self):
        cfg=self.kws.configure(self.owner,self.home,dict(revision=1,sources=self.body['sources']))
        self.assertEqual(cfg['bindings'],[])
        self.assertEqual(SNAPSHOT.unpack_from(self.kws.snapshot(self.sub))[-1],0)

    def test_app_keeps_other_device_types_without_adding_them_to_voice_vocabulary(self):
        from gateway.core_v1.firebase_commissioning import CoreCommissioning
        cloud=CoreCommissioning(self.r,{'home_id':self.home},['account'])
        cloud.request('account','POST','/api/device/update',{'device_id':'AB001122334402','ch3_name':'Máy bơm','ch3_type':'pump'})
        self.assertEqual(cloud.projections('account')['AB001122334402']['channels']['ch3']['device_type'],'pump')
        with self.assertRaises(CoreError):
            self.kws.configure(self.owner,self.home,{**self.body,'revision':1,'bindings':[{**self.body['bindings'][0],'channel':3}]})


del RegistryTest


class CoreKwsFeedbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_ack_precedes_reply_and_only_origin_subbox_receives_it(self):
        case=CoreKwsTest();case.setUp()
        audio=SimpleNamespace(speak_proactive=AsyncMock(return_value=True))
        task=asyncio.create_task(case.kws.feedback(audio))
        try:
            await asyncio.sleep(.01)
            case.kws.receive(case.intent())
            await asyncio.sleep(.15)
            audio.speak_proactive.assert_not_awaited()
            command=case.r.one('SELECT * FROM commands')
            case.r.ack(case.action,command['command_id'],'APPLIED',command['config_rev'],True)
            for _ in range(30):
                if audio.speak_proactive.await_count:break
                await asyncio.sleep(.02)
            audio.speak_proactive.assert_awaited_once_with('Relay của Kênh 1 đã bật.','SB001122334401')
            self.assertEqual(len(case.r.rows('SELECT * FROM commands')),1)
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True);case.tearDown()
