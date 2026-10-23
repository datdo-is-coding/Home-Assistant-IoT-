from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from registry_manager import RegistryManager
from dialog_manager import DialogManager
from intent_engine import IntentEngine


class VoiceTargets(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = RegistryManager.__new__(RegistryManager)
        self.registry.data = {'pending': {}, 'nodes': {
            'SB1': {'status': 'online', 'room': 'livingroom', 'channels': {
                'ch1': {'device_type': 'light', 'name': 'Điều hòa'}}},
            'AB1': {'status': 'online', 'room': 'livingroom', 'channels': {
                'ch1': {'device_type': 'light', 'name': 'Đèn trần', 'aliases': ['đèn chính']},
                'ch2': {'device_type': 'light', 'name': 'Đèn ngủ'}}},
            'AB2': {'status': 'online', 'room': 'livingroom', 'channels': {
                'ch1': {'device_type': 'air_conditioner', 'name': 'Điều hòa'}}},
        }}

    async def test_specific_device_name_survives_parse_and_resolves_exactly(self):
        for text, target, channel in [('bật đèn trần', 'den_tran', 'ch1'),
                                      ('tắt đèn ngủ', 'den_ngu', 'ch2')]:
            intent = await IntentEngine(registry=self.registry).extract(text)
            self.assertEqual(intent['command']['device'], target)
            dm = DialogManager(self.registry)
            needs, _, _, result = dm.inspect_intent(intent, detected_room='livingroom')
            self.assertFalse(needs)
            self.assertEqual(self.registry.find_node_by_device(result['command']['device'],
                             result['command']['location']), ('AB1', channel))

    async def test_registered_custom_name_and_rename_are_live(self):
        channel = self.registry.data['nodes']['AB1']['channels']['ch1']
        channel['name'] = 'Góc của bé'
        channel['aliases'] = ['đèn bé Na']
        engine = IntentEngine(registry=self.registry)
        for name in ('Góc của bé', 'đèn bé Na'):
            intent = await engine.extract('bật ' + name)
            self.assertEqual(self.registry.find_node_by_device(intent['command']['device'], 'livingroom'),
                             ('AB1', 'ch1'))
        channel['name'] = 'Đèn đọc sách'
        intent = await engine.extract('tắt đèn đọc sách')
        self.assertEqual(intent['command']['device'], 'den_doc_sach')
        self.assertEqual(self.registry.find_node_by_device('den_doc_sach', 'livingroom'), ('AB1', 'ch1'))
        self.assertIsNone(self.registry.find_node_by_device('goc_cua_be', 'livingroom'))

    async def test_asr_reads_new_names_for_each_utterance(self):
        from asr_engine import ASREngine
        engine = ASREngine()
        engine._registry = self.registry
        engine._initialized = engine._using_beam_search = True
        stream = SimpleNamespace(accept_waveform=Mock(), result=SimpleNamespace(text='BẬT ĐÈN'))
        engine.recognizer = SimpleNamespace(create_stream=Mock(return_value=stream), decode_stream=Mock())
        channel = self.registry.data['nodes']['AB1']['channels']['ch1']
        for name in ('Góc của bé', 'Đèn đọc sách'):
            channel['name'] = name
            engine.transcribe_with_confidence([0.1]*16000, 16000)
            self.assertIn(name.upper(), engine.recognizer.create_stream.call_args.kwargs['hotwords'])

    async def test_ambiguity_uses_real_candidates_and_followup_matches_shown_name(self):
        dm = DialogManager(self.registry)
        intent = {'command': {'action': 'turn_on', 'device': 'light', 'location': 'phong_khach'}}
        needs, question, _, _ = dm.inspect_intent(intent, client_key='AB1')
        self.assertTrue(needs)
        self.assertNotIn('Điều hòa', question)
        self.assertIn('Đèn trần', question)
        self.assertIn('Đèn ngủ', question)
        answer = dm.fill_slot(dm.get_active_session('AB1'), 'đèn trần')
        self.assertEqual(answer['command']['node_id'], 'AB1')
        self.assertEqual(answer['command']['channel'], 'ch1')

    async def test_duplicate_names_require_explicit_selection(self):
        self.registry.data['nodes']['AB1']['channels']['ch2']['name'] = 'Đèn trần'
        dm = DialogManager(self.registry)
        dm.inspect_intent({'command': {'action': 'turn_on', 'device': 'den_tran', 'location': 'livingroom'}}, client_key='AB1')
        session = dm.get_active_session('AB1')
        unclear = dm.fill_slot(session, 'đèn trần')
        self.assertNotIn('node_id', unclear['command'])
        selected = dm.fill_slot(session, 'cái thứ hai')
        self.assertEqual(selected['command']['channel'], 'ch2')

    async def test_pending_and_offline_never_enter_choices(self):
        self.registry.data['pending']['AB1'] = {}
        self.registry.data['nodes']['AB2']['status'] = 'offline'
        self.assertEqual(self.registry.find_device_candidates(None, 'phong_khach'), [])

    async def test_gateway_followup_executes_only_selected_channel(self):
        from main import SmartHomeGateway
        from verify_engine import VerifyResult
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry = self.registry
        self.registry._seq = {'AB1': 0}
        gateway.dialog = DialogManager(self.registry)
        gateway.intent = IntentEngine(registry=self.registry)
        gateway.tts = SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'pcm'))
        gateway.broadcast_event = Mock()
        gateway.verifier = SimpleNamespace(verify_command=AsyncMock(return_value=(VerifyResult.ACK_ONLY,0,0,0)))
        first = await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        self.assertTrue(first['follow_up'])
        gateway.verifier.verify_command.assert_not_awaited()
        second = await gateway.process_voice_command('đèn trần', client_node_id='AB1', detected_room='livingroom')
        self.assertFalse(second['follow_up'])
        self.assertEqual(gateway.verifier.verify_command.call_args.args[:3], ('AB1', 'ch1', 'turn_on'))

    def make_gateway(self):
        from main import SmartHomeGateway
        from verify_engine import VerifyResult
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry = self.registry
        self.registry._seq = {'AB1': 0, 'AB2': 0}
        gateway.dialog = DialogManager(self.registry)
        gateway.intent = IntentEngine(registry=self.registry)
        gateway.tts = SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'pcm'))
        gateway.broadcast_event = Mock()
        gateway.verifier = SimpleNamespace(verify_command=AsyncMock(return_value=(VerifyResult.ACK_ONLY,0,0,0)))
        return gateway

    async def test_both_followup_controls_only_the_offered_lights(self):
        for answer in ('bật cả hai', 'cả hai', 'tắt cả hai'):
            with self.subTest(answer=answer):
                gateway = self.make_gateway()
                await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
                result = await gateway.process_voice_command(answer, client_node_id='AB1')
                self.assertFalse(result['follow_up'])
                action = 'turn_off' if answer.startswith('tắt') else 'turn_on'
                self.assertEqual([call.args[:3] for call in gateway.verifier.verify_command.await_args_list],
                                 [('AB1', 'ch1', action), ('AB1', 'ch2', action)])
                self.assertIsNone(gateway.dialog.get_active_session('AB1'))

    async def test_action_prefixed_ordinal_keeps_pending_choices(self):
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        result = await gateway.process_voice_command('bật cái thứ hai', client_node_id='AB1')
        self.assertFalse(result['follow_up'])
        self.assertEqual(gateway.verifier.verify_command.call_args.args[:3], ('AB1', 'ch2', 'turn_on'))

    async def test_ambiguous_followup_stops_after_one_reprompt(self):
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        first = await gateway.process_voice_command('cái đó', client_node_id='AB1')
        second = await gateway.process_voice_command('cái đó', client_node_id='AB1')
        self.assertTrue(first['follow_up'])
        self.assertFalse(second['follow_up'])
        self.assertIsNone(gateway.dialog.get_active_session('AB1'))
        gateway.verifier.verify_command.assert_not_awaited()

    async def test_group_with_a_stale_candidate_does_not_dispatch(self):
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        del self.registry.data['nodes']['AB1']['channels']['ch2']
        result = await gateway.process_voice_command('bật cả hai', client_node_id='AB1')
        self.assertFalse(result['follow_up'])
        gateway.verifier.verify_command.assert_not_awaited()

    async def test_cancel_followup_never_dispatches(self):
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        result = await gateway.process_voice_command('hủy', client_node_id='AB1')
        self.assertEqual(result['verify'], 'cancelled')
        self.assertFalse(result['follow_up'])
        gateway.verifier.verify_command.assert_not_awaited()

    async def test_explicit_new_device_can_replace_pending_question(self):
        self.registry.data['nodes']['AB2']['channels']['ch1'] = {'name': 'Quạt trần', 'device_type': 'fan'}
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        result = await gateway.process_voice_command('bật quạt trần', client_node_id='AB1', detected_room='livingroom')
        self.assertFalse(result['follow_up'])
        self.assertEqual(gateway.verifier.verify_command.call_args.args[:3], ('AB2', 'ch1', 'turn_on'))

    async def test_untrusted_group_targets_cannot_dispatch(self):
        gateway = self.make_gateway()
        gateway.intent.extract = AsyncMock(return_value={'command': {
            'action': 'turn_on', 'device': 'den_tran', 'location': 'livingroom',
            'targets': [('AB2', 'ch1')]}})
        result = await gateway.process_voice_command('bật đèn trần', client_node_id='AB1')
        self.assertFalse(result['success'])
        gateway.verifier.verify_command.assert_not_awaited()

    async def test_group_failure_reports_partial_result(self):
        from verify_engine import VerifyResult
        gateway = self.make_gateway()
        await gateway.process_voice_command('bật đèn', client_node_id='AB1', detected_room='livingroom')
        gateway.verifier.verify_command.side_effect = [(VerifyResult.ACK_ONLY,0,0,0), RuntimeError('offline')]
        result = await gateway.process_voice_command('bật cả hai', client_node_id='AB1')
        self.assertFalse(result['success'])
        self.assertEqual(result['verify'], 'partial')
        self.assertIn('1 thiết bị chưa xác nhận', result['voice_reply'])
        self.assertFalse(result['follow_up'])
