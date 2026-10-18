"""Transactional ownership, bindings, reported state and durable command outbox."""
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import time
from .database import Database

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

class CoreError(Exception):
    def __init__(self, code, message=None, status=409):
        self.code, self.status = code, status
        super().__init__(message or code)

def require(condition, code='invalid_input', status=400):
    if not condition:
        raise CoreError(code, status=status)

def name(value):
    require(isinstance(value, str) and 1 <= len(value.strip()) <= 100 and not any(ord(c) < 32 for c in value))
    return value.strip()

def uid(prefix):
    return prefix + secrets.token_hex(12)

class Registry(Database):
    def __init__(self, path, master_key, clock=time.time, *, recover=True):
        super().__init__(path, master_key)
        self.clock = clock
        if recover:
            with self.transaction():
                self.db.execute("UPDATE registered_nodes SET connectivity='OFFLINE', last_seen=NULL")
                self.db.execute("UPDATE commands SET status='TIMEOUT',reason='gateway_restart' WHERE status IN ('RECEIVED','ACCEPTED')")

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        if row is None:
            raise CoreError('not_found', status=404)
        return dict(row)

    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args)]

    def authorize(self, user, home, roles=('Owner','Member','Installer')):
        row = self.db.execute('SELECT role FROM home_members WHERE user_id=? AND home_id=?', (user, home)).fetchone()
        require(row is not None and row[0] in roles, 'forbidden', 403)

    def event(self, home, kind, data):
        self.db.execute('INSERT INTO state_events(home_id,kind,data,created) VALUES(?,?,?,?)', (home, kind, canonical(data).decode(), self.clock()))

        self.db.execute('DELETE FROM state_events WHERE event_id <= (SELECT coalesce(max(event_id),0)-10000 FROM state_events)')

    def audit(self, user, home, action, target):
        self.db.execute('INSERT INTO audit_logs(home_id,user_id,action,target,created) VALUES(?,?,?,?,?)', (home,user,action,str(target),self.clock()))

    def create_user(self, label):
        user, token = uid('USR-'), secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO users VALUES(?,?,?)', (user,name(label),hashlib.sha256(token.encode()).hexdigest()))
        return user, token

    def authenticate(self, token):
        require(isinstance(token,str) and 20 <= len(token) <= 256, 'unauthorized', 401)
        row = self.db.execute('SELECT user_id FROM users WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        require(row is not None, 'unauthorized', 401)
        return row[0]

    def create_home(self, user, label):
        home = uid('HOME-')
        with self.transaction():
            self.db.execute('INSERT INTO homes VALUES(?,?)', (home,name(label)))
            self.db.execute('INSERT INTO home_members VALUES(?,?,?)', (home,user,'Owner'))
        return home

    def add_member(self, user, home, member, role):
        self.authorize(user, home, ('Owner',))
        require(role in ('Owner','Member','Installer'))
        with self.transaction():
            self.db.execute('INSERT INTO home_members VALUES(?,?,?) ON CONFLICT(home_id,user_id) DO UPDATE SET role=excluded.role', (home,member,role))
            self.audit(user,home,'membership',member)

    def homes(self, user):
        return self.rows('SELECT h.*,m.role FROM homes h JOIN home_members m USING(home_id) WHERE m.user_id=?', (user,))

    def create_room(self, user, home, label):
        self.authorize(user,home,('Owner','Installer'))
        room = uid('ROOM-')
        with self.transaction():
            self.db.execute('INSERT INTO rooms VALUES(?,?,?)', (room,home,name(label)))
            self.audit(user,home,'room_created',room)
        return room

    def rooms(self, user, home):
        self.authorize(user, home)
        return self.rows('SELECT * FROM rooms WHERE home_id=?',(home,))

    def add_factory_device(self, factory, kind, model, secret, setup_code):
        require(isinstance(factory,str) and re.fullmatch(r'HC-[0-9A-F]{12}',factory) is not None)
        require(kind in ('ACTION_BOX','SUB_BOX') and isinstance(secret,bytes) and len(secret)==32)
        require(isinstance(setup_code,str) and 12<=len(setup_code)<=128)
        try:
            self.db.execute('INSERT INTO factory_devices(factory_id,product_type,model,secret,setup_hash) VALUES(?,?,?,?,?)',
                            (factory,kind,name(model),self.cipher.encrypt(secret),hashlib.sha256(setup_code.encode()).hexdigest()))
        except sqlite3.IntegrityError as e:
            raise CoreError('factory_exists') from e

    def claim(self, user, factory, setup_code, room, parent=None):
        room_row = self.one('SELECT * FROM rooms WHERE room_id=?',(room,))
        self.authorize(user,room_row['home_id'],('Owner','Installer'))
        f = self.one('SELECT * FROM factory_devices WHERE factory_id=?',(factory,))
        require(isinstance(setup_code,str) and len(setup_code)<=128)
        require(not f['revoked'] and hmac.compare_digest(f['setup_hash'],hashlib.sha256(setup_code.encode()).hexdigest()),'claim_denied',403)
        require(not self.db.execute("SELECT 1 FROM registered_nodes WHERE factory_id=? AND registration<>'PAIRING'",(factory,)).fetchone(),'already_claimed',409)
        if f['product_type']=='SUB_BOX':
            require(parent is None)
            require(not self.db.execute('SELECT 1 FROM node_assignments WHERE room_id=? AND primary_subbox=1 AND active=1',(room,)).fetchone(),'room_has_primary',409)
        else:
            p = self.get_node(user,parent)
            require(p['product_type']=='SUB_BOX' and p['room_id']==room and p['registration']=='REGISTERED','invalid_parent')
            require(self.db.execute('SELECT count(*) FROM node_assignments WHERE parent_id=? AND active=1',(parent,)).fetchone()[0]<4,'peer_capacity',409)
        claim = dict(claim_id=uid('CLAIM-'),factory_id=factory,room_id=room,parent_id=parent,
                     nonce=secrets.token_hex(32),expires=int(self.clock()+120))
        try:
            with self.transaction():
                self.db.execute("UPDATE pairing_claims SET status='EXPIRED' WHERE status='PAIRING' AND expires<=?",(self.clock(),))
                existing=self.db.execute('SELECT node_id FROM registered_nodes WHERE factory_id=?',(factory,)).fetchone()
                if existing:
                    planned=existing[0]
                else:
                    planned=self.db.execute("INSERT INTO registered_nodes(factory_id,home_id,registration) VALUES(?,?,'PAIRING')",(factory,room_row['home_id'])).lastrowid
                claim['node_id']=planned
                key=hmac.digest(self.cipher.decrypt(f['secret']),b'HC-OPERATING-V1\0'+bytes.fromhex(claim['nonce']),'sha256')
                self.db.execute('INSERT INTO node_credentials VALUES(?,?,0) ON CONFLICT(node_id) DO UPDATE SET key_cipher=excluded.key_cipher,revoked=0',(planned,self.cipher.encrypt(key)))
                self.db.execute('INSERT INTO pairing_claims(claim_id,node_id,factory_id,user_id,room_id,parent_id,nonce,expires) VALUES(?,?,?,?,?,?,?,?)',
                                (claim['claim_id'],planned,factory,user,room,parent,claim['nonce'],claim['expires']))
                self.audit(user,room_row['home_id'],'claim_started',factory)
        except sqlite3.IntegrityError as e:
            raise CoreError('claim_pending') from e
        return claim

    def assign(self,user,node,room,parent=None):
        n=self.get_node(user,node)
        self.authorize(user,n['home_id'],('Owner',))
        destination=self.one('SELECT * FROM rooms WHERE room_id=?',(room,))
        require(destination['home_id']==n['home_id'],'cross_home_transfer_requires_release',403)
        require(n['registration']=='REGISTERED','assignment_pending',409)
        if n['product_type']=='ACTION_BOX':
            p=self.get_node(user,parent)
            require(p['product_type']=='SUB_BOX' and p['registration']=='REGISTERED' and p['room_id']==room,'invalid_parent')
            require(self.db.execute('SELECT count(*) FROM node_assignments WHERE parent_id=? AND active=1',(parent,)).fetchone()[0]<4,'peer_capacity',409)
        else:
            require(parent is None)
            require(not self.db.execute('SELECT 1 FROM node_assignments WHERE parent_id=? AND active=1',(node,)).fetchone(),'children_attached',409)
            require(not self.db.execute('SELECT 1 FROM node_assignments WHERE room_id=? AND primary_subbox=1 AND active=1 AND node_id<>?',(room,node)).fetchone(),'room_has_primary',409)
        claim=dict(claim_id=uid('CLAIM-'),node_id=node,factory_id=n['factory_id'],room_id=room,parent_id=parent,nonce=secrets.token_hex(32),expires=int(self.clock()+120))
        with self.transaction():
            self.db.execute("UPDATE pairing_claims SET status='EXPIRED' WHERE status='PAIRING' AND expires<=?",(self.clock(),))
            self.db.execute('INSERT INTO pairing_claims(claim_id,node_id,factory_id,user_id,room_id,parent_id,nonce,expires) VALUES(?,?,?,?,?,?,?,?)',
                            (claim['claim_id'],node,n['factory_id'],user,room,parent,claim['nonce'],claim['expires']))
            self.db.execute("UPDATE registered_nodes SET registration='TRANSFER_PENDING' WHERE node_id=?",(node,))
            self.db.execute("UPDATE commands SET status='FAILED',reason='assignment_pending' WHERE node_id=? AND status IN ('RECEIVED','ACCEPTED')",(node,))
            self.audit(user,n['home_id'],'assignment_pending',node)
        return claim

    def confirm_claim(self, claim_id, proof, *, stored, peer_confirmed, channels):
        c = self.one('SELECT * FROM pairing_claims WHERE claim_id=?',(claim_id,))
        require(c['status']=='PAIRING' and c['expires']>self.clock(),'claim_expired',409)
        f = self.one('SELECT * FROM factory_devices WHERE factory_id=?',(c['factory_id'],))
        require(not f['revoked'],'revoked',403)
        claim = {k:c[k] for k in ('claim_id','node_id','factory_id','room_id','parent_id','nonce','expires')}
        claim['expires']=int(claim['expires'])
        secret = self.cipher.decrypt(f['secret'])
        require(isinstance(proof,str) and hmac.compare_digest(hmac.digest(secret,canonical(dict(claim=claim,stored=stored,peer_confirmed=peer_confirmed,channels=channels)),'sha256').hex(),proof),'auth_failed',403)
        require(stored is True and peer_confirmed is True,'configuration_unconfirmed',409)
        require(channels == (3 if f['product_type']=='ACTION_BOX' else 0),'capability_mismatch')
        room = self.one('SELECT * FROM rooms WHERE room_id=?',(c['room_id'],))
        self.authorize(c['user_id'],room['home_id'],('Owner','Installer'))
        key = hmac.digest(secret,b'HC-OPERATING-V1\0'+bytes.fromhex(c['nonce']),'sha256')
        try:
            with self.transaction():
                if c['parent_id'] is not None:
                    p = self.get_node(c['user_id'],c['parent_id'])
                    require(p['registration']=='REGISTERED' and p['room_id']==c['room_id'],'invalid_parent')
                    require(self.db.execute('SELECT count(*) FROM node_assignments WHERE parent_id=? AND active=1',(c['parent_id'],)).fetchone()[0]<4,'peer_capacity',409)
                node=c['node_id']
                prior=self.one('SELECT registration FROM registered_nodes WHERE node_id=?',(node,))['registration']
                require(prior in ('PAIRING','TRANSFER_PENDING'),'claim_closed',409)
                self.db.execute("UPDATE registered_nodes SET home_id=?,registration='REGISTERED',boot_id=NULL,last_seen=NULL,connectivity='OFFLINE' WHERE node_id=?",(room['home_id'],node))
                self.db.execute('UPDATE node_credentials SET key_cipher=?,revoked=0 WHERE node_id=?',(self.cipher.encrypt(key),node))
                self.db.execute('UPDATE node_assignments SET active=0 WHERE node_id=?',(node,))
                if prior=='TRANSFER_PENDING':self.db.execute('UPDATE registered_nodes SET config_rev=config_rev+1 WHERE node_id=?',(node,))
                self.db.execute('INSERT INTO node_assignments(node_id,room_id,parent_id,primary_subbox) VALUES(?,?,?,?)',(node,c['room_id'],c['parent_id'],int(c['parent_id'] is None)))
                for number in range(1,channels+1):
                    channel=f"{c['factory_id']}:CH{number}"
                    self.db.execute('INSERT OR IGNORE INTO channels(channel_id,node_id,number) VALUES(?,?,?)',(channel,node,number))
                    self.db.execute('INSERT OR IGNORE INTO channel_states(channel_id) VALUES(?)',(channel,))
                self.db.execute("UPDATE pairing_claims SET status='REGISTERED' WHERE claim_id=?",(claim_id,))
                self.record_config(node)
                self.event(room['home_id'],'registered',{'node_id':node})
        except sqlite3.IntegrityError as e:
            raise CoreError('assignment_conflict') from e
        return self.get_node(c['user_id'],node)

    def node_key(self, node):
        row=self.one('SELECT c.* FROM node_credentials c JOIN registered_nodes n USING(node_id) WHERE c.node_id=? AND c.revoked=0 AND n.registration=?',(node,'REGISTERED'))
        return self.cipher.decrypt(row['key_cipher'])

    def get_node(self, user, node):
        row = self.one('SELECT n.*,f.product_type,f.model,a.room_id,a.parent_id FROM registered_nodes n JOIN factory_devices f USING(factory_id) LEFT JOIN node_assignments a ON a.node_id=n.node_id AND a.active=1 WHERE n.node_id=?',(node,))
        self.authorize(user,row['home_id'])
        return row

    def nodes(self, user, home):
        self.authorize(user,home)
        return [self.get_node(user,r['node_id']) for r in self.rows("SELECT node_id FROM registered_nodes WHERE home_id=? AND registration<>'PAIRING'",(home,))]

    def channels(self, user, node):
        self.get_node(user,node)
        return self.rows('SELECT c.*,s.*,b.device_id FROM channels c JOIN channel_states s USING(channel_id) LEFT JOIN device_bindings b ON b.channel_id=c.channel_id AND b.active=1 WHERE c.node_id=? ORDER BY c.number',(node,))

    def session_challenge(self, node, boot):
        self.node_key(node)
        require(type(boot)==int and 0<boot<2**64)
        current=self.one('SELECT boot_id FROM registered_nodes WHERE node_id=?',(node,))['boot_id']
        require(current==str(boot) or not self.db.execute('SELECT 1 FROM admitted_boots WHERE node_id=? AND boot_id=?',(node,str(boot))).fetchone(),'boot_replay',409)
        challenge=dict(node_id=node,boot_id=boot,nonce=secrets.token_hex(32),expires=int(self.clock()+30))
        self.db.execute('INSERT INTO session_challenges VALUES(?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET nonce=excluded.nonce,boot_id=excluded.boot_id,expires=excluded.expires',(node,challenge['nonce'],str(boot),challenge['expires']))
        return challenge

    def admit_session(self, node, nonce, proof):
        c=self.one('SELECT * FROM session_challenges WHERE node_id=?',(node,))
        challenge=dict(node_id=node,nonce=c['nonce'],boot_id=int(c['boot_id']),expires=int(c['expires']))
        require(c['expires']>self.clock() and nonce==c['nonce'],'challenge_expired',403)
        require(isinstance(proof,str) and hmac.compare_digest(hmac.digest(self.node_key(node),canonical(challenge),'sha256').hex(),proof),'auth_failed',403)
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO admitted_boots VALUES(?,?)',(node,c['boot_id']))
            self.db.execute("UPDATE registered_nodes SET boot_id=?,connectivity='ONLINE',last_seen=? WHERE node_id=?",(c['boot_id'],self.clock(),node))
            self.db.execute('DELETE FROM session_challenges WHERE node_id=?',(node,))
            self.db.execute("UPDATE commands SET status='FAILED',reason='node_reboot' WHERE node_id=? AND boot_id<>? AND status IN ('RECEIVED','ACCEPTED')",(node,c['boot_id']))

    def record_config(self,node):
        n=self.one('SELECT * FROM registered_nodes WHERE node_id=?',(node,))
        bindings=self.rows('SELECT c.channel_id,c.number,b.device_id FROM channels c LEFT JOIN device_bindings b ON b.channel_id=c.channel_id AND b.active=1 WHERE c.node_id=?',(node,))
        self.db.execute('INSERT INTO config_revisions VALUES(?,?,?,?)',(node,n['config_rev'],canonical({'channels':bindings}).decode(),self.clock()))

    def bump(self,node):
        self.db.execute('UPDATE registered_nodes SET config_rev=config_rev+1 WHERE node_id=?',(node,))
        self.db.execute("UPDATE commands SET status='FAILED',reason='configuration_changed' WHERE node_id=? AND status IN ('RECEIVED','ACCEPTED')",(node,))
        self.record_config(node)

    def _bind(self,user,device,channel):
        d=self.one('SELECT * FROM devices WHERE device_id=?',(device,))
        self.authorize(user,d['home_id'],('Owner','Installer'))
        target=self.one('SELECT c.*,n.home_id,n.registration FROM channels c JOIN registered_nodes n USING(node_id) WHERE c.channel_id=?',(channel,))
        require(target['home_id']==d['home_id'] and target['registration']=='REGISTERED','invalid_binding',403)
        old=self.db.execute('SELECT c.node_id FROM device_bindings b JOIN channels c USING(channel_id) WHERE b.device_id=? AND b.active=1',(device,)).fetchone()
        self.db.execute('UPDATE device_bindings SET active=0 WHERE device_id=?',(device,))
        self.db.execute('INSERT INTO device_bindings(device_id,channel_id,created) VALUES(?,?,?)',(device,channel,self.clock()))
        for node in {target['node_id']} | ({old[0]} if old else set()):
            self.bump(node)
        self.event(d['home_id'],'binding_changed',{'device_id':device,'channel_id':channel})
        self.audit(user,d['home_id'],'bind',device)

    def bind(self,user,device,channel):
        try:
            with self.transaction():
                self._bind(user,device,channel)
        except sqlite3.IntegrityError as e:
            raise CoreError('channel_bound') from e

    def create_device(self,user,home,label,kind,channel):
        self.authorize(user,home,('Owner','Installer'))
        require(kind in ('light','fan','outlet','other'))
        device=uid('DEV-')
        try:
            with self.transaction():
                self.db.execute('INSERT INTO devices VALUES(?,?,?,?)',(device,home,name(label),kind))
                self._bind(user,device,channel)
        except sqlite3.IntegrityError as e:
            raise CoreError('channel_bound') from e
        return self.one('SELECT * FROM devices WHERE device_id=?',(device,))

    def rename_device(self,user,device,label,kind):
        d=self.one('SELECT * FROM devices WHERE device_id=?',(device,))
        self.authorize(user,d['home_id'],('Owner','Installer'))
        require(kind in ('light','fan','outlet','other'))
        with self.transaction():
            self.db.execute('UPDATE devices SET name=?,kind=? WHERE device_id=?',(name(label),kind,device))
            self.event(d['home_id'],'device_changed',{'device_id':device})

    def unbind(self,user,channel):
        c=self.one('SELECT c.*,n.home_id FROM channels c JOIN registered_nodes n USING(node_id) WHERE channel_id=?',(channel,))
        self.authorize(user,c['home_id'],('Owner','Installer'))
        with self.transaction():
            self.db.execute('UPDATE device_bindings SET active=0 WHERE channel_id=?',(channel,))
            self.bump(c['node_id'])
            self.event(c['home_id'],'binding_removed',{'channel_id':channel})

    def devices(self,user,home):
        self.authorize(user,home)
        return self.rows('SELECT d.*,b.channel_id FROM devices d LEFT JOIN device_bindings b ON d.device_id=b.device_id AND b.active=1 WHERE d.home_id=?',(home,))

    def report_state(self,node,payload):
        self.node_key(node)
        n=self.one('SELECT * FROM registered_nodes WHERE node_id=?',(node,))
        require(str(payload.get('boot_id'))==n['boot_id'],'session_required',403)
        require(type(payload.get('state_seq'))==int and 0<payload['state_seq']<2**32)
        require(type(payload.get('config_rev'))==int and payload['config_rev']==n['config_rev'],'config_mismatch',409)
        require(payload.get('node_id')==node)
        reports=payload.get('channels')
        require(isinstance(reports,list) and len(reports)==3)
        require(all(isinstance(c,dict) for c in reports))
        require({c.get('number') for c in reports}=={1,2,3})
        for c in reports:
            require(type(c.get('number'))==int and type(c.get('relay_state'))==bool and type(c.get('ct_valid'))==bool)
            require(type(c.get('fault_flags'))==int and 0<=c['fault_flags']<=65535)
            current=c.get('current_rms_a')
            require((c['ct_valid'] and type(current) in (int,float) and math.isfinite(current) and 0<=current<=1000) or (not c['ct_valid'] and current is None))
        last=self.db.execute('SELECT max(state_seq) FROM channel_states s JOIN channels c USING(channel_id) WHERE c.node_id=? AND s.boot_id=?',(node,n['boot_id'])).fetchone()[0]
        if last is not None and payload['state_seq']<=last:
            return False
        with self.transaction():
            for c in reports:
                channel=f"{n['factory_id']}:CH{c['number']}"
                self.db.execute('UPDATE channel_states SET relay_state=?,current_rms_a=?,ct_valid=?,fault_flags=?,boot_id=?,state_seq=?,config_rev=?,reported_at=? WHERE channel_id=?',
                                (int(c['relay_state']),c['current_rms_a'],int(c['ct_valid']),c['fault_flags'],n['boot_id'],payload['state_seq'],payload['config_rev'],self.clock(),channel))
            self.db.execute("UPDATE registered_nodes SET last_seen=?,connectivity='ONLINE',reported_rev=? WHERE node_id=?",(self.clock(),payload['config_rev'],node))
            self.event(n['home_id'],'state_report',payload)
        return True

    def command(self,user,device,desired,idempotency_key,ttl=5):
        d=self.one('SELECT * FROM devices WHERE device_id=?',(device,))
        self.authorize(user,d['home_id'],('Owner','Member'))
        require(type(desired)==bool and isinstance(idempotency_key,str) and 1<=len(idempotency_key)<=100)
        require(type(ttl) in (int,float) and 0<ttl<=30)
        old=self.db.execute('SELECT * FROM commands WHERE user_id=? AND idempotency_key=?',(user,idempotency_key)).fetchone()
        if old:
            require(old['device_id']==device and old['desired']==int(desired),'idempotency_conflict',409)
            return dict(old)
        route=self.one('SELECT c.*,n.boot_id,n.config_rev,n.reported_rev,n.registration,n.last_seen,a.parent_id,p.last_seen AS parent_seen FROM device_bindings b JOIN channels c USING(channel_id) JOIN registered_nodes n USING(node_id) JOIN node_assignments a ON a.node_id=n.node_id AND a.active=1 JOIN registered_nodes p ON p.node_id=a.parent_id AND p.registration=\'REGISTERED\' WHERE b.device_id=? AND b.active=1',(device,))
        now=self.clock()
        require(route['registration']=='REGISTERED' and all(t is not None and 0<=now-t<15 for t in (route['last_seen'],route['parent_seen'])),'offline',409)
        require(route['config_rev']==route['reported_rev'],'config_pending',409)
        require(not self.db.execute("SELECT 1 FROM ota_targets WHERE node_id IN (?,?) AND status IN ('TRANSFERRING','VERIFYING','REBOOTING','HEALTH_CHECK')",(route['node_id'],route['parent_id'])).fetchone(),'ota_in_progress',409)
        require(self.db.execute("SELECT count(*) FROM commands WHERE node_id=? AND status IN ('RECEIVED','ACCEPTED')",(route['node_id'],)).fetchone()[0]<16,'queue_full',429)
        command=uid('CMD-')
        with self.transaction():
            self.db.execute('UPDATE channels SET command_generation=command_generation+1 WHERE channel_id=?',(route['channel_id'],))
            generation=self.one('SELECT command_generation FROM channels WHERE channel_id=?',(route['channel_id'],))['command_generation']
            self.db.execute('INSERT INTO commands(command_id,home_id,user_id,idempotency_key,device_id,channel_id,node_id,parent_id,boot_id,config_rev,desired,generation,status,created,expires,next_try) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (command,d['home_id'],user,idempotency_key,device,route['channel_id'],route['node_id'],route['parent_id'],route['boot_id'],route['config_rev'],int(desired),generation,'ACCEPTED',now,now+ttl,now))
            self.audit(user,d['home_id'],'command',command)
            self.event(d['home_id'],'command',{'command_id':command,'status':'ACCEPTED'})
        return self.get_command(user,command)

    def get_command(self,user,command):
        c=self.one('SELECT * FROM commands WHERE command_id=?',(command,))
        self.authorize(user,c['home_id'])
        return c

    def ack(self,node,command,status,revision,reported):
        self.node_key(node)
        c=self.one('SELECT * FROM commands WHERE command_id=?',(command,))
        n=self.one('SELECT * FROM registered_nodes WHERE node_id=?',(node,))
        require(c['node_id']==node and c['config_rev']==revision==n['config_rev'] and c['boot_id']==n['boot_id'],'ack_mismatch',409)
        require(status in ('RECEIVED','ACCEPTED','APPLIED','FAILED'))
        if c['status']==status:
            return
        require(c['status'] in ('RECEIVED','ACCEPTED') and c['expires']>self.clock(),'command_closed',409)
        if status=='APPLIED':
            require(type(reported)==bool and int(reported)==c['desired'],'state_mismatch',409)
        with self.transaction():
            self.db.execute('UPDATE commands SET status=? WHERE command_id=?',(status,command))
            self.event(c['home_id'],'command',{'command_id':command,'status':status})

    def due_commands(self):
        now=self.clock()
        with self.transaction():
            expired=self.rows("SELECT * FROM commands WHERE status IN ('RECEIVED','ACCEPTED') AND (expires<=? OR (attempts>=3 AND next_try<=?))",(now,now))
            for c in expired:
                self.db.execute("UPDATE commands SET status='TIMEOUT',reason='ack_timeout' WHERE command_id=?",(c['command_id'],))
                self.event(c['home_id'],'command',{'command_id':c['command_id'],'status':'TIMEOUT'})
            due=self.rows("SELECT * FROM commands WHERE status IN ('RECEIVED','ACCEPTED') AND next_try<=? AND expires>? AND attempts<3 ORDER BY created LIMIT 64",(now,now))
            for c in due:
                self.db.execute('UPDATE commands SET attempts=attempts+1,next_try=? WHERE command_id=?',(now+.75,c['command_id']))
        return due

    def unpair(self,user,node):
        n=self.get_node(user,node)
        self.authorize(user,n['home_id'],('Owner',))
        require(not self.db.execute('SELECT 1 FROM node_assignments WHERE parent_id=? AND active=1',(node,)).fetchone(),'children_attached',409)
        with self.transaction():
            self.db.execute("UPDATE registered_nodes SET registration='REVOKED',connectivity='OFFLINE' WHERE node_id=?",(node,))
            self.db.execute('UPDATE node_credentials SET revoked=1 WHERE node_id=?',(node,))
            self.db.execute('UPDATE factory_devices SET revoked=1 WHERE factory_id=?',(n['factory_id'],))
            self.db.execute('UPDATE node_assignments SET active=0 WHERE node_id=?',(node,))
            self.db.execute('UPDATE device_bindings SET active=0 WHERE channel_id IN (SELECT channel_id FROM channels WHERE node_id=?)',(node,))
            self.db.execute("UPDATE commands SET status='FAILED',reason='revoked' WHERE node_id=? AND status IN ('RECEIVED','ACCEPTED')",(node,))
            self.event(n['home_id'],'node_revoked',{'node_id':node})
            self.audit(user,n['home_id'],'unpair',node)

    def snapshot(self,user,home):
        self.authorize(user,home)
        nodes=self.nodes(user,home)
        channels=[]
        for n in nodes:
            parent=next((p for p in nodes if p['node_id']==n['parent_id']),None)
            fresh=all(x is not None and x['last_seen'] is not None and 0<=self.clock()-x['last_seen']<15 and x['registration']=='REGISTERED' for x in ([n,parent] if n['parent_id'] else [n]))
            n['availability']='ONLINE' if fresh else 'OFFLINE'
            for c in self.channels(user,n['node_id']):
                c['availability']='ONLINE' if fresh and c['reported_at'] is not None and 0<=self.clock()-c['reported_at']<15 and c['config_rev']==n['config_rev'] else 'STALE'
                channels.append(c)
        return dict(home_id=home,rooms=self.rooms(user,home),nodes=nodes,channels=channels,devices=self.devices(user,home),
                    cursor=self.db.execute('SELECT coalesce(max(event_id),0) FROM state_events WHERE home_id=?',(home,)).fetchone()[0])

    def events(self,user,home,after=0):
        self.authorize(user,home)
        return [dict(r,data=json.loads(r['data'])) for r in self.rows('SELECT * FROM state_events WHERE home_id=? AND event_id>? ORDER BY event_id LIMIT 256',(home,after))]
