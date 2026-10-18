import json
import unittest
import test_hc_registry as fixture
from gateway.core_v1.ha import HomeAssistantAdapter
from gateway.core_v1.registry import CoreError

class HATest(unittest.TestCase):
    setUp = fixture.RegistryTest.setUp
    tearDown = fixture.RegistryTest.tearDown
    enroll = fixture.RegistryTest.enroll
    online = fixture.RegistryTest.online
    report = fixture.RegistryTest.report
    bind = fixture.RegistryTest.bind

    def adapter(self):
        user, _ = self.r.create_user('HA integration')
        self.r.add_member(self.owner, self.home, user, 'Member')
        return HomeAssistantAdapter(self.r, user, self.home)

    def test_rename_rebind_and_removal_keep_identity(self):
        d = self.bind()['device_id']
        ha = self.adapter()
        first = {p.topic: p.payload for p in ha.outgoing()}
        topic = f'homeassistant/light/hc_{d}/relay/config'
        uid = json.loads(first[topic])['unique_id']
        self.r.rename_device(self.owner, d, 'Renamed', 'light')
        self.r.bind(self.owner, d, 'HC-001122334402:CH2')
        update = {p.topic: p.payload for p in ha.outgoing()}
        self.assertEqual(json.loads(update[topic])['unique_id'], uid)
        self.assertEqual(json.loads(update[topic])['device']['name'], 'Renamed')
        self.r.unbind(self.owner, 'HC-001122334402:CH2')
        deleted = {p.topic: p.payload for p in ha.outgoing()}
        self.assertEqual(deleted[topic], b'')

        self.assertEqual({p.topic: p.payload for p in self.adapter().outgoing()}[topic], b'')

    def test_reported_state_current_invalid_and_stale(self):
        d = self.bind()['device_id']
        ha = self.adapter()
        self.online(self.sub); self.online(self.action); self.report(state=False, current=.4)
        messages = {p.topic: p.payload for p in ha.outgoing()}
        root = f'{ha.root}/{d}'
        self.assertEqual(messages[root + '/relay'], b'OFF')
        self.assertEqual(messages[root + '/current'], b'0.4')
        sensor = json.loads(messages[f'homeassistant/sensor/hc_{d}/current/config'])
        self.assertEqual(sensor['unit_of_measurement'], 'A')
        self.assertNotIn('power', json.dumps(sensor))
        command = ha.receive(root + '/set', b'ON')
        self.assertEqual(command['status'], 'ACCEPTED')
        self.assertEqual(self.r.snapshot(self.owner, self.home)['channels'][0]['relay_state'], 0)
        self.report(seq=2, valid=False)
        messages = {p.topic: p.payload for p in ha.outgoing()}
        self.assertEqual(messages[root + '/current_available'], b'offline')
        self.assertEqual(messages[root + '/current'], b'')
        self.r.db.execute('UPDATE registered_nodes SET last_seen=NULL')
        messages = {p.topic: p.payload for p in ha.outgoing()}
        self.assertEqual(messages[root + '/availability'], b'offline')
        self.assertEqual(messages[root + '/relay'], b'')

    def test_commands_require_live_membership_and_no_retained_replay(self):
        d = self.bind()['device_id']
        ha = self.adapter()
        with self.assertRaises(CoreError):
            ha.receive(f'{ha.root}/{d}/set', b'ON', retained=True)
        with self.assertRaises(CoreError):
            ha.receive(f'{ha.root}/{d}/set', b'TOGGLE')
        self.r.db.execute('DELETE FROM home_members WHERE user_id=?', (ha.user,))
        with self.assertRaises(CoreError):
            ha.receive(f'{ha.root}/{d}/set', b'ON')
        with self.assertRaises(CoreError):
            HomeAssistantAdapter(self.r, self.owner, self.home)

    def test_birth_republishes_discovery_and_type_change_cleans_old_entity(self):
        d = self.bind()['device_id']
        ha = self.adapter()
        ha.outgoing()
        self.assertEqual(ha.outgoing(), [])
        ha.receive('homeassistant/status', b'online')
        self.assertTrue(ha.outgoing())
        self.r.rename_device(self.owner, d, 'Fan', 'fan')
        messages = {p.topic: p.payload for p in ha.outgoing()}
        self.assertEqual(messages[f'homeassistant/light/hc_{d}/relay/config'], b'')
        self.assertTrue(messages[f'homeassistant/fan/hc_{d}/relay/config'])
