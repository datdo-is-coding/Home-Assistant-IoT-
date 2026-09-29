import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from main import SmartHomeGateway
import config
config.BOOTSTRAP_PASSWORD = "test_bootstrap_pw_1234"


class CleanGatewayVoiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_fast_path_voice_commands(self):
        gw = SmartHomeGateway()
        gw.registry.data["nodes"].clear()
        gw.registry.register_node(
            node_id='livingroom-node01',
            mac='AA:BB:CC:DD:EE:01',
            channels={
                'ch1': {'name': 'Đèn phòng khách', 'device_type': 'light'},
                'ch2': {'name': 'Quạt phòng khách', 'device_type': 'fan'}
            },
            area='phong_khach',
            description='Node phòng khách T1'
        )

        test_commands = [
            ("bật đèn phòng khách", "turn_on"),
            ("tắt quạt phòng khách", "turn_off"),
            ("bật tất cả thiết bị", "turn_on"),
            ("tắt hết", "turn_off"),
            ("mở quạt", "turn_on")
        ]

        for cmd, expected_action in test_commands:
            res = await gw.process_voice_command(cmd)
            self.assertIsNotNone(res)
            self.assertIn('voice_reply', res)


if __name__ == '__main__':
    unittest.main()
