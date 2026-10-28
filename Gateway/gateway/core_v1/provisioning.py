"""Physical-presence commissioning over Espressif protocomm security1.

Only ciphertext goes over the provisioning radio. This module prepares the
factory-authenticated envelope and verifies independent device/parent receipts.
"""
import hmac
import secrets
import struct
from .registry import canonical, require

ENROLLMENT = struct.Struct('<4sBBHIII6s6s32s32s32s32s16s16s32s33s65s128s65s')
GRANT = struct.Struct('<4sIII32s6s16sQ')
RECEIPT = struct.Struct('<4s32sIIBB')
PEER_RECEIPT = struct.Struct('<4s32sII6s')


def mac_bytes(value):
    require(isinstance(value, str), 'invalid_mac')
    try:
        result = bytes.fromhex(value.replace(':', ''))
    except ValueError:
        result = b''
    require(len(result) == 6 and not result[0] & 1 and any(result), 'invalid_mac')
    return result


def fixed(value, length):
    require(isinstance(value, str) and '\0' not in value, 'invalid_string')
    value = value.encode('utf-8')
    require(len(value) < length, 'string_too_long')
    return value.ljust(length, b'\0')


def tagged(key, body):
    return body + hmac.digest(key, body, 'sha256')


def verify(key, packet, size):
    require(isinstance(packet, bytes) and len(packet) == size + 32, 'invalid_packet')
    require(hmac.compare_digest(hmac.digest(key, packet[:size], 'sha256'), packet[size:]), 'auth_failed', 403)
    return packet[:size]


