"""Signed Core OTA target v2 (112-byte header plus raw P-256 signature).

The full cloud manifest supplies freshness and dependency checks. This compact
target is independently checked by the Box before it writes an alternate slot.
"""
import hashlib
import json
import re
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

ROLE_SUBBOX = 1
ROLE_ACTIONBOX = 2
ARTIFACT_FIRMWARE = 1
HEADER = struct.Struct('<BBBB32s16sI32sHHHHQII')
HEADER_SIZE = HEADER.size
TARGET_SIZE = HEADER_SIZE + 64
MAX_IMAGE_SIZE = 0x2f0000
FIELDS = ('schema', 'role', 'artifact_type', 'flags', 'compatibility_id', 'version',
          'size', 'sha256', 'min_agent', 'min_bootloader', 'protocol_min', 'protocol_max',
          'release_counter', 'security_epoch', 'key_id')


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _public_key(public_key):
    _require(isinstance(public_key, ec.EllipticCurvePublicKey)
             and isinstance(public_key.curve, ec.SECP256R1), 'invalid_public_key')
    return public_key


def key_id(public_key):
    """Key identifier bound to the provisioned 65-byte uncompressed trust root."""
    raw = _public_key(public_key).public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], 'little')


def compatibility_id(model, hardware_class, chip, layout, security_profile):
    """SHA-256 of the UTF-8 canonical JSON tuple; no inferred hardware revision."""
    values = (model, hardware_class, chip, layout, security_profile)
    _require(all(isinstance(value, str) and 0 < len(value) <= 128
                 and value == value.strip() and all(32 <= ord(c) < 127 for c in value)
                 for value in values), 'invalid_compatibility_tuple')
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def target_header(manifest):
    _require(isinstance(manifest, dict) and set(manifest) == set(FIELDS), 'invalid_fields')
    m = manifest
    limits = dict(schema=255, role=255, artifact_type=255, flags=255, size=MAX_IMAGE_SIZE,
                  min_agent=65535, min_bootloader=65535, protocol_min=65535,
                  protocol_max=65535, release_counter=(1 << 64) - 1,
                  security_epoch=(1 << 32) - 1, key_id=(1 << 32) - 1)
    for name, maximum in limits.items():
        _require(type(m[name]) is int and 0 <= m[name] <= maximum, 'invalid_' + name)
    _require(m['schema'] == 2 and m['role'] in (ROLE_SUBBOX, ROLE_ACTIONBOX)
             and m['artifact_type'] == ARTIFACT_FIRMWARE and m['flags'] == 0, 'unsupported_target')
    _require(m['size'] > 0 and m['release_counter'] > 0 and m['min_agent'] > 0
             and m['min_bootloader'] > 0 and 0 < m['protocol_min'] <= m['protocol_max'], 'invalid_bounds')
    _require(isinstance(m['version'], str)
             and re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', m['version']) is not None, 'invalid_version')
    for name in ('compatibility_id', 'sha256'):
        _require(isinstance(m[name], str) and re.fullmatch('[0-9a-f]{64}', m[name]) is not None
                 and m[name] != '00' * 32, 'invalid_' + name)
    values = [m[name] for name in FIELDS]
    values[4] = bytes.fromhex(m['compatibility_id'])
    values[5] = m['version'].encode('ascii')
    values[7] = bytes.fromhex(m['sha256'])
    return HEADER.pack(*values)


def parse_target(packet):
    """Decode a canonical v2 packet; this function alone does not verify trust."""
    _require(isinstance(packet, bytes) and len(packet) == TARGET_SIZE, 'invalid_target_length')
    values = list(HEADER.unpack(packet[:HEADER_SIZE]))
    values[4] = values[4].hex()
    raw_version = values[5]
    try:
        values[5] = raw_version.split(b'\0', 1)[0].decode('ascii')
    except UnicodeDecodeError as error:
        raise ValueError('invalid_version') from error
    values[7] = values[7].hex()
    manifest = dict(zip(FIELDS, values))
    _require(target_header(manifest) == packet[:HEADER_SIZE], 'noncanonical_target')
    return manifest


def verify_target(packet, public_key, *, compatibility_id, role, agent_version=2,
                  bootloader_api=1, protocol_version=1, confirmed_counter=0,
                  security_epoch=0, max_size=MAX_IMAGE_SIZE, image=None):
    m = parse_target(packet)
    _require(m['key_id'] == key_id(public_key), 'wrong_key_id')
    signature = packet[HEADER_SIZE:]
    der = utils.encode_dss_signature(int.from_bytes(signature[:32], 'big'),
                                     int.from_bytes(signature[32:], 'big'))
    try:
        public_key.verify(der, packet[:HEADER_SIZE], ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as error:
        raise ValueError('invalid_signature') from error
    _require(m['compatibility_id'] == compatibility_id and m['role'] == role, 'wrong_target')
    _require(m['min_agent'] <= agent_version and m['min_bootloader'] <= bootloader_api
             and m['protocol_min'] <= protocol_version <= m['protocol_max'], 'incompatible_agent')
    _require(m['size'] <= max_size, 'image_too_large')
    _require(m['release_counter'] > confirmed_counter and m['security_epoch'] >= security_epoch,
             'release_downgrade')
    if image is not None:
        _require(isinstance(image, bytes) and len(image) == m['size']
                 and hashlib.sha256(image).hexdigest() == m['sha256'], 'hash_mismatch')
    return m
