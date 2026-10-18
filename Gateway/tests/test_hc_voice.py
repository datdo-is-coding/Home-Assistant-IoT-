import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from test_hc_registry import RegistryTest
from gateway.core_v1.registry import CoreError
from gateway.core_v1.voice import CoreVoice


class VoiceTests(IsolatedAsyncioTestCase):
    _RegistryTest = RegistryTest

    def setUp(self):
        self.fixture = self._RegistryTest()
        self.fixture.setUp()
        f = self.fixture
        self.r = f.r
        self.member, self.token = self.r.create_user('Voice SubBox')
        self.r.db.execute('INSERT INTO home_members VALUES(?,?,?)', (f.home, self.member, 'Member'))
        self.device = f.bind()
        f.online(f.sub, 200)
        f.online(f.action)
        f.report()
        self.voice = CoreVoice(self.r, {f.sub: self.member}, None)

    def tearDown(self):
        self.fixture.tearDown()

    def test_unique_room_device_and_explicit_set_only(self):
        for text, state in [('bật đèn', True), ('tắt đèn', False), ('turn on light', True)]:
            self.assertEqual(self.voice.resolve(self.member, self.fixture.sub, self.fixture.action, text),
                             (self.device['device_id'], state))
        for text in ['đảo đèn', 'bật đèn và tắt quạt', 'đừng bật đèn', 'bật tất cả', 'bật']:
            with self.assertRaises(CoreError):
                self.voice.resolve(self.member, self.fixture.sub, self.fixture.action, text)

    def test_ambiguous_device_and_wrong_source_fail_closed(self):
        self.r.create_device(self.fixture.owner, self.fixture.home, 'Second light', 'light', 'HC-001122334402:CH2')
        with self.assertRaises(CoreError):
            self.voice.resolve(self.member, self.fixture.sub, self.fixture.action, 'bật đèn')
        with self.assertRaises(CoreError):
            self.voice.resolve(self.member, self.fixture.sub, self.fixture.sub, 'bật light')
        with self.assertRaises(CoreError):
            self.voice.authorize(self.fixture.owner, self.fixture.sub)

    def test_member_revocation_rechecked(self):
        self.r.db.execute('DELETE FROM home_members WHERE user_id=?', (self.member,))
        with self.assertRaises(CoreError):
            self.voice.resolve(self.member, self.fixture.sub, self.fixture.action, 'bật đèn')

    async def test_repeated_request_reuses_command_and_never_claims_accepted_success(self):
        command = self.voice.submit(self.member, self.fixture.sub, self.fixture.action, 'bật đèn', 'a'*32)
        again = self.voice.submit(self.member, self.fixture.sub, self.fixture.action, 'bật đèn', 'a'*32)
        self.assertEqual(command['command_id'], again['command_id'])
        self.assertEqual(len(self.r.rows('SELECT * FROM commands')), 1)
        self.assertEqual(self.voice.result(command)['verify'], 'pending')
        self.r.ack(self.fixture.action, command['command_id'], 'APPLIED', command['config_rev'], True)
        self.assertEqual(self.voice.result(self.r.get_command(self.member, command['command_id']))['verify'], 'success')

    async def test_fault_and_expiry_never_report_success(self):
        cmd = self.voice.submit(self.member, self.fixture.sub, self.fixture.action, 'bật đèn', 'b'*32)
        self.r.ack(self.fixture.action, cmd['command_id'], 'FAILED', cmd['config_rev'], False)
        self.assertEqual(self.voice.result(self.r.get_command(self.member, cmd['command_id']))['verify'], 'failed')
        cmd = self.voice.submit(self.member, self.fixture.sub, self.fixture.action, 'tắt đèn', 'c'*32)
        self.r.clock = lambda: cmd['expires'] + 1
        self.assertEqual(self.voice.result(cmd)['verify'], 'timeout')
        with self.assertRaises(CoreError):
            self.r.ack(self.fixture.action, cmd['command_id'], 'APPLIED', cmd['config_rev'], False)

    async def test_old_recording_is_not_dispatched_after_slow_asr(self):
        import time
        self.voice.asr = type('ASR', (), {'transcribe_with_confidence': lambda *args: ('bật đèn', .99)})()
        ws = type('Socket', (), {'closed': False, 'send_json': AsyncMock()})()
        await self.voice.process(ws, self.member, self.fixture.sub, self.fixture.action,
                                 'd'*32, b'\x00\x00'*160, time.monotonic()-20)
        self.assertEqual(self.r.rows('SELECT * FROM commands'), [])
        self.assertEqual(ws.send_json.call_args.args[0]['verify'], 'expired')


del RegistryTest
