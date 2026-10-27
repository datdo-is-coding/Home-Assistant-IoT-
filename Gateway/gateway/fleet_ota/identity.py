"""Firebase human identity and P-256 proof-of-possession gateway identity."""
import asyncio
import base64
from dataclasses import dataclass
import json
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def unb64(value):
    if not isinstance(value, str) or len(value) > 32768:
        raise ValueError('invalid encoding')
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


def verify_bytes(message, signature, public_key):
    try:
        raw = unb64(signature)
        if len(raw) != 64 or not isinstance(public_key.curve, ec.SECP256R1):
            raise ValueError('invalid signature')
        der = utils.encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big'))
        public_key.verify(der, message, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, TypeError, AttributeError, ValueError) as error:
        raise ValueError('invalid signature') from error


def verify_signed(envelope, public_key):
    try:
        verify_bytes(canonical_json(envelope['payload']), envelope['signature'], public_key)
        return envelope['payload']
    except (KeyError, TypeError) as error:
        raise ValueError('invalid signed envelope') from error


@dataclass(frozen=True)
class Principal:
    uid: str
    roles: frozenset = frozenset()
    gateway_id: str = ''
    home_id: str = ''
    tenant_id: str = ''
    owner_epoch: int = 0


class GrantSigner:
    def __init__(self, private_key, key_id):
        if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(private_key.curve, ec.SECP256R1):
            raise ValueError('P-256 signing key required')
        self.private_key, self.key_id = private_key, key_id

    def sign_bytes(self, message):
        r, s = utils.decode_dss_signature(self.private_key.sign(message, ec.ECDSA(hashes.SHA256())))
        return b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))

    def sign(self, payload):
        return {'payload': payload, 'signature': self.sign_bytes(canonical_json(payload)), 'key_id': self.key_id, 'algorithm': 'ES256'}

    def public_pem(self):
        return self.private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')

    def device_token(self, identity, now):
        header = b64(canonical_json({'alg': 'ES256', 'typ': 'JWT', 'kid': self.key_id}))
        claims = b64(canonical_json(dict(identity, iss='homecompetition-ota', aud='homecompetition-ota-device', iat=now, exp=now + 900)))
        return header + '.' + claims + '.' + self.sign_bytes((header + '.' + claims).encode('ascii'))


class FirebaseAuth:
    def __init__(self, firebase_app, signer, clock=time.time):
        self.firebase_app, self.signer, self.clock = firebase_app, signer, clock

    async def __call__(self, token):
        try:
            header, payload, signature = token.split('.')
            claims = json.loads(unb64(payload))
            is_device = claims.get('iss') == 'homecompetition-ota'
        except (ValueError, TypeError, AttributeError):
            raise ValueError('invalid token')
        if is_device:
            verify_bytes((header + '.' + payload).encode('ascii'), signature, self.signer.private_key.public_key())
            metadata = json.loads(unb64(header))
            now = int(self.clock())
            if metadata != {'alg': 'ES256', 'typ': 'JWT', 'kid': self.signer.key_id} or claims.get('aud') != 'homecompetition-ota-device' or type(claims.get('iat')) is not int or type(claims.get('exp')) is not int or not claims['iat'] <= now < claims['exp'] or claims['exp'] - claims['iat'] > 900:
                raise ValueError('invalid device token')
            return Principal(claims['gateway_id'], gateway_id=claims['gateway_id'], home_id=claims['home_id'], tenant_id=claims['tenant_id'], owner_epoch=claims['owner_epoch'])
        from firebase_admin import auth
        claims = await asyncio.to_thread(auth.verify_id_token, token, app=self.firebase_app, check_revoked=True)
        roles = claims.get('ota_roles', [])
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise ValueError('invalid roles')
        return Principal(claims['uid'], frozenset(roles))
