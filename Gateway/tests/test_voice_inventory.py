"""Read-only spoken inventory uses registered devices, never command dispatch."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from main import SmartHomeGateway
from dialog_manager import DialogManager, DialogSession


class VoiceInventoryTests(unittest.IsolatedAsyncioTestCase):
    def make_gateway(self, nodes=None, pending=None):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry = SimpleNamespace(get_all_nodes=lambda: nodes or {},
                                           get_pending=lambda: pending or {})
        gateway.dialog = DialogManager()
        gateway.intent = SimpleNamespace(extract=AsyncMock(return_value=None))
        gateway.verifier = SimpleNamespace(verify_command=AsyncMock())
        gateway.tts = SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'pcm'))
        gateway.broadcast_event = Mock()
        return gateway

    async def test_phrases_return_inventory_without_parsing_or_dispatch(self):
        for phrase in ('Trong nhà có những thiết bị nào?', 'nhà mình có thiết bị gì',
                       'liệt kê các thiết bị trong nhà', 'co nhung thiet bi nao'):
            with self.subTest(phrase=phrase):
                gateway = self.make_gateway({'AB1': {'room': 'livingroom', 'status': 'online',
                    'channels': {'ch1': {'name': 'Đèn chính', 'device_type': 'light'}}}})
                gateway.dialog._sessions['AB1'] = DialogSession(
                    'AB1', 'AB1', {'command': {'action': 'turn_on'}}, 'channel')
                result = await gateway.process_voice_command(phrase, client_node_id='AB1')
                self.assertEqual(result['verify'], 'inventory')
                self.assertIn('1 thiết bị', result['voice_reply'])
                self.assertIn('Đèn chính ở phòng khách', result['voice_reply'])
                self.assertEqual(result['tts_format'], 'pcm')
                self.assertFalse(result['follow_up'])
                self.assertIsNone(gateway.dialog.get_active_session('AB1'))
                gateway.intent.extract.assert_not_awaited()
                gateway.verifier.verify_command.assert_not_awaited()

    async def test_empty_pending_revoked_and_subbox_are_not_appliances(self):
        nodes = {nid: {'status': status, 'channels': {'ch1': {'name': 'Ẩn'}}}
                 for nid, status in [('SB123', 'online'), ('ABpending', 'online'),
                                     ('ABrevoked', 'NEEDS_REPROVISION')]}
        gateway = self.make_gateway(nodes, {'ABpending': {}})
        result = await gateway.process_voice_command('trong nhà có những thiết bị nào')
        self.assertEqual(result['voice_reply'], 'Nhà bạn chưa có thiết bị nào được đăng ký.')

    async def test_duplicates_are_counted_and_offline_is_explicit(self):
        nodes = {f'AB{i}': {'status': status, 'room': 'bedroom',
                           'channels': {'ch1': {'name': 'Quạt trần'}}}
                 for i, status in enumerate(('online', 'online', 'offline'))}
        result = await self.make_gateway(nodes).process_voice_command('nhà mình có thiết bị gì')
        self.assertIn('3 thiết bị', result['voice_reply'])
        self.assertIn('2 Quạt trần ở phòng ngủ', result['voice_reply'])
        self.assertIn('Quạt trần ở phòng ngủ, đang ngoại tuyến', result['voice_reply'])

    async def test_long_list_is_bounded_and_online_devices_come_first(self):
        nodes = {f'AB{i}': {'status': 'offline' if i == 0 else 'online', 'room': 'unknown',
                           'channels': {'ch1': {'name': f'Đèn số {i}'}}}
                 for i in range(8)}
        result = await self.make_gateway(nodes).process_voice_command('liệt kê thiết bị')
        reply = result['voice_reply']
        self.assertIn('8 thiết bị', reply)
        self.assertEqual(reply.count('Đèn số'), 5)
        self.assertNotIn('Đèn số 0', reply)
        self.assertIn('Còn 3 thiết bị khác', reply)

    async def test_control_and_room_questions_are_not_mistaken_for_house_inventory(self):
        for phrase in ('bật tất cả thiết bị trong nhà', 'phòng ngủ có thiết bị nào',
                       'trong nhà có những thiết bị nào rồi bật tất cả lên'):
            gateway = self.make_gateway()
            result = await gateway.process_voice_command(phrase)
            self.assertNotEqual(result['verify'], 'inventory')
            gateway.intent.extract.assert_awaited_once()
