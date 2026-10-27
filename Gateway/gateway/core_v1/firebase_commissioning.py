"""Firebase management access to the existing Core radio coordinator's registry."""
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from .provisioning import Provisioning
from .registry import require, canonical


class CoreCommissioning:
    def __init__(self, registry, config, installer_uids):
        self.r, self.config = registry, config
        self.provisioning = Provisioning(registry)
        self.home = config['home_id']
        self.r.one('SELECT * FROM homes WHERE home_id=?', (self.home,))
        self.users = {uid: 'FIREBASE-' + hashlib.sha256(uid.encode()).hexdigest()[:24]
                      for uid in installer_uids}
        with self.r.transaction():
            for user in self.users.values():
                self.r.db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',
                    (user, 'Firebase installer', hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
                self.r.db.execute('INSERT OR IGNORE INTO home_members VALUES(?,?,?)',
                                  (self.home, user, 'Installer'))
            self.r.db.execute('''CREATE TABLE IF NOT EXISTS firebase_commissioning_requests(
                actor TEXT, request_key TEXT, fingerprint TEXT NOT NULL, claim_id TEXT NOT NULL,
                PRIMARY KEY(actor,request_key))''')
            for node, parent in config.get('parents', {}).items():
                self.r.db.execute('''INSERT INTO commissioning_generations VALUES(?,?)
                    ON CONFLICT(parent_id) DO UPDATE SET generation=max(generation,excluded.generation)''',
                    (int(node), parent['generation']))

    def actor(self, uid):
        require(uid in self.users, 'forbidden', 403)
        return self.users[uid]

    def context(self, uid):
        return {'profile': 'core-v1', 'snapshot': self.r.snapshot(self.actor(uid), self.home),
                'defaults': {key: self.config[key] for key in ('channel','mqtt_uri','ota_pubkey','parents')
                             if key in self.config}}

    def request(self, uid, method, path, body):
        user = self.actor(uid)
        uri = urlsplit(path)
        query = parse_qs(uri.query)
        require(not uri.scheme and not uri.netloc and not uri.fragment and
                set(query) <= {'home_id'} and query.get('home_id', [self.home]) == [self.home],
                'forbidden', 403)
        path = uri.path
        if method == 'GET' and path == '/api/v1/states/snapshot' and not body:
            return self.r.snapshot(user, self.home)
        if method == 'POST' and path == '/api/v1/nodes/claim':
            require(set(body) <= {'factory_id','setup_code','room_id','parent_id','idempotency_key'})
            require(self.r.one('SELECT home_id FROM rooms WHERE room_id=?',(body['room_id'],))['home_id']==self.home,'forbidden',403)
            key = body.get('idempotency_key')
            require(isinstance(key,str) and 1 <= len(key) <= 200, 'idempotency_required')
            fingerprint = hashlib.sha256(canonical(body)).hexdigest()
            old = self.r.db.execute('SELECT * FROM firebase_commissioning_requests WHERE actor=? AND request_key=?',
                                    (user,'claim:'+key)).fetchone()
            if old:
                require(old['fingerprint']==fingerprint,'idempotency_conflict',409)
                return self.r.one('SELECT * FROM pairing_claims WHERE claim_id=?',(old['claim_id'],))
            claim = self.r.claim(user,body['factory_id'],body['setup_code'],body['room_id'],body.get('parent_id'))
            self.r.db.execute('INSERT INTO firebase_commissioning_requests VALUES(?,?,?,?)',
                              (user,'claim:'+key,fingerprint,claim['claim_id']))
            return claim
        if method == 'POST' and path == '/api/v1/provisioning/prepare':
            require(set(body) <= {'claim_id','challenge','radio_mac','parent_mac','channel',
                                 'wifi_ssid','wifi_password','mqtt_uri','ota_pubkey'})
            claim = self.r.one('SELECT c.*,r.home_id FROM pairing_claims c JOIN rooms r USING(room_id) WHERE claim_id=?',
                               (body['claim_id'],))
            require(claim['user_id']==user and claim['home_id']==self.home,'forbidden',403)
            require(claim['status']=='PAIRING' and claim['expires']>self.r.clock(),'claim_expired')
            options = {k:v for k,v in body.items() if k not in ('claim_id','challenge')}
            for field in ('channel','ota_pubkey'):
                expected = self.config[field]
                require(field not in options or options[field]==expected,'invalid_'+field)
                options[field] = expected
            if claim['parent_id'] is None:
                expected=self.config['mqtt_uri']
                require('mqtt_uri' not in options or options['mqtt_uri']==expected,'invalid_network')
                options['mqtt_uri']=expected
            else:
                parent=self.config.get('parents',{}).get(str(claim['parent_id']))
                require(parent is not None,'parent_metadata_missing')
                expected=parent['sta_mac']
                require('parent_mac' not in options or options['parent_mac'].replace(':','').lower()==expected.replace(':','').lower(),'invalid_parent')
                options['parent_mac']=expected
            fingerprint=hashlib.sha256(canonical(body)).hexdigest()
            previous=self.r.db.execute('SELECT * FROM firebase_commissioning_requests WHERE actor=? AND request_key=?',
                                       (user,'prepare:'+claim['claim_id'])).fetchone()
            if previous:
                require(previous['fingerprint']==fingerprint,'envelope_already_issued')
                stored=self.r.one('SELECT packet_cipher FROM commissioning_envelopes WHERE claim_id=?',(claim['claim_id'],))
                return {'packet':self.r.cipher.decrypt(stored['packet_cipher']).hex(),
                        'claim_id':claim['claim_id'],'expires':int(claim['expires'])}
            result=self.provisioning.prepare(user,claim['claim_id'],body['challenge'],**options)
            self.r.db.execute('INSERT INTO firebase_commissioning_requests VALUES(?,?,?,?)',
                              (user,'prepare:'+claim['claim_id'],fingerprint,claim['claim_id']))
            return {key:result[key] for key in ('claim_id','packet','expires')}
        if method == 'GET' and re.fullmatch(r'/api/v1/provisioning/CLAIM-[0-9a-f]{24}',path) and not body:
            claim=self.r.one('SELECT c.*,r.home_id FROM pairing_claims c JOIN rooms r USING(room_id) WHERE claim_id=?',
                             (path.rsplit('/',1)[1],))
            require(claim['user_id']==user and claim['home_id']==self.home,'forbidden',403)
            return {key:claim[key] for key in ('claim_id','node_id','status','expires')}
        require(False,'endpoint_denied',403)

    def projections(self, uid):
        snapshot=self.r.snapshot(self.actor(uid),self.home)
        rooms={r['room_id']:r['name'] for r in snapshot['rooms']}
        result={}
        for node in snapshot['nodes']:
            if node['registration']!='REGISTERED': continue
            subbox=node['product_type']=='SUB_BOX'
            identifier=('SB' if subbox else 'AB')+node['factory_id'][3:]
            channels={}
            for channel in snapshot['channels']:
                if channel['node_id']!=node['node_id']: continue
                # Unbound channels are inventory only; this transport does not accept relay commands.
                channels['ch'+str(channel['number'])]={'name':'Kênh '+str(channel['number']),
                                                       'device_type':'custom'}
            result[identifier]={'name':node['factory_id'],'room':rooms.get(node['room_id'],''),
                'board_model':'subbox' if subbox else 'actionbox_v2','firmware_version':node['firmware'] or '',
                'online':node['availability']=='ONLINE','last_updated':int((node['last_seen'] or 0)*1000),
                'channels':channels,'core_node_id':node['node_id']}
        return result
