import asyncio
import json
import hmac
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from gateway.core_v1.speaker_voice import SpeakerVoiceSession
from gateway.core_v1.kws import CoreKws
from gateway.core_v1.registry import CoreError
from gateway.core_v1.firebase_commissioning import CoreCommissioning
from test_hc_registry import RegistryTest
from asr_engine import ASREngine
from audio_server import AudioServer


class PiSpeakerVoiceTests(IsolatedAsyncioTestCase):
    _Fixture=RegistryTest
    def setUp(self):
        self.fixture = self._Fixture();self.fixture.setUp();f=self.fixture
        self.device=f.bind();f.online(f.sub,200);f.online(f.action);f.report()
        self.socket=SimpleNamespace(send=AsyncMock())
        self.server=SimpleNamespace(
            gateway=SimpleNamespace(asr=SimpleNamespace(transcribe_with_confidence=Mock(return_value=('bật đèn',.9)))),
            _asr_lock=asyncio.Lock(),_is_ws_alive=lambda ws:True,
            _is_token_valid=lambda token,node:token=='valid',_send_voice_reply=AsyncMock())
        self.core=SimpleNamespace(r=f.r,users={'uid':'installer'},kws=CoreKws(f.r))
        self.core.r.db.execute('INSERT INTO users VALUES(?,?,?)',('CONTROL-installer','Pi control','unused'))
        self.core.r.db.execute('INSERT INTO home_members VALUES(?,?,?)',(f.home,'CONTROL-installer','Member'))
        self.session=SpeakerVoiceSession(self.server,self.socket,self.core,f.sub,'SB1','valid')

    def tearDown(self):
        self.fixture.tearDown()

    async def start(self):
        await self.session.text(dict(type='start',codec='pcm',sample_rate=16000,
                                     source_node_id=self.fixture.action,request_id='a'*32))

    async def test_pcm_does_not_actuate_before_stop_and_feedback_waits_for_ack(self):
        await self.start();self.session.audio(b'\0\0'*16000)
        self.assertEqual(self.fixture.r.db.execute('SELECT count(*) FROM commands').fetchone()[0],0)
        async def result(*args):
            await self.session.send_json(dict(type='command_result',verify='success',voice_reply='Đã thực hiện lệnh.'))
        self.session.voice.wait_result=AsyncMock(side_effect=result)
        await self.session.text(dict(type='stop'));await self.session.processing
        command=self.fixture.r.db.execute('SELECT * FROM commands').fetchone()
        self.assertEqual(command['status'],'ACCEPTED')
        self.session.voice.wait_result.assert_awaited_once()
        self.server._send_voice_reply.assert_awaited_once()
        self.assertTrue(any(json.loads(c.args[0]).get('has_tts') is True for c in self.socket.send.await_args_list))
        self.assertTrue(any(json.loads(c.args[0]).get('type')=='transcript' for c in self.socket.send.await_args_list))

    async def test_source_rejection_cancel_and_packet_bounds(self):
        with self.assertRaises(CoreError):
            await self.session.text(dict(type='start',codec='pcm',sample_rate=16000,source_node_id=999,request_id='a'*32))
        await self.start()
        with self.assertRaises(CoreError):self.session.audio(b'x')
        self.session.audio(b'\0\0'*200)
        await self.session.text(dict(type='cancel'));await self.session.text(dict(type='stop'))
        self.assertIsNone(self.session.processing)
        self.assertEqual(self.fixture.r.db.execute('SELECT count(*) FROM commands').fetchone()[0],0)

    async def test_revoked_socket_is_not_accepted(self):
        await self.start();self.server._is_token_valid=lambda *args:False
        with self.assertRaises(CoreError):self.session.audio(b'\0\0'*160)
        await self.session.close()

    async def test_existing_primary_light_binding_resolves_multiple_lights(self):
        f=self.fixture
        f.r.create_device(f.owner,f.home,'Secondary','light','HC-001122334402:CH3')
        self.core.kws.configure(f.owner,f.home,dict(revision=0,
            sources=[dict(node_id='SB001122334401',room='BEDROOM')],
            bindings=[dict(node_id='AB001122334402',channel=1,room='BEDROOM',device='LIGHT')]))
        device,on=self.session.voice.resolve(self.session.voice.user,f.sub,f.action,'bật đèn')
        self.assertEqual(device,self.device['device_id']);self.assertTrue(on)
        device,on=self.session.voice.resolve(self.session.voice.user,f.sub,f.action,'tắt secondary')
        self.assertFalse(on);self.assertNotEqual(device,self.device['device_id'])

    async def test_authenticated_wss_protocol_reaches_core_ack(self):
        f=self.fixture
        self.core.home=f.home
        node='SB001122334401'
        token=hmac.digest(f.keys[f.sub],b'HC-SPEAKER-V1\0','sha256').hex()
        messages=[json.dumps(dict(t='hello',id=node,speaker=True,playback_only=False)),
                  json.dumps(dict(type='start',codec='pcm',sample_rate=16000,source_node_id=f.action,request_id='b'*32)),
                  b'\0\0'*1600,json.dumps(dict(type='stop'))]
        class Socket:
            open=True;closed=False;remote_address=('test',0)
            request_headers={'Authorization':'Bearer '+token,'X-Device-ID':node}
            transport=SimpleNamespace(get_extra_info=lambda key:object())
            sent=[]
            async def __aiter__(self):
                for message in messages:
                    yield message
                    await asyncio.sleep(.02)
                await asyncio.sleep(.2)
            async def send(self,value):self.sent.append(json.loads(value))
            async def close(self,*args):self.open=False;self.closed=True
        gateway=SimpleNamespace(firebase_commissioning=SimpleNamespace(core=self.core),
                                local_kws_enabled=False,asr=self.server.gateway.asr)
        server=AudioServer(gateway);server._send_voice_reply=AsyncMock()
        async def ack():
            for _ in range(100):
                command=f.r.db.execute('SELECT * FROM commands').fetchone()
                if command:
                    f.r.ack(f.action,command['command_id'],'APPLIED',command['config_rev'],True)
                    return
                await asyncio.sleep(.01)
        socket=Socket()
        await asyncio.gather(server._handle_client(socket),ack())
        self.assertTrue(any(r.get('verify')=='success' for r in socket.sent),socket.sent)
        server._send_voice_reply.assert_awaited_once()

    async def test_reconfigure_name_type_aliases_and_stale_command_are_consistent(self):
        f=self.fixture;cloud=CoreCommissioning(f.r,{'home_id':f.home},['account'])
        pending=self.session.voice.submit(self.session.voice.user,f.sub,f.action,'bật đèn','e'*32)
        result=cloud.request('account','POST','/api/device/update',{'device_id':'AB001122334402',
            'ch1_name':'Máy pha cà phê','ch1_type':'custom','ch1_aliases':['máy cà phê']})
        self.assertEqual(f.r.get_command(self.session.voice.user,pending['command_id'])['status'],'FAILED')
        self.assertTrue(result['success']);f.report(seq=2)
        for phrase in ('bật máy pha cà phê','tắt máy cà phê'):
            target,on=self.session.voice.resolve(self.session.voice.user,f.sub,f.action,phrase)
            self.assertEqual(target,self.device['device_id'])
        with self.assertRaises(CoreError):self.session.voice.resolve(self.session.voice.user,f.sub,f.action,'bật light')
        with self.assertRaises(CoreError):self.session.voice.resolve(self.session.voice.user,f.sub,f.action,'bật đèn')
        projection=cloud.projections('account')['AB001122334402']['channels']['ch1']
        self.assertEqual(projection['aliases'],['máy cà phê']);self.assertEqual(projection['device_type'],'custom')
        for kind in ('den','quat','o_cam','air_conditioner','custom'):
            cloud.request('account','POST','/api/device/update',{'device_id':'AB001122334402','ch1_type':kind})
        for aliases in ('not-a-list',[None],['x']*9):
            with self.assertRaises(CoreError):cloud.request('account','POST','/api/device/update',{
                'device_id':'AB001122334402','ch1_aliases':aliases})

    async def test_alias_ambiguity_never_uses_primary_light_fallback(self):
        f=self.fixture;cloud=CoreCommissioning(f.r,{'home_id':f.home},['account'])
        cloud.request('account','POST','/api/device/update',{'device_id':'AB001122334402',
            'ch1_aliases':['đèn'],'ch2_name':'Other','ch2_type':'custom','ch2_aliases':['đèn']})
        with self.assertRaises(CoreError) as error:
            self.session.voice.resolve(self.session.voice.user,f.sub,f.action,'bật đèn')
        self.assertEqual(error.exception.code,'voice_ambiguous')


class ASRCorrectionTests(TestCase):
    def test_scoped_names_have_equal_keyword_weight_without_accepting_quiet_or_negated_commands(self):
        engine=ASREngine();vocabulary=['Máy pha cà phê','máy cà phê']
        for text in ('bật máy pha cà phê','tắt máy cà phê'):
            self.assertAlmostEqual(engine._estimate_confidence(text,text,5,.025,vocabulary=vocabulary),.8)
            self.assertLess(engine._estimate_confidence(text,text,5,.007,vocabulary=vocabulary),.7)
        self.assertFalse(engine._known_command('không bật máy cà phê',vocabulary))
        self.assertFalse(engine._known_command('bật máy khác',vocabulary))
    def test_noncommands_do_not_become_actions(self):
        engine=ASREngine()
        for text in ('bạn bè','ban đêm','đêm qua','ban đêm không ngủ','bất quá','không bật đèn'):
            corrected=engine._phonetic_correct(text)
            self.assertFalse(corrected.startswith(('bật ','tắt ')),corrected)

del RegistryTest
