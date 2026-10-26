from test_maintenance_transport import MaintenanceTransport
from main import SmartHomeGateway
from unittest.mock import Mock

class ChannelMetering(MaintenanceTransport):
    async def test_per_channel_measurements_independent_of_relay_and_invalid_clears(self):
        gateway = SmartHomeGateway.__new__(SmartHomeGateway)
        gateway.registry = self.registry
        gateway.broadcast_event = Mock()
        node = self.registry.data['nodes'][self.uid]
        node['channels'] = {f'ch{i}': {'name': f'Channel {i}'} for i in range(1, 4)}
        def sample(ch, current, **extra):
            return dict(channel=ch, state='OFF', current_ma=current, voltage_v=230,
                        power_w=12, valid=True, sample_uptime_ms=9500, **extra)
        payload = {'node_id': self.uid, 'uptime_s': 10,
                   'channels': [sample(3, 321), sample(1, 0), sample(2, 1234)]}
        await gateway._on_subbox_actionbox('unused', payload)
        self.assertEqual(node['channels']['ch2']['telemetry']['current_ma'], 1234)
        self.assertEqual(node['channels']['ch1']['telemetry']['current_ma'], 0)
        self.assertTrue(node['channels']['ch1']['telemetry']['valid'])
        self.assertEqual(node['relay_state'], [0, 0, 0])
        self.assertEqual(gateway.broadcast_event.call_args.args[0], 'node_telemetry')
        self.assertEqual(gateway.broadcast_event.call_args.args[1]['channels']['ch3']['current_ma'], 321)
        for changes in ({'valid': False}, {'sample_uptime_ms': 0}, {'sample_uptime_ms': 1000},
                        {'current_ma': float('nan')}, {'current_ma': -1}, {'current_ma': True},
                        {'voltage_v': 'bad'}):
            payload['channels'] = [{**sample(2, 1234), **changes}]
            await gateway._on_subbox_actionbox('unused', payload)
            meter = node['channels']['ch2']['telemetry']
            self.assertFalse(meter['valid'], changes)
            self.assertIsNone(meter['current_ma'])
            self.assertIsNone(node['channels']['ch2']['power'])
        self.assertEqual(node['channels']['ch2']['name'], 'Channel 2')
        payload['channels'] = [{**sample(2, 1250), 'voltage_v': None, 'power_w': None}]
        await gateway._on_subbox_actionbox('unused', payload)
        self.assertTrue(node['channels']['ch2']['telemetry']['valid'])
        self.assertEqual(node['channels']['ch2']['telemetry']['current_ma'], 1250)
        self.assertIsNone(node['channels']['ch2']['power'])

        history = self.registry.get_channel_telemetry_history(self.uid, 'ch2', limit=50)
        self.assertEqual(len(history), 9)
        self.assertEqual(history[-1]['current_ma'], 1250)
        self.assertTrue(history[-1]['valid'])
        self.assertEqual(history[-1]['quality'], 'good')
        self.assertIsNone(history[-1]['voltage_v'])
        self.assertIsNone(history[-1]['power_w'])
        self.assertEqual(history[-1]['sample_uptime_ms'], 9500)
        invalid = next(r for r in history if not r['valid'])
        self.assertIsNone(invalid['current_ma'])
        self.assertIsNone(invalid['power_w'])
        self.assertEqual(invalid['quality'], 'invalid')

        ch1 = self.registry.get_channel_telemetry_history(self.uid, 'ch1', limit=5)
        ch3 = self.registry.get_channel_telemetry_history(self.uid, 'ch3', limit=5)
        self.assertEqual([r['channel'] for r in ch1], ['ch1'])
        self.assertEqual([r['channel'] for r in ch3], ['ch3'])
        self.assertEqual(ch1[0]['current_ma'], 0)
        self.assertEqual(ch3[0]['current_ma'], 321)
        self.assertEqual(self.registry.get_channel_telemetry_history(self.uid, 'ch9'), [])

        payload['channels'] = [{**sample(2, 1250), 'sample_uptime_ms': 1000}]
        await gateway._on_subbox_actionbox('unused', payload)
        stale = self.registry.get_channel_telemetry_history(self.uid, 'ch2', limit=1)[0]
        self.assertFalse(stale['valid'])
        self.assertEqual(stale['quality'], 'stale')
        self.assertIsNone(stale['current_ma'])
