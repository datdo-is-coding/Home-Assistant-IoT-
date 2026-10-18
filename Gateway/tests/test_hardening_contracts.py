"""Offline persistence, target resolution and load-verification contracts."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from registry_manager import RegistryManager
from mqtt_handler import MQTTHandler
from verify_engine import CommandVerifier, VerifyResult


class Persistence(unittest.TestCase):
    def test_sqlite_survives_json_removal_and_retains_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / 'registry.json'
            legacy.write_text(json.dumps({'nodes': {'AB1': {'channels': {'ch1': {'device_type': 'light'}}, 'relay_state': [0, 0]}}, 'pending': {'AB2': {'mac': 'AA'}}, 'rooms': {}}))
            db = str(Path(tmp) / 'registry.db')
            registry = RegistryManager(str(legacy), db_path=db)
            registry.update_relay_state('AB1', [1, 0])
            self.assertEqual(json.loads(legacy.read_text())['nodes']['AB1']['relay_state'], [0, 0])
            legacy.unlink()
            loaded = RegistryManager(str(legacy), db_path=db)
            self.assertEqual(loaded.data['nodes']['AB1']['relay_state'], [1, 0])
            self.assertIn('AB2', loaded.get_pending())
            loaded.delete_node('AB1')
            self.assertNotIn('AB1', RegistryManager(str(legacy), db_path=db).get_all_nodes())

    def test_ambiguous_targets_never_choose_first(self):
        registry = RegistryManager.__new__(RegistryManager)
        registry.data = {'nodes': {node: {'room': 'phong_ngu', 'status': 'online', 'channels': {'ch1': {'device_type': 'light', 'name': node}}} for node in ('AB1', 'AB2')}}
        self.assertIsNone(registry.find_node_by_device('light', 'phong_ngu'))
        self.assertEqual(len(registry.find_device_candidates('light', 'phong_ngu')), 2)


class LoadVerification(unittest.IsolatedAsyncioTestCase):
    async def test_channel_three_ack_updates_only_third_relay(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryManager(str(Path(tmp) / 'registry.json'), str(Path(tmp) / 'registry.db'))
            registry.data['nodes']['ABV2'] = {'relay_state': [1, 0], 'channels': {'ch3': {}}}
            mqtt = MQTTHandler()
            async def send(node, channel, action, seq=None, **kwargs):
                mqtt.command_acks[(node, seq)] = {'channel': 3, 'status': 'OK', 'state': 'ON'}
                return True
            mqtt.send_command = AsyncMock(side_effect=send)
            verifier = CommandVerifier(mqtt, registry)
            result, *_ = await verifier.verify_command('ABV2', 'ch3', 'turn_on', seq=7)
            self.assertEqual(result, VerifyResult.ACK_ONLY)
            self.assertEqual(registry.get_all_nodes()['ABV2']['relay_state'], [1, 0, 1])

    async def test_actionbox_v2_channel_three_uses_selected_subbox_route(self):
        mqtt = MQTTHandler()
        mqtt.node_identities['ABV2'] = {'hardware_uid': '112233445566', 'config_version': 1}
        mqtt.subbox_route = lambda node: 'SB1'
        mqtt.publish = AsyncMock(return_value=True)
        for channel in ('ch3', '3', 3):
            mqtt.publish.reset_mock()
            self.assertTrue(await mqtt.send_command('ABV2', channel, 'turn_on', seq=17))
            mqtt.publish.assert_awaited_once()
            args = mqtt.publish.call_args
            self.assertEqual(args.args[0], 'home/subbox/SB1/command')
            self.assertEqual(args.args[1]['channel'], 3)
            self.assertEqual(args.args[1]['cmd'], 'TURN_ON')
            self.assertEqual(args.args[1]['node_id'], 'ABV2')
        self.assertTrue(await mqtt.send_relay_set('ABV2', 3, 0))
        self.assertFalse(await mqtt.send_relay_set('ABV2', 4, 1))

    async def test_confirmed_ack_updates_registry_before_next_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryManager(str(Path(tmp) / 'registry.json'), str(Path(tmp) / 'registry.db'))
            registry.data['nodes']['AB1'] = {'relay_state': [0, 1], 'channels': {}}
            mqtt = MQTTHandler()
            async def send(node, channel, action, seq=None, **kwargs):
                mqtt.command_acks[(node, seq)] = {'channel': 1, 'status': 'OK', 'state': 'ON'}
                return True
            mqtt.send_command = AsyncMock(side_effect=send)
            verifier = CommandVerifier(mqtt, registry)
            result, *_ = await verifier.verify_command('AB1', 'ch1', 'turn_on', seq=7)
            self.assertEqual(result, VerifyResult.ACK_ONLY)
            self.assertEqual(registry.get_all_nodes()['AB1']['relay_state'], [1, 1])
            loaded = RegistryManager(str(Path(tmp) / 'registry.json'), str(Path(tmp) / 'registry.db'))
            self.assertEqual(loaded.get_all_nodes()['AB1']['relay_state'], [1, 1])
            result, *_ = await verifier.verify_command('AB1', 'ch1', 'turn_off', seq=8)
            self.assertEqual(result, VerifyResult.FAILED)
            self.assertEqual(registry.get_all_nodes()['AB1']['relay_state'], [1, 1])

    async def check_command(self, sample=None, thresholds=None, report_channel=1, action="turn_on", command_channel="ch1"):
        mqtt = MQTTHandler()
        async def send(node, channel, action, seq=None, **kwargs):
            ch_num = {"ch1": 1, "ch2": 2, "ch3": 3}.get(channel, 1)
            mqtt.command_acks[(node, seq)] = {'channel': ch_num, 'status': 'OK', 'state': 'ON' if action == "turn_on" else 'OFF', 'hardware_uid': 'AABBCCDDEEFF'}
            if sample is not None:
                mqtt.load_reports[(node, seq)] = {'channel': report_channel, 'hardware_uid': 'AABBCCDDEEFF', 'sample': sample}
            return True
        mqtt.send_command = AsyncMock(side_effect=send)
        registry = SimpleNamespace(get_all_nodes=lambda: {'AB1': {'channels': {command_channel: {'load_verification': thresholds or {}}}}}, get_rated_watts=lambda *args: 0)
        verifier = CommandVerifier(mqtt, registry)
        return (await verifier.verify_command('AB1', command_channel, action, seq=7))[0]

    async def test_ack_without_calibration_is_not_load_confirmation(self):
        self.assertEqual(await self.check_command(), VerifyResult.ACK_ONLY)

    async def test_calibrated_fresh_sample_confirms_load(self):
        sample = {'valid': True, 'current_ma': 150, 'power_w': 30, 'sample_uptime_ms': 1700, 'command_uptime_ms': 1000, 'boot_id': 1}
        self.assertEqual(await self.check_command(sample, {'on_min_ma': 100, 'off_max_ma': 10, 'settle_ms': 500}), VerifyResult.CONFIRMED_LOAD)

    async def test_invalid_sample_does_not_claim_success(self):
        sample = {'valid': False, 'current_ma': 150, 'power_w': 30, 'sample_uptime_ms': 1700, 'command_uptime_ms': 1000, 'boot_id': 1}
        self.assertEqual(await self.check_command(sample, {'on_min_ma': 100, 'off_max_ma': 10}), VerifyResult.ACK_ONLY)

    async def test_load_report_wrong_channel_does_not_confirm(self):
        sample = {'valid': True, 'current_ma': 150, 'power_w': 30}
        self.assertEqual(
            await self.check_command(sample, {'on_min_ma': 100}, report_channel=2, command_channel='ch1'),
            VerifyResult.ACK_ONLY
        )

    async def test_load_report_zero_power_does_not_confirm_load(self):
        sample = {'valid': True, 'current_ma': 0, 'power_w': 0}
        self.assertEqual(
            await self.check_command(sample, {'min_on_power_w': 5.0}),
            VerifyResult.ACK_ONLY
        )

    async def test_load_report_power_threshold_confirms_load(self):
        sample = {'valid': True, 'current_ma': 120, 'power_w': 25.0}
        self.assertEqual(
            await self.check_command(sample, {'min_on_power_w': 10.0}),
            VerifyResult.CONFIRMED_LOAD
        )

    async def test_load_report_off_exceeds_max_off_power_fails_confirmation(self):
        sample = {'valid': True, 'current_ma': 80, 'power_w': 15.0}
        self.assertEqual(
            await self.check_command(sample, {'max_off_power_w': 5.0}, action='turn_off'),
            VerifyResult.ACK_ONLY
        )

    async def test_toggle_is_rejected_before_publish(self):
        mqtt = MQTTHandler()
        mqtt.publish = AsyncMock()
        self.assertFalse(await mqtt.send_command('AB1', 'ch1', 'toggle'))
        mqtt.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
