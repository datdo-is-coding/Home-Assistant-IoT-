import asyncio
import json
import time
from unittest import TestCase,IsolatedAsyncioTestCase
from gateway.core_v1.infrared.voice import climate_intent
from gateway.core_v1.infrared.service import InfraredService
from gateway.core_v1.infrared.codec import decode,panasonic_seed,encode,nec
from gateway.core_v1.registry import CoreError
from test_pi_speaker_voice import PiSpeakerVoiceTests as _Fixture


class ClimateGrammarTests(TestCase):
    def test_explicit_temperature_and_negative_commands(self):
        for phrase in ('đặt điều hòa 26 độ','chỉnh nhiệt độ điều hòa hai mươi sáu độ','điều hòa về 26 độ'):
            target,patch,kind=climate_intent(phrase);self.assertEqual(target,'dieu hoa');self.assertEqual(patch,{'power':True,'temperature':26})
        self.assertEqual(climate_intent('giảm nhiệt độ máy lạnh hai độ')[1],{'delta':-2})
        for phrase in ('không đặt điều hòa 26 độ','đừng bật điều hòa','chưa tắt điều hòa','hôm nay trời đẹp'):
            self.assertIsNone(climate_intent(phrase))


class ClimateVoiceTests(IsolatedAsyncioTestCase):
    _BaseFixture=_Fixture
    def setUp(self):
        self.base=self._BaseFixture();self.base.setUp()
        for key in ('fixture','device','socket','server','core','session'):setattr(self,key,getattr(self.base,key))
    def tearDown(self):self.base.tearDown()
    async def prepare_remote(self):
        f=self.fixture;self.core.home=f.home
        self.socket.core_token='valid';self.socket.infrared_capabilities={'version':2,'tx':True,'rx':True}
        self.server._ws_nodes={'SB001122334401':self.socket}
        self.ir=InfraredService(self.core,self.server);self.core.infrared=self.ir;self.transmissions=[];self.results=[]
        async def send(text):
            message=json.loads(text)
            if message.get('type') in ('ir_prepare','ir_send'):
                if message['type']=='ir_send':self.transmissions.append(message)
                result={'id':message['id'],'ok':True,'mono_ms':1000}
                asyncio.get_running_loop().call_soon(self.ir.accept,self.socket,result)
            else:self.results.append(message)
        self.socket.send=send
        await self.ir.for_user(f.owner,'POST','/api/v1/ir/test',{'node_id':f.sub,'profile_id':'panasonic-cwa75c4179','idempotency_key':'profile_test_123'})
        self.remote=await self.ir.for_user(f.owner,'POST','/api/v1/ir/remotes',{'node_id':f.sub,'profile_id':'panasonic-cwa75c4179','name':'Điều hòa Panasonic','aliases':['máy lạnh'],'confirmed':True})
        self.transmissions.clear()

    async def test_asr_to_climate_and_relative_request_is_not_applied_twice(self):
        await self.prepare_remote();f=self.fixture
        self.server.gateway.asr.transcribe_with_confidence.return_value=('đặt máy lạnh 24 độ',.9)
        await self.session.voice.process(self.session,self.session.voice.user,f.sub,f.action,'c'*32,b'\0\0'*1600,time.monotonic())
        self.assertEqual(len(self.transmissions),1)
        state=bytes.fromhex(panasonic_seed(decode(self.transmissions[-1]['data'],36700)))
        self.assertEqual((state[14]>>1)&31,24);self.assertEqual(state[13]&1,1)
        self.assertTrue(any(r.get('verify')=='ack_only' and r.get('delivery')=='ir_sent' and '24 độ' in r.get('voice_reply','') for r in self.results))
        for _ in range(2):await self.session.voice.execute(self.session,self.session.voice.user,f.sub,f.action,'tăng nhiệt độ máy lạnh 1 độ','d'*32)
        self.assertEqual(len(self.transmissions),2)
        settings=json.loads(self.ir.remote(self.remote['remote_id'])['settings']);self.assertEqual(settings['temperature'],25)
        await self.session.voice.execute(self.session,self.session.voice.user,f.sub,f.action,'tắt điều hòa','e'*32)
        state=bytes.fromhex(panasonic_seed(decode(self.transmissions[-1]['data'],36700)));self.assertEqual(state[13]&1,0)

    async def test_other_room_and_ambiguous_relay_names_never_emit_ir(self):
        await self.prepare_remote();f=self.fixture
        with self.assertRaises(CoreError):await self.session.voice.execute(self.session,self.session.voice.user,f.sub,999,'bật máy lạnh','a'*32)
        f.r.db.execute('UPDATE devices SET name=? WHERE device_id=?',('Máy lạnh',self.device['device_id']))
        with self.assertRaises(CoreError):await self.session.voice.execute(self.session,self.session.voice.user,f.sub,f.action,'bật máy lạnh','b'*32)
        self.assertEqual(self.transmissions,[])

    async def test_learned_power_frame_does_not_invent_a_temperature_baseline(self):
        await self.prepare_remote();f=self.fixture
        rid=self.remote['remote_id']
        self.ir.r.db.execute('UPDATE ir_remotes SET seed=NULL WHERE remote_id=?',(rid,))
        self.ir.r.db.execute('INSERT INTO ir_learned VALUES(?,?,?,?,?)',(rid,'on','Bật',38000,encode(nec(16,2),38000)))
        await self.ir.for_user(f.owner,'POST','/api/v1/ir/remotes/'+rid+'/send',{'state':{'power':True},'idempotency_key':'learned_power_on'})
        with self.assertRaises(CoreError) as error:
            await self.session.voice.execute(self.session,self.session.voice.user,f.sub,f.action,'tăng nhiệt độ máy lạnh 1 độ','f'*32)
        self.assertEqual(error.exception.code,'ir_temperature_unknown');self.assertEqual(len(self.transmissions),1)

del _Fixture

