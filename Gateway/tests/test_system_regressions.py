"""Run offline: python -m unittest discover -s Gateway/tests -p test_system_regressions.py"""
import asyncio
from collections import OrderedDict
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer
from intent_engine import IntentEngine
from tts_engine import TTSEngine
from mqtt_handler import MQTTHandler
from verify_engine import CommandVerifier, VerifyResult
from registry_manager import RegistryManager
from main import SmartHomeGateway
from dialog_manager import DialogManager
import config


class VoiceSafety(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_timeout_reply_does_not_claim_execution(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.intent = IntentEngine()
        gateway.dialog = DialogManager()
        gateway.registry = SimpleNamespace(
            find_node_by_device=lambda *args: ('AB123', 'ch1'),
            resolve_fullname=lambda *args: 'đèn phòng khách',
            next_seq=lambda *args: 7,
        )
        gateway.verifier = CommandVerifier(None, gateway.registry)
        gateway.verifier.verify_command = AsyncMock(return_value=(VerifyResult.TIMEOUT, 0, 0, 0))
        gateway.tts = SimpleNamespace(synthesize=AsyncMock(return_value=None), synthesize_pcm=AsyncMock(return_value=None))
        result = await gateway.process_voice_command('bật đèn phòng khách', client_node_id='SB1')
        self.assertEqual(result['verify'], 'timeout')
        self.assertNotIn('Đã bật', result['voice_reply'])
        self.assertIn('xác nhận', result['voice_reply'])

    async def test_asr_only_acceptance_and_event_loop(self):
        def recognize(*args):
            time.sleep(0.08)
            return 'bật đèn', 0.99
        gateway = SimpleNamespace(asr=SimpleNamespace(transcribe_with_confidence=recognize),
                                  process_voice_command=AsyncMock())
        server = AudioServer(gateway)
        ws = SimpleNamespace(asr_only=True, send=AsyncMock())
        pending = asyncio.create_task(server._process_audio(ws, [0] * 160, 16000))
        await asyncio.sleep(0.01)
        self.assertFalse(pending.done(), 'ASR blocked the event loop')
        await pending
        self.assertTrue(json.loads(ws.send.call_args.args[0])['accepted'])
        gateway.process_voice_command.assert_not_awaited()
        gateway.asr.transcribe_with_confidence = lambda *args: ('bật đèn', 0.01)
        server._send_voice_reply = AsyncMock()
        await server._process_audio(ws, [0] * 160, 16000)
        self.assertFalse(json.loads(ws.send.call_args.args[0])['accepted'])
        gateway.process_voice_command.assert_not_awaited()

    async def test_context_does_not_cross_clients(self):
        engine = IntentEngine()
        await engine.extract('bật đèn phòng khách', session_key='A')
        other = await engine.extract('tắt nó', session_key='B')
        same = await engine.extract('tắt nó', session_key='A')
        self.assertNotEqual(other.target.device_type, 'light')
        self.assertEqual(same.target.device_type, 'light')

    async def test_forwarded_voice_request_is_executed_once(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway._subbox_voice_requests = {}
        gateway.mqtt = SimpleNamespace(publish=AsyncMock())
        gateway.process_voice_command = AsyncMock(return_value={'voice_reply': 'OK', 'verify': 'success'})
        payload = {'text': 'bật đèn phòng bếp', 'origin_node': 'AB123', 'request_id': 7}
        await gateway._on_subbox_voice('home/subbox/SB1/voice/request', payload)
        await gateway._on_subbox_voice('home/subbox/SB1/voice/request', payload)
        gateway.process_voice_command.assert_awaited_once_with(payload['text'], client_node_id='SB1:AB123')
        self.assertEqual(gateway.mqtt.publish.await_count, 2)


class CommandAcknowledgements(unittest.IsolatedAsyncioTestCase):
    async def test_single_route_and_matching_ack(self):
        mqtt = MQTTHandler()
        await mqtt._on_actionbox('home/subbox/SB1/event/actionbox', {
            'node_id': 'AB123', 'hardware_uid': 'AABBCCDDEEFF', 'protocol_version': 3, 'config_version': 1,
            'channels': [{'channel': 1, 'power_w': 0}],
        })
        async def publish(topic, payload, **kwargs):
            self.assertEqual(topic, 'home/subbox/SB1/command')
            self.assertEqual(payload['cmd'], 'TURN_ON')
            await mqtt._on_actionbox('home/subbox/SB1/event/actionbox', {
                **payload, 'hardware_uid': 'AABBCCDDEEFF', 'protocol_version': 3, 'config_version': 1,
                'status': 'OK', 'state': 'ON',
            })
            return True
        mqtt.publish = AsyncMock(side_effect=publish)
        verifier = CommandVerifier(mqtt, SimpleNamespace(get_rated_watts=lambda *args: 0))
        result, *_ = await verifier.verify_command('AB123', 'ch1', 'turn_on', seq=7)
        self.assertEqual(result, VerifyResult.ACK_ONLY)
        mqtt.publish.assert_awaited_once()

    async def test_no_ack_never_means_success_even_without_power_sensor(self):
        mqtt = MQTTHandler()
        mqtt.send_command = AsyncMock(return_value=True)
        verifier = CommandVerifier(mqtt, SimpleNamespace(get_rated_watts=lambda *args: 0))
        with patch.object(config, 'VERIFY_TIMEOUT_SECONDS', 0):
            result, *_ = await verifier.verify_command('AB123', 'ch1', 'turn_on', seq=7)
        self.assertEqual(result, VerifyResult.TIMEOUT)
        self.assertNotIn('Đã bật', verifier.generate_failure_message('turn_on', 'light', '', result))

    async def test_wrong_boot_session_ack_is_ignored(self):
        mqtt = MQTTHandler()
        await mqtt._on_actionbox('home/subbox/SB1/event/actionbox', {
            'node_id': 'AB123', 'hardware_uid': 'AABBCCDDEEFF', 'protocol_version': 3, 'config_version': 1,
            'request_id': 7, 'status': 'OK', 'state': 'ON',
            'session_id': mqtt.session_id ^ 1,
        })
        self.assertNotIn(('AB123', 7), mqtt.command_acks)


class RegistryPersistence(unittest.TestCase):
    def test_one_changed_node_does_not_sync_fifty_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            db_file = str(Path(directory) / 'test.db')
            registry = RegistryManager(db_path=db_file)
            registry.data = {'nodes': {f'n{i}': {'relay_state': [0, 0]} for i in range(50)}}
            registry._rebuild_rooms = Mock()
            registry._sync_node_to_sqlite = Mock()
            registry.update_relay_state('n1', [1, 0])
            registry.update_relay_state('n1', [1, 0])
            self.assertEqual(registry._sync_node_to_sqlite.call_count, 1)
            self.assertEqual(registry._sync_node_to_sqlite.call_args[0], ('n1', registry.data['nodes']['n1']))
            with registry._get_db() as conn:
                row = conn.execute("SELECT payload FROM registry_entries WHERE entry_id='n1'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(json.loads(row[0])['relay_state'], [1, 0])


class CacheBudget(unittest.TestCase):
    def test_bytes_bounded_and_replacement_accounting(self):
        engine = TTSEngine.__new__(TTSEngine)
        engine._mem_cache = OrderedDict()
        engine._mem_cache_bytes = 0
        chunk = b'x' * (8 * 1024 * 1024)
        engine._cache_put('a', chunk)
        engine._cache_put('b', chunk)
        engine._cache_put('c', chunk)
        self.assertEqual(list(engine._mem_cache), ['b', 'c'])
        engine._cache_put('b', b'y')
        self.assertEqual(engine._mem_cache_bytes, len(chunk) + 1)
        for key in range(300):
            engine._cache_put(str(key), b'x')
        self.assertEqual(len(engine._mem_cache), 256)
        self.assertEqual(engine._mem_cache_bytes, 256)


if __name__ == '__main__':
    unittest.main()
