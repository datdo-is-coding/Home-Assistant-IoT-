"""Byte-level commercial OTA target contract and trust-boundary checks."""
import hashlib
import struct
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from gateway.fleet_ota.manifest import (
    ARTIFACT_FIRMWARE, ROLE_SUBBOX, compatibility_id, key_id, parse_target,
    target_header, verify_target,
)


def vector():
    private = ec.derive_private_key(1, ec.SECP256R1())
    image = b'commercial-ota-vector\x00\xff'
    manifest = dict(schema=2, role=ROLE_SUBBOX, artifact_type=ARTIFACT_FIRMWARE,
                    flags=0, compatibility_id=hashlib.sha256(b'pilot-class').hexdigest(),
                    version='2.0.0', size=len(image), sha256=hashlib.sha256(image).hexdigest(),
                    min_agent=2, min_bootloader=1, protocol_min=1, protocol_max=1,
                    release_counter=0x0102030405060708, security_epoch=3,
                    key_id=key_id(private.public_key()))
    return private, image, manifest


def signed(private, manifest):
    raw = target_header(manifest)
    r, s = utils.decode_dss_signature(private.sign(raw, ec.ECDSA(hashes.SHA256())))
    return raw + r.to_bytes(32, 'big') + s.to_bytes(32, 'big')


class FleetManifestTest(unittest.TestCase):
    def setUp(self):
        self.private, self.image, self.manifest = vector()
        self.packet = signed(self.private, self.manifest)
        self.policy = dict(compatibility_id=self.manifest['compatibility_id'], role=ROLE_SUBBOX)

    def verify(self, packet=None, **policy):
        return verify_target(self.packet if packet is None else packet, self.private.public_key(),
                             **{**self.policy, **policy})

    def test_packed_layout_roundtrip_and_image(self):
        raw = target_header(self.manifest)
        self.assertEqual(len(raw), 112)
        self.assertEqual(len(self.packet), 176)
        self.assertEqual(raw[:4], b'\x02\x01\x01\x00')
        self.assertEqual(raw[36:52], b'2.0.0' + b'\0' * 11)
        self.assertEqual(raw[52:56], struct.pack('<I', len(self.image)))
        self.assertEqual(raw[88:96], b'\x02\x00\x01\x00\x01\x00\x01\x00')
        self.assertEqual(raw[96:108], b'\x08\x07\x06\x05\x04\x03\x02\x01\x03\x00\x00\x00')
        self.assertEqual(parse_target(self.packet), self.manifest)
        self.assertEqual(self.verify(image=self.image), self.manifest)

    def test_every_header_byte_is_authenticated(self):
        for at in range(176):
            bad = bytearray(self.packet)
            bad[at] ^= 1
            with self.subTest(at=at), self.assertRaises(ValueError):
                self.verify(bytes(bad))

    def test_policy_hash_key_counter_and_epoch_rejected(self):
        for policy in (dict(compatibility_id='00' * 32), dict(role=2),
                       dict(agent_version=1), dict(bootloader_api=0),
                       dict(protocol_version=2), dict(max_size=1),
                       dict(confirmed_counter=self.manifest['release_counter']),
                       dict(security_epoch=4), dict(image=self.image + b'x')):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.verify(**policy)
        with self.assertRaises(ValueError):
            verify_target(self.packet, ec.derive_private_key(2, ec.SECP256R1()).public_key(), **self.policy)

    def test_strict_fields_types_versions_and_lengths(self):
        for field, value in [('schema', 1), ('role', 0), ('artifact_type', 2), ('flags', 1),
                             ('version', ''), ('version', 'a' * 16), ('version', 'bad/name'),
                             ('size', 0), ('size', True), ('size', 0x300000),
                             ('sha256', 'F' * 64), ('compatibility_id', '00' * 32),
                             ('release_counter', 0), ('release_counter', 1 << 64),
                             ('security_epoch', -1), ('min_agent', 0),
                             ('protocol_min', 2), ('key_id', 1 << 32)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                target_header({**self.manifest, field: value})
        with self.assertRaises(ValueError):
            target_header({**self.manifest, 'unknown': 1})
        for length in (0, 68, 112, 132, 175, 177, 196):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse_target((self.packet + b'\0' * 196)[:length])
        bad = bytearray(self.packet)
        bad[42] = 0x41  # Reject noncanonical bytes after the version's NUL.
        with self.assertRaises(ValueError):
            parse_target(bytes(bad))

    def test_compatibility_tuple_is_unambiguous_and_explicit(self):
        values = ('HC-S1', 'pilot-mac-001122334455', 'esp32s3', 'layout-sha256', 'unenforced-sb')
        self.assertEqual(compatibility_id(*values), compatibility_id(*values))
        self.assertNotEqual(compatibility_id(*values), compatibility_id(*values[:1], 'revision-B', *values[2:]))
        with self.assertRaises(ValueError):
            compatibility_id('HC-S1', '', *values[2:])


if __name__ == '__main__':
    unittest.main()
