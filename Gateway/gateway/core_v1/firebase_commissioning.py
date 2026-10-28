"""Firebase management access to the existing Core radio coordinator's registry."""
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from .provisioning import Provisioning
from .registry import require, canonical, name, uid as new_id
from .kws import CoreKws


class CoreCommissioning:
    def __init__(self, registry, config, installer_uids):
        self.r, self.config = registry, config
        self.provisioning = Provisioning(registry)
        self.home = config['home_id']
        self.kws=CoreKws(registry)
        self.r.one('SELECT * FROM homes WHERE home_id=?', (self.home,))
        self.users = {uid: 'FIREBASE-' + hashlib.sha256(uid.encode()).hexdigest()[:24]
                      for uid in installer_uids}
        with self.r.transaction():
            for user in self.users.values():
                self.r.db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',
                    (user, 'Firebase installer', hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
                self.r.db.execute('INSERT OR IGNORE INTO home_members VALUES(?,?,?)',
                                  (self.home, user, 'Installer'))
                control='CONTROL-'+user
                self.r.db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',
                                  (control,'Firebase control',hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
                self.r.db.execute("INSERT OR IGNORE INTO home_members VALUES(?,?,'Member')",(self.home,control))
            self.r.db.execute('CREATE TABLE IF NOT EXISTS core_node_labels(node_id INTEGER PRIMARY KEY REFERENCES registered_nodes,payload TEXT NOT NULL)')
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
        return {'profile': 'core-v1', 'capabilities':{'configure':True,'control':True}, 'snapshot': self.r.snapshot(self.actor(uid), self.home),
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
        if path=='/api/kws/config':
            if method=='GET' and not body:return self.kws.config(user,self.home)
            if method=='PUT':return self.kws.configure(user,self.home,body)
        if method=='POST' and path=='/api/device/update':
            return self.update_device(user,body)
        if method=='POST' and path=='/api/v1/channels/command':
            require(set(body)=={'node_id','channel','on','idempotency_key'})
            node=self.kws.scope(body['node_id']);require(node['home_id']==self.home,'forbidden',403)
            require(type(body['node_id']) is int and type(body['channel']) is int and body['channel'] in (1,2,3) and type(body['on']) is bool)
            device=self.r.one('SELECT device_id FROM device_bindings WHERE channel_id=? AND active=1',(node['factory_id']+':CH'+str(body['channel']),))
            return self.r.command('CONTROL-'+user,device['device_id'],body['on'],body['idempotency_key'])
        if method=='GET' and re.fullmatch(r'/api/v1/commands/CMD-[0-9a-f]{24}',path) and not body:
            return self.r.get_command('CONTROL-'+user,path.rsplit('/',1)[1])
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
            result={key:claim[key] for key in ('claim_id','node_id','status','expires')}
            if result['status']=='PAIRING' and result['expires']<=self.r.clock():
                result['status']='EXPIRED'
            return result
        require(False,'endpoint_denied',403)

    def update_device(self,user,body):
        allowed={'device_id','name','room','location','description'}|{f'ch{c}_{f}' for c in (1,2,3) for f in ('name','type')}
        require(isinstance(body,dict) and set(body)<=allowed and 'device_id' in body)
        ident=body['device_id'];product='SUB_BOX' if isinstance(ident,str) and ident.startswith('SB') else 'ACTION_BOX'
        node=self.kws.identity(ident,self.home,product)
        room=self.r.one('SELECT name FROM rooms WHERE room_id=?',(node['room_id'],))['name']
        require('room' not in body or body['room']==room,'room_belongs_to_subbox')
        metadata={k:name(body[k]) for k in ('name','location','description') if k in body and body[k]}
        changes=[]
        for channel in (1,2,3):
            key=f'ch{channel}';cid=node['factory_id']+f':CH{channel}'
            if not any(key+'_'+f in body for f in ('name','type')):continue
            require(product=='ACTION_BOX','invalid_channel')
            old=self.r.db.execute('SELECT d.* FROM devices d JOIN device_bindings b USING(device_id) WHERE b.channel_id=? AND b.active=1',(cid,)).fetchone()
            label=name(body.get(key+'_name',old['name'] if old else f'Kênh {channel}'))
            kind=body.get(key+'_type',old['kind'] if old else 'other')
            require(kind in ('light','fan','outlet','other','switch','pump','custom'),'invalid_device_type')
            if key+'_type' in body:metadata.setdefault('channel_types',{})[key]=kind
            kind=kind if kind in ('light','fan','outlet') else 'other'
            changes.append((cid,old,label,kind))
        with self.r.transaction():
            for cid,old,label,kind in changes:
                if old:
                    self.r.db.execute('UPDATE devices SET name=?,kind=? WHERE device_id=?',(label,kind,old['device_id']))
                    if old['kind']!=kind:self.r.bump(node['node_id'])
                else:
                    device=new_id('DEV-');self.r.db.execute('INSERT INTO devices VALUES(?,?,?,?)',(device,self.home,label,kind));self.r._bind(user,device,cid)
            previous=self.r.db.execute('SELECT payload FROM core_node_labels WHERE node_id=?',(node['node_id'],)).fetchone()
            previous_metadata=json.loads(previous[0]) if previous else {}
            metadata={**previous_metadata,**metadata,'channel_types':{**previous_metadata.get('channel_types',{}),**metadata.get('channel_types',{})}}
            self.r.db.execute('INSERT OR REPLACE INTO core_node_labels VALUES(?,?)',(node['node_id'],canonical(metadata).decode()))
            self.r.audit(user,self.home,'device_configure',str(node['node_id']))
        return {'success':True,'config_pending':bool(changes)}

    def projections(self, uid):
        snapshot=self.r.snapshot(self.actor(uid),self.home)
        rooms={r['room_id']:r['name'] for r in snapshot['rooms']}
        devices={d['device_id']:d for d in snapshot['devices']}
        result={}
        for node in snapshot['nodes']:
            if node['registration']!='REGISTERED': continue
            subbox=node['product_type']=='SUB_BOX'
            identifier=('SB' if subbox else 'AB')+node['factory_id'][3:]
            channels={}
            for channel in snapshot['channels']:
                if channel['node_id']!=node['node_id']: continue
                device=devices.get(channel.get('device_id'),{})
                fresh=channel['availability']=='ONLINE'
                channels['ch'+str(channel['number'])]={'name':device.get('name','Kênh '+str(channel['number'])),
                    'device_type':device.get('kind','custom'),'logical_device_id':device.get('device_id'),
                    'state':bool(channel['relay_state']) if fresh and channel['relay_state'] is not None else None,
                    'current':channel['current_rms_a'] if fresh and channel['ct_valid'] else None,
                    'ct_valid':bool(fresh and channel['ct_valid']),'fault_flags':channel['fault_flags']}
            labels=self.r.db.execute('SELECT payload FROM core_node_labels WHERE node_id=?',(node['node_id'],)).fetchone()
            metadata=json.loads(labels[0]) if labels else {}
            for key,value in channels.items():
                value['device_type']=metadata.get('channel_types',{}).get(key,value['device_type'])
            parent=next((n for n in snapshot['nodes'] if n['node_id']==node['parent_id']),None)
            result[identifier]={**metadata,'name':metadata.get('name',node['factory_id']),'room':rooms.get(node['room_id'],''),
                'board_model':'subbox' if subbox else 'actionbox_v2','firmware_version':node['firmware'] or '',
                'online':node['availability']=='ONLINE','last_updated':int((node['last_seen'] or 0)*1000),
                'channels':channels,'core_node_id':node['node_id'],'subbox_id':'SB'+parent['factory_id'][3:] if parent else None}
        return result
