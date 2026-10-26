import asyncio
import json
import time
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from registry_manager import RegistryManager
from kws_service import KwsService


class LocalKwsGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.registry = RegistryManager(registry_path=str(Path(tmp.name)/'missing'), db_path=str(Path(tmp.name)/'db'))
        self.sb = 'SB001122334455'; self.ab = 'AB112233445566'
        self.registry.data['nodes'] = {
            self.sb: {'status':'online', 'owner_epoch':1},
            self.ab: {'status':'online','hardware_uid':self.ab[2:],'subbox_id':self.sb,
                      'owner_epoch':2,'desired_config_version':3,'channels':{'ch3':{'name':'Đèn bàn'}}}}
        self.gateway = SimpleNamespace(registry=self.registry, mqtt=SimpleNamespace(publish=AsyncMock(return_value=True)),
            audio_server=SimpleNamespace(speak_kws=AsyncMock(return_value=True)), broadcast_event=Mock(),
            process_voice_command=AsyncMock())
        self.service = KwsService(self.gateway)
        self.addAsyncCleanup(self.service.stop)

    def body(self):
        return {'revision':self.service.get_config()['revision'], 'sources':[{'node_id':self.ab,'room':'BEDROOM'}],
                'bindings':[{'node_id':self.ab,'channel':3,'room':'BEDROOM','device':'LIGHT'}]}

    def event(self, **changes):
        return dict(schema_version=1,issued_at=int(time.time()),session_id=11,request_id=12,origin_node=self.ab,target_node=self.ab,
                    target_subbox=self.sb,channel=3,action='TURN_ON',state='ON',status='success',reason='ok',follow_up=False, **changes)

    async def test_config_persists_exact_identity_ack_and_stale_revision(self):
        saved = await self.service.set_config(self.body())
        self.assertEqual(saved['bindings'][0]['hardware_uid'], self.ab[2:])
        self.assertEqual(saved['sources'][0]['owner_epoch'], 2)
        self.assertEqual(saved['sync'][self.sb]['status'], 'pending')
        topic, payload = self.gateway.mqtt.publish.call_args.args
        self.assertEqual(topic, f'home/subbox/{self.sb}/command')
        self.assertEqual(payload['cmd'], 'KWS_CONFIG')
        other = KwsService(self.gateway)
        self.assertEqual(other.get_config()['revision'], saved['revision'])
        with self.assertRaisesRegex(ValueError, 'revision_conflict'):
            await self.service.set_config({'revision':0,'bindings':[],'sources':[]})
        await self.service.on_config_ack(f'home/subbox/{self.sb}/event/kws_config', {'revision':saved['revision'],'status':'applied'})
        self.assertEqual(self.service.get_config()['sync'][self.sb]['status'], 'applied')
        self.registry.data['nodes'][self.ab]['owner_epoch'] += 1
        self.assertEqual(self.service.get_config()['bindings'], [])
        self.assertEqual(self.service.get_config()['sources'], [])

    async def test_invalid_config_does_not_overwrite(self):
        for change in ({'channel':True}, {'channel':4}, {'node_id':'ABbad'}, {'device':'PUMP'}):
            body = self.body(); body['bindings'][0].update(change)
            with self.assertRaises(ValueError): await self.service.set_config(body)
        body = self.body(); body['bindings'] *= 2
        with self.assertRaises(ValueError): await self.service.set_config(body)
        self.assertEqual(self.service.get_config()['revision'], 0)

    async def test_result_validates_origin_target_deduplicates_without_redispatch(self):
        await self.service.set_config(self.body())
        topic = f'home/subbox/{self.sb}/event/kws_result'
        self.assertTrue(await self.service.on_result(topic, self.event()))
        self.assertFalse(await self.service.on_result(topic, self.event()))
        await self.service.drain()
        self.gateway.audio_server.speak_kws.assert_awaited_once()
        args = self.gateway.audio_server.speak_kws.call_args.args
        self.assertEqual(args[0], self.sb)
        self.assertIn('relay', args[1].lower())
        self.gateway.process_voice_command.assert_not_called()
        for bad in ({'origin_node':'ABFFFFFFFFFFFF'}, {'state':'OFF'}, {'channel':1}, {'session_id':True}, {'follow_up':True}):
            event = self.event(); event.update(bad); event['request_id'] += 1
            self.assertFalse(await self.service.on_result(topic, event), bad)

    async def test_bounded_queue_and_expired_response(self):
        await self.service.set_config(self.body())
        self.service.max_pending = 1
        gate = asyncio.Event()
        async def wait_for_gate(*args): await gate.wait()
        self.gateway.audio_server.speak_kws.side_effect = wait_for_gate
        self.assertTrue(await self.service.on_result(f'home/subbox/{self.sb}/event/kws_result',self.event()))
        event=self.event();event['request_id']+=1
        self.assertFalse(await self.service.on_result(f'home/subbox/{self.sb}/event/kws_result',event))
        gate.set();await self.service.drain()

    async def test_speaker_only_playback_and_missing_speaker_never_falls_back(self):
        from audio_server import AudioServer
        self.gateway.tts = SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'\0' * 320))
        audio = AudioServer(self.gateway)
        class Socket:
            def __init__(self, node): self.node_id=node; self.has_speaker=True; self.sent=[]
            async def send(self, message): self.sent.append(json.loads(message) if isinstance(message,str) else message)
        origin = Socket(self.sb); other = Socket('SBFFFFFFFFFFFF')
        audio._ws_nodes = {self.sb:origin, other.node_id:other}
        audio._active_speakers = {origin,other}
        event=self.event();event.update(status='incomplete',reason='missing_device',follow_up=True)
        self.assertTrue(await audio.speak_kws(self.sb, 'Bạn muốn đèn hay quạt?', event, asyncio.Semaphore(2)))
        self.assertEqual(other.sent, [])
        self.assertEqual(origin.sent[-1]['type'], 'kws_playback_done')
        self.assertEqual(origin.sent[-1]['request_id'], 12)
        self.assertFalse(any(isinstance(m,dict) and 'follow_up_command' in m for m in origin.sent))
        del audio._ws_nodes[self.sb]
        self.assertFalse(await audio.speak_kws(self.sb,'x',event,asyncio.Semaphore(2)))
        self.assertEqual(other.sent, [])

    async def test_local_mode_rejects_legacy_voice_dispatch(self):
        from main import SmartHomeGateway
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.local_kws_enabled = True
        gateway.process_voice_command = AsyncMock()
        gateway._subbox_voice_requests = {}
        gateway.mqtt = self.gateway.mqtt
        await gateway._on_subbox_voice(f'home/subbox/{self.sb}/voice/request',{'text':'bật đèn','origin_node':self.ab,'request_id':1})
        gateway.process_voice_command.assert_not_called()

        from audio_server import AudioServer
        self.gateway.local_kws_enabled = True
        self.gateway.asr = None
        audio = AudioServer(self.gateway)
        class Socket:
            def __init__(self): self.sent = []
            async def send(self, message): self.sent.append(json.loads(message))
        ws = Socket()
        await audio._process_audio(ws, [0.0] * 160, 16000, self.sb)
        self.assertEqual(ws.sent, [{"type": "transcript", "text": "", "accepted": False, "reason": "local_kws"}])
        self.gateway.process_voice_command.assert_not_called()

    async def test_expired_or_undated_result_is_not_replayed_after_reconnect(self):
        await self.service.set_config(self.body())
        topic = f'home/subbox/{self.sb}/event/kws_result'
        for issued in (None, 0, True, int(time.time())-16, int(time.time())+10):
            event = self.event()
            if issued is None: event.pop('issued_at')
            else: event['issued_at'] = issued
            self.assertFalse(await self.service.on_result(topic, event), issued)
        self.assertEqual(len(self.service._tasks), 0)

    async def test_kws_and_proactive_playback_share_same_speaker_lock(self):
        from audio_server import AudioServer
        gate = asyncio.Event()
        started = asyncio.Event()
        class Socket:
            node_id = self.sb
            has_speaker = True
            def __init__(self): self.starts = 0
            async def send(self, message):
                if isinstance(message, str) and json.loads(message).get('type') == 'audio_start':
                    self.starts += 1
                    started.set()
                    if self.starts == 1: await gate.wait()
        ws = Socket()
        audio = AudioServer(self.gateway)
        audio._ws_nodes = {self.sb:ws}
        audio._active_speakers = {ws}
        first = asyncio.create_task(audio._broadcast_pcm_stream([ws], b'\0'*320, kws_result=self.event()))
        await started.wait()
        second = asyncio.create_task(audio._broadcast_pcm_stream([ws], b'\0'*320, broadcast=True))
        try:
            await asyncio.sleep(0.02)
            self.assertEqual(ws.starts, 1)
        finally:
            gate.set()
            await asyncio.gather(first, second)
        self.assertEqual(ws.starts, 2)

    async def test_unconfigured_gateway_never_sends_invalid_revision_zero(self):
        # An old revision-zero ACK must not turn an unconfigured device into an error.
        self.service._config['sync'][self.sb] = {'revision':0, 'status':'error'}
        await self.service.sync_config(self.sb)
        self.gateway.mqtt.publish.assert_not_awaited()
        self.assertEqual(self.service.get_config()['sync'], {})
        self.assertFalse(await self.service.on_config_ack(
            f'home/subbox/{self.sb}/event/kws_config', {'revision':0, 'status':'error'}))
        self.assertEqual(self.service.get_config()['sync'], {})
