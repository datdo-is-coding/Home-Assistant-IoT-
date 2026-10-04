"""Offline PCM relay -> Pi ASR/NLU -> MQTT regression checks."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer
from intent_engine import IntentEngine
from mqtt_handler import MQTTHandler
from verify_engine import CommandVerifier


class Socket:
    remote_address = ('test', 0)
    open = True

    def __init__(self, messages=()):
        self.messages = iter(messages)
        self.sent = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.messages)
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, message):
        self.sent.append(message if isinstance(message, bytes) else json.loads(message))


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

    async def test_sound_effects_also_skip_capture_only_sockets(self):
        server = AudioServer()
        ws = Socket()
        ws.has_speaker = False
        ws.audio_relay = True
        await server._broadcast_pcm_stream([ws], b'\x00\x00' * 160)
        await server._send_audio_stream_mp3(ws, b'not-needed')
        self.assertEqual(ws.sent, [])


if __name__ == '__main__':
    unittest.main()