class Provisioning:
    def __init__(self, registry):
        self.r = registry
        self.r.db.executescript('''
          CREATE TABLE IF NOT EXISTS commissioning_envelopes(
            claim_id TEXT PRIMARY KEY REFERENCES pairing_claims(claim_id),
            packet_cipher BLOB NOT NULL, grant_cipher BLOB, child_mac BLOB NOT NULL,
            device_receipt BLOB, parent_receipt BLOB);
          CREATE TABLE IF NOT EXISTS commissioning_generations(
            parent_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS commissioning_radio_keys(
            parent_id INTEGER PRIMARY KEY REFERENCES registered_nodes(node_id) ON DELETE CASCADE,
            pmk_cipher BLOB NOT NULL);
        ''')

    def radio_key(self, parent):
        row = self.r.db.execute('SELECT pmk_cipher FROM commissioning_radio_keys WHERE parent_id=?',
                                (parent,)).fetchone()
        return self.r.cipher.decrypt(row['pmk_cipher']) if row else None

    def remember_radio_key(self, parent, pmk):
        require(isinstance(pmk, bytes) and len(pmk) == 16 and any(pmk), 'invalid_radio_key')
        node = self.r.one('SELECT f.product_type FROM registered_nodes n JOIN factory_devices f USING(factory_id) WHERE n.node_id=?', (parent,))
        require(node['product_type'] == 'SUB_BOX', 'invalid_parent')
        old = self.radio_key(parent)
        require(old is None or hmac.compare_digest(old, pmk), 'radio_key_conflict')
        if old is None:
            self.r.db.execute('INSERT INTO commissioning_radio_keys VALUES(?,?)',
                              (parent, self.r.cipher.encrypt(pmk)))

    def prepare(self, user, claim_id, challenge, *, radio_mac, parent_mac=None,
                channel=1, wifi_ssid='', wifi_password='', mqtt_uri='', ota_pubkey=''):
        """Build once per claim; changing any setting requires a fresh claim.

        challenge is the 32-byte hex response from encrypted hc-info. radio_mac
        is the device STA MAC reported there (Base MAC is identity, not routing).
        """
        c = self.r.one('SELECT * FROM pairing_claims WHERE claim_id=?', (claim_id,))
        require(c['user_id'] == user, 'forbidden', 403)
        require(c['status'] == 'PAIRING' and c['expires'] > self.r.clock(), 'claim_expired')
        room = self.r.one('SELECT * FROM rooms WHERE room_id=?', (c['room_id'],))
        self.r.authorize(user, room['home_id'], ('Owner', 'Installer'))
        f = self.r.one('SELECT * FROM factory_devices WHERE factory_id=?', (c['factory_id'],))
        require(not f['revoked'], 'revoked', 403)
        require(type(channel) is int and 1 <= channel <= 13, 'invalid_channel')
        try:
            challenge_bytes = bytes.fromhex(challenge)
            pubkey = bytes.fromhex(ota_pubkey) if ota_pubkey else bytes(65)
        except (ValueError, TypeError):
            require(False, 'invalid_hex')
        require(len(challenge_bytes) == 32 and any(challenge_bytes), 'invalid_challenge')
        require(len(pubkey) == 65 and (not any(pubkey) or pubkey[0] == 4), 'invalid_ota_key')
        child_mac = mac_bytes(radio_mac)
        subbox = f['product_type'] == 'SUB_BOX'
        require((subbox and parent_mac is None) or (not subbox and parent_mac is not None), 'invalid_parent')
        require(subbox or not (wifi_ssid or wifi_password or mqtt_uri), 'actionbox_router_forbidden')
        if subbox:
            require(bool(wifi_ssid) and mqtt_uri.startswith('mqtts://'), 'secure_network_required')
        previous = self.r.db.execute('SELECT * FROM commissioning_envelopes WHERE claim_id=?', (claim_id,)).fetchone()
        require(previous is None, 'envelope_already_issued')
        parent_radio = bytes(6) if subbox else mac_bytes(parent_mac)
        nonce = bytes.fromhex(c['nonce'])
        secret = self.r.cipher.decrypt(f['secret'])
        lmk = secrets.token_bytes(16)
        pmk = self.radio_key(c['node_id'] if subbox else c['parent_id'])
        if subbox and pmk is None:
            pmk = secrets.token_bytes(16)
        require(pmk is not None, 'parent_radio_key_missing')
        n = self.r.one('SELECT config_rev,registration FROM registered_nodes WHERE node_id=?', (c['node_id'],))
        revision = n['config_rev'] + (n['registration'] == 'TRANSFER_PENDING')
        body = ENROLLMENT.pack(b'HCP1', 1 if subbox else 2, channel, 0,
                              c['node_id'], c['parent_id'] or 0, revision,
                              bytes.fromhex(c['factory_id'][3:]), parent_radio,
                              challenge_bytes, nonce, fixed(claim_id, 32), fixed(c['room_id'], 32),
                              pmk, lmk, fixed(f['model'], 32), fixed(wifi_ssid, 33),
                              fixed(wifi_password, 65), fixed(mqtt_uri, 128), pubkey)
        packet = tagged(secret, body)
        grant = None
        with self.r.transaction():
            if subbox:
                self.remember_radio_key(c['node_id'], pmk)
            if not subbox:
                parent = self.r.get_node(user, c['parent_id'])
                require(parent['registration'] == 'REGISTERED' and parent['room_id'] == c['room_id'], 'invalid_parent')
                self.r.db.execute('INSERT INTO commissioning_generations VALUES(?,1) ON CONFLICT(parent_id) DO UPDATE SET generation=generation+1', (c['parent_id'],))
                generation = self.r.one('SELECT generation FROM commissioning_generations WHERE parent_id=?', (c['parent_id'],))['generation']
                grant = tagged(self.r.node_key(c['parent_id']), GRANT.pack(b'HCG1', c['node_id'], c['parent_id'], parent['config_rev'], nonce, child_mac, lmk, generation))
            self.r.db.execute('INSERT INTO commissioning_envelopes(claim_id,packet_cipher,grant_cipher,child_mac) VALUES(?,?,?,?)',
                              (claim_id, self.r.cipher.encrypt(packet), self.r.cipher.encrypt(grant) if grant else None, child_mac))
        return dict(claim_id=claim_id, packet=packet.hex(), parent_grant=grant.hex() if grant else None,
                    parent_id=c['parent_id'], expires=int(c['expires']))

    def accept_receipt(self, receipt):
        """Accept device or parent receipt in either order. Return registered node
        only after both independently authenticated receipts are persisted.
        """
        require(isinstance(receipt, bytes) and len(receipt) in (78, 82), 'invalid_packet')
        require(receipt[:4] in (b'HCA1', b'HCR1'), 'invalid_packet')
        nonce = receipt[4:36].hex()
        c = self.r.one('SELECT * FROM pairing_claims WHERE nonce=?', (nonce,))
        require(c['status'] == 'REGISTERED' or (c['status'] == 'PAIRING' and c['expires'] > self.r.clock()), 'claim_expired')
        e = self.r.one('SELECT * FROM commissioning_envelopes WHERE claim_id=?', (c['claim_id'],))
        f = self.r.one('SELECT * FROM factory_devices WHERE factory_id=?', (c['factory_id'],))
        require(not f['revoked'], 'revoked', 403)
        secret = self.r.cipher.decrypt(f['secret'])
        opkey = hmac.digest(secret, b'HC-OPERATING-V1\0' + bytes.fromhex(nonce), 'sha256')
        channels = 3 if c['parent_id'] else 0
        if receipt[:4] == b'HCA1':
            _, _, node, parent, actual_channels, flags = RECEIPT.unpack(verify(opkey, receipt, RECEIPT.size))
            require((node, parent, actual_channels, flags) == (c['node_id'], c['parent_id'] or 0, channels, 3), 'configuration_unconfirmed')
            field = 'device_receipt'
        else:
            require(c['parent_id'] is not None, 'invalid_parent')
            _, _, node, parent, child_mac = PEER_RECEIPT.unpack(verify(self.r.node_key(c['parent_id']), receipt, PEER_RECEIPT.size))
            require((node, parent, child_mac) == (c['node_id'], c['parent_id'], e['child_mac']), 'peer_mismatch')
            field = 'parent_receipt'
        if c['status'] == 'REGISTERED':
            require(e[field] is not None and hmac.compare_digest(e[field], receipt), 'receipt_mismatch', 403)
            self.r.node_key(c['node_id'])
            return self.r.get_node(c['user_id'], c['node_id'])
        self.r.db.execute(f'UPDATE commissioning_envelopes SET {field}=? WHERE claim_id=?', (receipt, c['claim_id']))
        e = self.r.one('SELECT * FROM commissioning_envelopes WHERE claim_id=?', (c['claim_id'],))
        if not e['device_receipt'] or (c['parent_id'] and not e['parent_receipt']):
            return None
        claim = {k: c[k] for k in ('claim_id','node_id','factory_id','room_id','parent_id','nonce','expires')}
        claim['expires'] = int(claim['expires'])
        proof = hmac.digest(secret, canonical(dict(claim=claim, stored=True, peer_confirmed=True, channels=channels)), 'sha256').hex()
        return self.r.confirm_claim(c['claim_id'], proof, stored=True, peer_confirmed=True, channels=channels)

    def pending(self, node):
        """Restricted key/route for commissioning frames; never an operating key lookup."""
        c = self.r.one("SELECT c.*,f.secret,f.revoked FROM pairing_claims c JOIN factory_devices f USING(factory_id) JOIN commissioning_envelopes e USING(claim_id) WHERE c.node_id=? AND c.status='PAIRING' AND c.expires>? ORDER BY c.expires DESC LIMIT 1", (node, self.r.clock()))
        require(not c['revoked'], 'revoked', 403)
        secret = self.r.cipher.decrypt(c['secret'])
        return hmac.digest(secret, b'HC-OPERATING-V1\0' + bytes.fromhex(c['nonce']), 'sha256'), c['parent_id']

    def outgoing_grants(self):
        rows = self.r.rows("SELECT c.*,e.grant_cipher FROM commissioning_envelopes e JOIN pairing_claims c USING(claim_id) JOIN factory_devices f USING(factory_id) WHERE c.status='PAIRING' AND c.expires>? AND f.revoked=0 AND e.grant_cipher IS NOT NULL AND e.parent_receipt IS NULL", (self.r.clock(),))
        return [(c['parent_id'], self.r.cipher.decrypt(c['grant_cipher'])) for c in rows]
