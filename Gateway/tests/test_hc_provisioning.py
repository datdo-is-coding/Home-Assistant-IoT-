"""Commissioning proofs through the real registry and binary MQTT bridge."""
import hashlib
import hmac
from pathlib import Path
import struct
import tempfile
import unittest

from gateway.core_v1.bridge import Bridge
from gateway.core_v1.protocol import Frame, MessageType
from gateway.core_v1.provisioning import Provisioning
from gateway.core_v1.registry import CoreError, Registry

class ProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.r = Registry(Path(self.tmp.name) / 'core.db', b'k' * 32,
                          clock=lambda: self.now)
        self.user, _ = self.r.create_user('Owner')
        self.home = self.r.create_home(self.user, 'Home')
        self.room = self.r.create_room(self.user, self.home, 'Room')
        self.p = Provisioning(self.r)

    def tearDown(self):
        self.r.close()
        self.tmp.cleanup()

    def prepare(self, number, parent=None):
        factory = f'HC-0011223344{number:02X}'
        secret = hashlib.sha256(factory.encode()).digest()
        self.r.add_factory_device(factory, 'ACTION_BOX' if parent else 'SUB_BOX',
                                  'HC-A1' if parent else 'HC-S1', secret,
                                  'unique-setup-code')
        claim = self.r.claim(self.user, factory, 'unique-setup-code', self.room, parent)
        options = dict(parent_mac='001122334401') if parent else dict(
            wifi_ssid='s' * 32, wifi_password='a' * 64, mqtt_uri='mqtts://broker')
        envelope = self.p.prepare(self.user, claim['claim_id'], '11' * 32,
                                  radio_mac=f'0011223344{number:02X}', **options)
        key = hmac.digest(secret, b'HC-OPERATING-V1\0' + bytes.fromhex(claim['nonce']), 'sha256')
        body = struct.pack('<4s32sIIBB', b'HCA1', bytes.fromhex(claim['nonce']),
                           claim['node_id'], parent or 0, 3 if parent else 0, 3)
        receipt = body + hmac.digest(key, body, 'sha256')
        return claim, envelope, key, receipt

    def parent(self):
        claim, _, key, receipt = self.prepare(1)
        self.p.accept_receipt(receipt)
        return claim['node_id'], key

    def parent_receipt(self, claim, key):
        body = struct.pack('<4s32sII6s', b'HCR1', bytes.fromhex(claim['nonce']),
                           claim['node_id'], claim['parent_id'], bytes.fromhex(claim['factory_id'][3:]))
        return body + hmac.digest(key, body, 'sha256')

    def test_envelope_matches_firmware_offsets_and_preserves_full_wifi_credentials(self):
        claim, envelope, _, _ = self.prepare(1)
        packet = bytes.fromhex(envelope['packet'])
        self.assertEqual(len(packet), 547)
        self.assertEqual(packet[:8], b'HCP1\x01\x01\0\0')
        self.assertEqual(packet[20:26], bytes.fromhex('001122334401'))
        self.assertEqual(packet[32:64], b'\x11' * 32)
        self.assertEqual(packet[64:96], bytes.fromhex(claim['nonce']))
        self.assertEqual(packet[224:257], b's' * 32 + b'\0')
        self.assertEqual(packet[257:322], b'a' * 64 + b'\0')
        secret = hashlib.sha256(claim['factory_id'].encode()).digest()
        self.assertEqual(packet[515:], hmac.digest(secret, packet[:515], 'sha256'))
        stored = self.r.one('SELECT packet_cipher FROM commissioning_envelopes')['packet_cipher']
        self.assertNotIn(b's' * 32, stored)

    def test_child_waits_for_both_receipts_in_either_order(self):
        parent, key = self.parent()
        for number, parent_first in ((2, False), (3, True)):
            with self.subTest(parent_first=parent_first):
                claim, envelope, _, receipt = self.prepare(number, parent)
                self.assertEqual(len(bytes.fromhex(envelope['parent_grant'])), 110)
                peer = self.parent_receipt(claim, key)
                first, second = (peer, receipt) if parent_first else (receipt, peer)
                self.assertIsNone(self.p.accept_receipt(first))
                self.assertEqual(self.r.get_node(self.user, claim['node_id'])['registration'], 'PAIRING')
                node = self.p.accept_receipt(second)
                self.assertEqual(node['registration'], 'REGISTERED')
                self.assertEqual(len(self.r.channels(self.user, node['node_id'])), 3)
                self.assertEqual(self.p.accept_receipt(receipt)['node_id'], node['node_id'])
                self.assertEqual(self.p.accept_receipt(peer)['node_id'], node['node_id'])

    def test_wrong_receipt_and_expiry_cannot_register_or_emit_grants(self):
        parent, key = self.parent()
        claim, _, _, receipt = self.prepare(2, parent)
        tampered = receipt[:-1] + bytes([receipt[-1] ^ 1])
        with self.assertRaisesRegex(CoreError, 'auth_failed'):
            self.p.accept_receipt(tampered)
        self.assertIsNone(self.r.one('SELECT device_receipt FROM commissioning_envelopes WHERE claim_id=?',
                                    (claim['claim_id'],))['device_receipt'])
        self.now = claim['expires']
        with self.assertRaisesRegex(CoreError, 'claim_expired'):
            self.p.accept_receipt(receipt)
        with self.assertRaises(CoreError):
            self.p.pending(claim['node_id'])
        self.assertEqual(self.p.outgoing_grants(), [])
        self.assertEqual(self.r.get_node(self.user, claim['node_id'])['registration'], 'PAIRING')

    def test_foreign_user_and_second_envelope_are_rejected(self):
        claim, _, _, _ = self.prepare(1)
        other, _ = self.r.create_user('Other')
        options = dict(radio_mac='001122334401', wifi_ssid='home', mqtt_uri='mqtts://broker')
        with self.assertRaisesRegex(CoreError, 'forbidden'):
            self.p.prepare(other, claim['claim_id'], '22' * 32, **options)
        with self.assertRaisesRegex(CoreError, 'envelope_already_issued'):
            self.p.prepare(self.user, claim['claim_id'], '22' * 32, **options)

    def test_binary_handshake_retries_receipt_after_lost_accept(self):
        claim, _, key, receipt = self.prepare(1)
        bridge = Bridge(self.r)
        node = claim['node_id']
        def frame(kind, sequence, payload):
            return Frame(kind, sequence, node, 0, 123, sequence, 1, payload).encode(key)
        challenge = Frame.decode(bridge.receive(node, frame(MessageType.HELLO, 1, b'n' * 16))[0][1], key)
        bridge.receive(node, frame(MessageType.IDENTITY_RESPONSE, 2, challenge.payload[16:]))
        response = bridge.receive(node, frame(MessageType.PAIR_REQUEST, 3, receipt))
        accept = Frame.decode(response[0][1], key)
        self.assertEqual(accept.type, MessageType.PAIR_ACCEPT)
        self.assertEqual(accept.payload, bytes.fromhex(claim['nonce']))

        retry = bridge.receive(node, frame(MessageType.PAIR_REQUEST, 4, receipt))
        self.assertEqual(Frame.decode(retry[0][1], key).payload, accept.payload)
        self.assertEqual(len(self.r.rows('SELECT * FROM node_assignments WHERE active=1')), 1)

if __name__ == '__main__':
    unittest.main()
