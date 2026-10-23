"""Offline PCM relay -> Pi ASR/NLU -> MQTT regression checks."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer
from intent_engine import IntentEngine
from mqtt_handler import MQTTHandler
from verify_engine import CommandVerifier

class Socket:
    remote_address = ('test', 0)
    open = True

    def __init__(self, messages=(), headers=None, path=""):
        self.messages = iter(messages)
        self.sent = []
        self.headers = headers or {}
        self.path = path
        self.closed = False
        self.close_code = None
        self.close_reason = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.messages)
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, message):
        self.sent.append(message if isinstance(message, bytes) else json.loads(message))

    async def close(self, code=1000, reason=""):
        self.open = False
        self.closed = True
        self.close_code = code
        self.close_reason = reason

class AudioRelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_subbox_audio_socket_never_receives_relay_commands(self):
        server = AudioServer()
        ws = Socket([json.dumps({'type': 'start', 'node_id': 'AB123',
                                'speaker': False, 'audio_relay': True,
                                'asr_only': False})])
        await server._handle_client(ws)
        self.assertFalse(server.has_ws('AB123'))
        self.assertFalse(await server.send_relay_ws('AB123', 'ch1', 'turn_on', 1))
        self.assertFalse(any(message.get('t') == 'rl' for message in ws.sent))

    async def test_light_and_fan_on_off_are_parsed_on_pi_and_sent_over_mqtt(self):
        for phrase, channel, command in [('bật đèn', 1, 'TURN_ON'),
                                         ('tắt đèn', 1, 'TURN_OFF'),
                                         ('bật quạt', 2, 'TURN_ON'),
                                         ('tắt quạt', 2, 'TURN_OFF')]:
            with self.subTest(phrase=phrase):
                mqtt = MQTTHandler()
                await mqtt._on_actionbox('home/subbox/SB1/event/actionbox', {
                    'node_id': 'AB123', 'hardware_uid': 'AABBCCDDEEFF',
                    'protocol_version': 3, 'config_version': 1,
                })
                published = []

                async def publish(topic, payload, **kwargs):
                    published.append((topic, payload))
                    return True

                mqtt.publish = publish
                engine = IntentEngine()
                observed = []
                gateway = SimpleNamespace(
                    asr=SimpleNamespace(transcribe_with_confidence=lambda *args: (phrase, 0.99)),
                    registry=SimpleNamespace(get_all_nodes=lambda: {'AB123': {'room': 'phong_ngu'}}),
                )
                server = AudioServer(gateway)
                verifier = CommandVerifier(mqtt, gateway.registry)
                verifier.audio_server = server

                async def process(text, client_node_id, detected_room):
                    observed.append((text, client_node_id, detected_room))
                    intent = await engine.extract(text, session_key=client_node_id)
                    cmd = intent['command']
                    ch = 'ch1' if cmd['device'] == 'light' else 'ch2'
                    await verifier.execute_action('AB123', ch, cmd['action'], seq=7)
                    return {'verify': 'ack_only'}

                gateway.process_voice_command = process
                ws = Socket([json.dumps({'type': 'start', 'node_id': 'AB123',
                                        'codec': 'pcm', 'sample_rate': 16000,
                                        'speaker': False, 'audio_relay': True,
                                        'asr_only': False}),
                             b'\x10\x00' * 1600, json.dumps({'type': 'stop'})])
                await server._handle_client(ws)
                self.assertEqual(observed, [(phrase, 'AB123', 'phong_ngu')])
                self.assertEqual(len(published), 1)
                topic, payload = published[0]
                self.assertEqual(topic, 'home/subbox/SB1/command')
                self.assertEqual((payload['channel'], payload['cmd']), (channel, command))
                self.assertFalse(any(message.get('t') == 'rl' for message in ws.sent))

    async def test_low_confidence_audio_never_dispatches(self):
        gateway = SimpleNamespace(
            asr=SimpleNamespace(transcribe_with_confidence=lambda *args: ('bật đèn', 0.01)),
            process_voice_command=AsyncMock(),
        )
        server = AudioServer(gateway)
        server._send_voice_reply = AsyncMock()
        ws = Socket()
        ws.audio_relay = True
        await server._process_audio(ws, [0] * 160, 16000, client_node_id='AB123')
        self.assertFalse(ws.sent[0]['accepted'])
        gateway.process_voice_command.assert_not_awaited()

    async def test_cancelled_or_duplicate_stop_never_executes_audio_twice(self):
        for ending, expected in [('cancel', 0), ('stop', 1)]:
            with self.subTest(ending=ending):
                server = AudioServer()
                server._process_audio = AsyncMock()
                ws = Socket([json.dumps({'type': 'start', 'node_id': 'AB123', 'audio_relay': True}),
                             b'\x10\x00' * 160,
                             json.dumps({'type': ending}), json.dumps({'type': 'stop'})])
                await server._handle_client(ws)
                self.assertEqual(server._process_audio.await_count, expected)

    async def test_capture_only_node_gets_result_without_unplayable_audio(self):
        for audio_format in ('pcm', 'mp3'):
            with self.subTest(audio_format=audio_format):
                gateway = SimpleNamespace(
                    asr=SimpleNamespace(transcribe_with_confidence=lambda *args: ('tắt đèn', 0.99)),
                    process_voice_command=AsyncMock(return_value={
                        'verify': 'ack_only', 'tts_audio': b'\x00\x00' * 160,
                        'tts_format': audio_format,
                    }),
                )
                server = AudioServer(gateway)
                ws = Socket()
                ws.has_speaker = False
                ws.audio_relay = True
                await server._process_audio(ws, [0] * 160, 16000, client_node_id='AB123')
                self.assertEqual([message['type'] for message in ws.sent if isinstance(message, dict)],
                                 ['transcript', 'command_result'])
                self.assertFalse(any(isinstance(message, bytes) for message in ws.sent))

    async def test_subbox_registered_with_speaker_and_retained(self):
        server = AudioServer()
        ws = Socket([
            json.dumps({'t': 'hello', 'id': 'subbox_livingroom', 'speaker': True, 'audio_relay': True}),
            json.dumps({'type': 'start', 'node_id': 'subbox_livingroom'}),
            json.dumps({'type': 'cancel'}),
        ])
        await server._handle_client(ws)
        self.assertTrue(ws.has_speaker)
        self.assertIn(ws, server._active_speakers)

    async def test_audio_reply_routed_to_active_subbox_speaker_when_caller_has_no_speaker(self):
        server = AudioServer()
        ws_sb = Socket()
        ws_sb.has_speaker = True
        ws_sb.node_id = 'subbox_livingroom'
        server._active_speakers.add(ws_sb)

        ws_ab = Socket()
        ws_ab.has_speaker = False
        ws_ab.node_id = 'AB123'

        pcm_sample = b'\x00\x00' * 160
        await server._send_pcm_stream(ws_ab, pcm_sample)

        self.assertTrue(any(isinstance(m, dict) and m.get('type') == 'audio_start' for m in ws_sb.sent))
        self.assertTrue(any(isinstance(m, bytes) for m in ws_sb.sent))

        self.assertFalse(any(isinstance(m, bytes) for m in ws_ab.sent))

    async def test_ws_auth_rejected_when_token_configured_and_missing(self):
        import config
        orig_token = config.WS_AUDIO_TOKEN
        config.WS_AUDIO_TOKEN = "secret_ws_token_123"
        try:
            server = AudioServer()
            ws = Socket([json.dumps({'t': 'hello', 'id': 'SB1'})])
            await server._handle_client(ws)
            self.assertTrue(ws.closed)
            self.assertEqual(ws.close_code, 1008)
            self.assertTrue(any(m.get('error') == 'unauthorized' for m in ws.sent if isinstance(m, dict)))
        finally:
            config.WS_AUDIO_TOKEN = orig_token

    async def test_ws_auth_accepted_with_token_in_hello(self):
        import config
        orig_token = config.WS_AUDIO_TOKEN
        config.WS_AUDIO_TOKEN = "secret_ws_token_123"
        try:
            server = AudioServer()
            ws = Socket([json.dumps({'t': 'hello', 'id': 'SB1', 'token': 'secret_ws_token_123'})])
            await server._handle_client(ws)
            self.assertFalse(ws.closed)
            self.assertTrue(ws.authenticated)
            self.assertEqual(server._ws_nodes.get('SB1'), ws)
        finally:
            config.WS_AUDIO_TOKEN = orig_token

    async def test_ws_auth_accepted_with_bearer_header(self):
        import config
        orig_token = config.WS_AUDIO_TOKEN
        config.WS_AUDIO_TOKEN = "secret_ws_token_123"
        try:
            server = AudioServer()
            ws = Socket(
                [json.dumps({'t': 'hello', 'id': 'SB1'})],
                headers={'Authorization': 'Bearer secret_ws_token_123'}
            )
            await server._handle_client(ws)
            self.assertFalse(ws.closed)
            self.assertTrue(ws.authenticated)
            self.assertEqual(server._ws_nodes.get('SB1'), ws)
        finally:
            config.WS_AUDIO_TOKEN = orig_token

    async def test_spoofed_compact_ack_is_rejected(self):
        gateway = SimpleNamespace(
            mqtt=SimpleNamespace(record_compact_ack=Mock()),
            registry=SimpleNamespace(update_relay_state=Mock(), update_heartbeat=Mock()),
            broadcast_event=Mock()
        )
        server = AudioServer(gateway)
        ws = Socket([
            json.dumps({'t': 'hello', 'id': 'SB1'}),
            json.dumps({'t': 'ack', 'id': 'AB_SPOOFED', 'rl': [1, 0, 0], 'seq': 42}),
        ])
        await server._handle_client(ws)
        gateway.mqtt.record_compact_ack.assert_not_called()
        gateway.registry.update_relay_state.assert_not_called()

    async def test_duplicate_identity_closes_previous_socket(self):
        server = AudioServer()
        ws1 = Socket([json.dumps({'t': 'hello', 'id': 'SB1'})])
        ws1.open = True
        await server._handle_client(ws1)
        self.assertEqual(server._ws_nodes.get('SB1'), ws1)

        ws2 = Socket([json.dumps({'t': 'hello', 'id': 'SB1'})])
        await server._handle_client(ws2)
        self.assertTrue(ws1.closed)
        self.assertEqual(server._ws_nodes.get('SB1'), ws2)

if __name__ == '__main__':
    unittest.main()

class RegisteredRelayTests(unittest.IsolatedAsyncioTestCase):
    def make_server(self, parent='SB1', status='online', pending=False):
        self.nodes = {
            'SB1': {'status': 'online'},
            'AB1': {'status': status, 'subbox_id': parent, 'owner_epoch': 6, 'room': 'bedroom'},
            'AB2': {'status': 'online', 'subbox_id': 'SB1', 'owner_epoch': 2, 'room': 'kitchen'},
        }
        registry = SimpleNamespace(
            get_all_nodes=lambda: self.nodes,
            get_pending=lambda: {'AB1': {}} if pending else {},
            on_hello=lambda *a, **k: {'node_id': 'SB1', 'action': 'known'},
            get_provision_payload=lambda *a: {},
        )
        server = AudioServer(SimpleNamespace(registry=registry))
        server._process_audio = AsyncMock()
        return server

    def messages(self, source='AB1'):
        return [json.dumps({'t': 'hello', 'id': 'SB1', 'speaker': True, 'audio_relay': True}),
                json.dumps({'type': 'start', 'node_id': source, 'audio_relay': True, 'speaker': False}),
                b'\x10\x00'*160, json.dumps({'type': 'stop'})]

    async def test_registered_children_keep_source_and_parent_speaker_identity(self):
        server = self.make_server()
        ws = Socket(self.messages())
        await server._handle_client(ws)
        server._process_audio.assert_awaited_once()
        self.assertEqual(server._process_audio.call_args.kwargs['client_node_id'], 'AB1')
        self.assertEqual(server._process_audio.call_args.kwargs['detected_room'], 'bedroom')
        self.assertEqual(ws.client_node_id, 'SB1')
        self.assertEqual(ws.node_id, 'SB1')
        self.assertTrue(ws.has_speaker)
        await server._send_pcm_stream(ws, b'\x00\x00'*160)
        self.assertTrue(any(isinstance(m,bytes) for m in ws.sent))

    async def test_unknown_foreign_pending_or_revoked_source_is_rejected(self):
        for parent,status,pending,source in [('SB2','online',False,'AB1'),
                                             ('SB1','online',False,'unknown'),
                                             ('SB1','NEEDS_REPROVISION',False,'AB1'),
                                             ('SB1','online',True,'AB1')]:
            with self.subTest(parent=parent,status=status,pending=pending,source=source):
                server=self.make_server(parent,status,pending)
                ws=Socket(self.messages(source))
                await server._handle_client(ws)
                server._process_audio.assert_not_awaited()
                self.assertTrue(any(isinstance(m,dict) and m.get('error')=='forbidden' for m in ws.sent))

    async def test_ownership_changed_mid_recording_prevents_execution(self):
        server=self.make_server()
        owner=self
        class RevokedSocket(Socket):
            async def __anext__(self):
                message=await super().__anext__()
                if isinstance(message,str) and json.loads(message).get('type')=='stop':
                    owner.nodes['AB1']['owner_epoch']=7
                return message
        ws=RevokedSocket(self.messages())
        await server._handle_client(ws)
        server._process_audio.assert_not_awaited()

class VoiceReplyFormatTests(unittest.IsolatedAsyncioTestCase):
    async def test_silent_followup_closes_instead_of_opening_mic_forever(self):
        import time
        gateway = SimpleNamespace(asr=SimpleNamespace(transcribe_with_confidence=lambda *args: ('', 0)),
                                  dialog=SimpleNamespace(clear_session=Mock()))
        server = AudioServer(gateway)
        server._followup_pending['AB1'] = time.monotonic() + 30
        server._send_voice_reply = AsyncMock()
        await server._process_audio(Socket(), [0]*160, 16000, client_node_id='AB1')
        gateway.dialog.clear_session.assert_called_once_with('AB1')
        server._send_voice_reply.assert_not_awaited()

    async def test_followup_listen_is_only_sent_after_pcm_to_registered_source(self):
        nodes = {'SB1': {}, 'AB1': {'subbox_id': 'SB1', 'status': 'online'}}
        gateway = SimpleNamespace(registry=SimpleNamespace(get_all_nodes=lambda: nodes,
            get_pending=lambda: {}), mqtt=SimpleNamespace(node_identities={
                'AB1': {'hardware_uid': '001122334455', 'config_version': 1}}, session_id=12))
        server = AudioServer(gateway)
        ws = Socket(); ws.node_id = 'SB1'; ws.has_speaker = True
        await server._send_pcm_stream(ws, b'\0\0'*160, follow_up=True, follow_up_node_id='AB1')
        end = next(m for m in ws.sent if isinstance(m, dict) and m.get('type') == 'audio_end')
        command = json.loads(end['follow_up_command'])
        self.assertEqual(command['cmd'], 'LISTEN_FOLLOWUP')
        self.assertEqual(command['node_id'], 'AB1')
        self.assertGreater(ws.sent.index(end), next(i for i,m in enumerate(ws.sent) if isinstance(m, bytes)))
        nodes['AB1']['subbox_id'] = 'SB2'
        ws.sent.clear()
        await server._send_pcm_stream(ws, b'\0\0'*160, follow_up=True, follow_up_node_id='AB1')
        end = next(m for m in ws.sent if isinstance(m,dict) and m.get('type') == 'audio_end')
        self.assertNotIn('follow_up_command', end)

    async def test_cancel_and_unknown_reply_are_pcm_not_encoded_audio(self):
        from main import SmartHomeGateway
        from dialog_manager import DialogManager
        for phrase in ('hủy', 'xin chào'):
            with self.subTest(phrase=phrase):
                gateway=SmartHomeGateway.__new__(SmartHomeGateway)
                gateway.dialog=DialogManager()
                gateway.intent=IntentEngine()
                gateway.tts=SimpleNamespace(synthesize=AsyncMock(return_value=b'RIFFencoded-wave'),
                                            synthesize_pcm=AsyncMock(return_value=b'\x01\x00'*160))
                gateway.broadcast_event=Mock()
                result=await gateway.process_voice_command(phrase,client_node_id='AB1')
                self.assertEqual(result['tts_audio'],b'\x01\x00'*160)
                gateway.tts.synthesize.assert_not_awaited()

    async def test_local_tts_is_initialized_before_audio_server_accepts_speech(self):
        from main import SmartHomeGateway
        from unittest.mock import patch
        import config
        gateway=SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry=SimpleNamespace(inventory_for_prompt=lambda:'')
        gateway.asr=SimpleNamespace(initialize=Mock())
        warmed=[]
        async def initialize():warmed.append(True)
        async def start_audio():
            self.assertTrue(warmed)
            raise RuntimeError('stop after readiness check')
        gateway.tts=SimpleNamespace(vieneu=SimpleNamespace(initialize=initialize))
        gateway.audio_server=SimpleNamespace(start=start_audio)
        with patch.object(config,'TTS_PROVIDER','vieneu'):
            with self.assertRaisesRegex(RuntimeError,'readiness check'):
                await gateway.start()
