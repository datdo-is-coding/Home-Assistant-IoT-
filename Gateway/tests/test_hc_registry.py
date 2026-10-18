import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from gateway.core_v1.registry import Registry, CoreError, canonical


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Registry(Path(self.tmp.name) / 'core.db', b'k' * 32)
        self.owner, self.token = self.r.create_user('owner')
        self.home = self.r.create_home(self.owner, 'Home')
        self.room = self.r.create_room(self.owner, self.home, 'Living')
        self.keys = {}
        self.sub = self.enroll('HC-001122334401', 'SUB_BOX')
        self.action = self.enroll('HC-001122334402', 'ACTION_BOX', self.sub)

    def tearDown(self):
        self.r.close()
        self.tmp.cleanup()

    def enroll(self, factory, kind, parent=None):
        secret = hashlib.sha256(factory.encode()).digest()
        self.r.add_factory_device(factory, kind, 'HC-S1' if kind == 'SUB_BOX' else 'HC-A1', secret, 'setup-' + factory)
        claim = self.r.claim(self.owner, factory, 'setup-' + factory, self.room, parent)
        self.assertIsInstance(claim['node_id'],int)
        proof = hmac.digest(secret, canonical(dict(claim=claim, stored=True, peer_confirmed=True, channels=3 if parent else 0)), 'sha256').hex()
        node = self.r.confirm_claim(claim['claim_id'], proof, stored=True, peer_confirmed=True, channels=3 if parent else 0)
        self.keys[node['node_id']] = self.r.node_key(node['node_id'])
        return node['node_id']

    def online(self, node, boot=100):
        challenge = self.r.session_challenge(node, boot)
        proof = hmac.digest(self.keys[node], canonical(challenge), 'sha256').hex()
        self.r.admit_session(node, challenge['nonce'], proof)

    def report(self, node=None, seq=1, boot=100, state=False, valid=True, current=.3):
        node = node or self.action
        rev = self.r.get_node(self.owner, node)['config_rev']
        payload = dict(node_id=node, boot_id=boot, state_seq=seq, config_rev=rev,
                       channels=[dict(number=i, relay_state=state, ct_valid=valid,
                                      current_rms_a=current if valid else None, fault_flags=0) for i in (1, 2, 3)])
        return self.r.report_state(node, payload)

    def bind(self):
        return self.r.create_device(self.owner, self.home, 'Light', 'light', 'HC-001122334402:CH1')

    def test_identity_three_channels_and_transactional_binding(self):
        self.assertEqual(len(self.r.channels(self.owner, self.action)), 3)
        device = self.bind()
        with self.assertRaises(CoreError):
            self.bind()
        self.r.rename_device(self.owner, device['device_id'], 'Ceiling', 'light')
        self.assertEqual(self.r.devices(self.owner, self.home)[0]['device_id'], device['device_id'])
        self.r.bind(self.owner, device['device_id'], 'HC-001122334402:CH2')
        self.assertEqual(self.r.devices(self.owner, self.home)[0]['channel_id'], 'HC-001122334402:CH2')

    def test_claim_not_complete_before_all_acknowledgements(self):
        fid = 'HC-001122334403'
        self.r.add_factory_device(fid, 'ACTION_BOX', 'HC-A1', b'a' * 32, 'unique-setup')
        claim = self.r.claim(self.owner, fid, 'unique-setup', self.room, self.sub)
        proof = hmac.digest(b'a' * 32, canonical(dict(claim=claim,stored=True,peer_confirmed=True,channels=3)), 'sha256').hex()
        with self.assertRaises(CoreError):
            self.r.confirm_claim(claim['claim_id'], proof, stored=False, peer_confirmed=True, channels=3)
        with self.assertRaises(CoreError):
            self.r.confirm_claim(claim['claim_id'], '00'*32, stored=True, peer_confirmed=True, channels=3)
        self.assertEqual(len(self.r.nodes(self.owner, self.home)), 2)

    def test_cross_home_and_roles(self):
        user, token = self.r.create_user('other')
        other_home = self.r.create_home(user, 'Other')
        with self.assertRaises(CoreError):
            self.r.create_device(user, self.home, 'x', 'light', 'HC-001122334402:CH1')
        with self.assertRaises(CoreError):
            self.r.create_device(self.owner, other_home, 'x', 'light', 'HC-001122334402:CH1')
        self.r.add_member(self.owner, self.home, user, 'Member')
        with self.assertRaises(CoreError):
            self.r.create_room(user, self.home, 'denied')
        self.assertEqual(self.r.authenticate(token), user)
        with self.assertRaises(CoreError):
            self.r.authenticate('wrong')

    def test_primary_subbox_and_factory_uniqueness(self):
        with self.assertRaises(CoreError):
            self.enroll('HC-001122334404', 'SUB_BOX')
        with self.assertRaises(CoreError):
            self.r.add_factory_device('HC-001122334402', 'ACTION_BOX', 'HC-A1', b'z'*32, 'another-setup')

    def test_stale_boot_sequence_ct_and_reboot(self):
        self.online(self.sub)
        self.online(self.action)
        self.assertTrue(self.report(seq=2))
        self.assertFalse(self.report(seq=1))
        self.assertFalse(self.report(seq=2))
        with self.assertRaises(CoreError):
            self.report(seq=3, boot=99)
        with self.assertRaises(CoreError):
            self.report(seq=3, current=float('nan'))
        self.assertTrue(self.report(seq=3, valid=False))
        self.r.close()
        self.r = Registry(Path(self.tmp.name) / 'core.db', b'k'*32)
        snapshot = self.r.snapshot(self.owner, self.home)
        self.assertEqual(snapshot['channels'][0]['availability'], 'STALE')
        self.assertIsNone(snapshot['channels'][0]['current_rms_a'])

    def test_command_requires_applied_matching_revision_and_route(self):
        device = self.bind()
        self.online(self.sub)
        self.online(self.action)
        self.report()
        command = self.r.command(self.owner, device['device_id'], True, 'request-1')
        self.assertEqual(command['status'], 'ACCEPTED')
        self.assertEqual(self.r.command(self.owner, device['device_id'], True, 'request-1')['command_id'], command['command_id'])
        with self.assertRaises(CoreError):
            self.r.command(self.owner, device['device_id'], False, 'request-1')
        self.assertEqual(self.r.snapshot(self.owner, self.home)['channels'][0]['relay_state'], 0)
        with self.assertRaises(CoreError):
            self.r.ack(self.action, command['command_id'], 'APPLIED', command['config_rev']-1, True)
        self.r.ack(self.action, command['command_id'], 'APPLIED', command['config_rev'], True)
        self.assertEqual(self.r.get_command(self.owner, command['command_id'])['status'], 'APPLIED')

    def test_rebind_revokes_pending_command_and_preserves_device(self):
        device = self.bind()
        self.online(self.sub)
        self.online(self.action)
        self.report()
        command = self.r.command(self.owner, device['device_id'], True, 'request-1')
        self.r.bind(self.owner, device['device_id'], 'HC-001122334402:CH2')
        self.assertEqual(self.r.get_command(self.owner, command['command_id'])['status'], 'FAILED')
        with self.assertRaises(CoreError):
            self.r.ack(self.action, command['command_id'], 'APPLIED', command['config_rev'], True)
        self.r.unpair(self.owner, self.action)
        with self.assertRaises(CoreError):
            self.r.session_challenge(self.action, 999)
        self.assertEqual(self.r.devices(self.owner, self.home)[0]['device_id'], device['device_id'])

    def test_current_boot_readmits_with_fresh_challenge_but_retired_boot_does_not(self):
        self.online(self.action,100)
        self.online(self.action,100)
        self.online(self.action,200)
        with self.assertRaises(CoreError):
            self.online(self.action,100)

    def test_command_generation_increases_per_channel(self):
        d=self.bind()
        self.online(self.sub); self.online(self.action); self.report()
        a=self.r.command(self.owner,d['device_id'],True,'first')
        b=self.r.command(self.owner,d['device_id'],False,'second')
        self.assertGreater(b['generation'],a['generation'])

    def test_command_refused_during_parent_or_child_ota(self):
        d=self.bind()
        self.online(self.sub); self.online(self.action); self.report()
        self.r.db.execute("INSERT INTO firmware_artifacts VALUES('fw','HC-A1','1.0.1',1,'hash','{}','sig','unused',0)")
        self.r.db.execute('INSERT INTO ota_jobs VALUES(?,?,?,?,?)',('job',self.home,'fw',0,self.owner))
        for node in (self.sub,self.action):
            self.r.db.execute("INSERT INTO ota_targets(job_id,node_id,status,updated) VALUES(?,?,'TRANSFERRING',0)",('job',node))
            with self.assertRaises(CoreError) as error:
                self.r.command(self.owner,d['device_id'],True,'ota-busy')
            self.assertEqual(error.exception.code,'ota_in_progress')
            self.r.db.execute('DELETE FROM ota_targets')

    def test_administrative_open_does_not_invalidate_live_session(self):
        self.online(self.sub); self.online(self.action); self.report()
        admin=Registry(Path(self.tmp.name)/'core.db',b'k'*32,recover=False)
        try:
            self.assertEqual(admin.get_node(self.owner,self.action)['connectivity'],'ONLINE')
        finally:
            admin.close()

    def test_room_move_is_staged_and_preserves_device_id(self):
        device=self.bind()
        room=self.r.create_room(self.owner,self.home,'Bedroom')
        old_room=self.room
        self.room=room
        parent=self.enroll('HC-001122334405','SUB_BOX')
        self.room=old_room
        claim=self.r.assign(self.owner,self.action,room,parent)
        self.assertEqual(self.r.get_node(self.owner,self.action)['registration'],'TRANSFER_PENDING')
        self.assertEqual(self.r.get_node(self.owner,self.action)['room_id'],old_room)
        secret=hashlib.sha256(b'HC-001122334402').digest()
        payload=dict(claim=claim,stored=True,peer_confirmed=True,channels=3)
        self.r.confirm_claim(claim['claim_id'],hmac.digest(secret,canonical(payload),'sha256').hex(),stored=True,peer_confirmed=True,channels=3)
        self.assertEqual(self.r.get_node(self.owner,self.action)['room_id'],room)
        self.assertEqual(self.r.devices(self.owner,self.home)[0]['device_id'],device['device_id'])

    def test_backup_integrity_and_no_clear_secrets(self):
        backup = Path(self.tmp.name) / 'backup.db'
        self.r.backup(backup)
        raw = backup.read_bytes()
        self.assertNotIn(self.token.encode(), raw)
        self.assertNotIn(self.keys[self.action], raw)
        self.assertEqual(self.r.integrity(), 'ok')


if __name__ == '__main__':
    unittest.main()
