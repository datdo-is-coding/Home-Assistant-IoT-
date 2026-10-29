"""Home-owner maintenance using authenticated Core frames and device receipts."""
import hashlib
import json
import re
import secrets
import struct

from .registry import CoreError, require, canonical, uid as new_id
from .protocol import MessageType

KINDS={'reboot':1,'factory_reset':2,'remove_from_home':3}
PACKET=struct.Struct('<BQ')
RECEIPT=struct.Struct('<QBB')


class Maintenance:
    def __init__(self,registry):
        self.r=registry
        registry.db.executescript('''
          CREATE TABLE IF NOT EXISTS core_maintenance_caps(
            node_id INTEGER PRIMARY KEY REFERENCES registered_nodes,boot_id TEXT NOT NULL,seen REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS core_maintenance(
            operation_id TEXT PRIMARY KEY,home_id TEXT NOT NULL,user_id TEXT NOT NULL,
            node_id INTEGER NOT NULL,device_uid TEXT NOT NULL,kind TEXT NOT NULL,
            request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,
            wire_id INTEGER NOT NULL,boot_id TEXT NOT NULL,created REAL NOT NULL,
            expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,
            error_code TEXT,UNIQUE(user_id,request_key));
          CREATE UNIQUE INDEX IF NOT EXISTS core_one_maintenance ON core_maintenance(node_id)
            WHERE state IN ('accepted','running');
        ''')

    def supported(self,node):
        return bool(self.r.db.execute("SELECT 1 FROM core_maintenance_caps c JOIN registered_nodes n USING(node_id) WHERE c.node_id=? AND c.boot_id=n.boot_id AND c.seen>? AND n.registration='REGISTERED'",(node,self.r.clock()-15)).fetchone())

    def expire(self):
        self.r.db.execute("UPDATE core_maintenance SET state='timed_out',error_code='maintenance_ack_unknown' WHERE state IN ('accepted','running') AND expires<=?",(self.r.clock(),))

    def view(self,row):
        return {'operation_id':row['operation_id'],'device_uid':row['device_uid'],'kind':row['kind'],
                'state':row['state'],'expires_at':row['expires'],'error_code':row['error_code'],
                'error_message':{'maintenance_ack_unknown':'Chưa xác nhận được kết quả trên bo. Kiểm tra thiết bị trước khi thử lại.',
                                 'maintenance_failed':'Bo chưa thực hiện được thao tác.'}.get(row['error_code'])}

    def get(self,user,home,identifier):
        self.expire();row=self.r.one('SELECT * FROM core_maintenance WHERE operation_id=?',(identifier,))
        require(row['home_id']==home,'forbidden',403);self.r.authorize(user,home,('Owner',))
        return self.view(row)

    def start(self,user,home,identifier,body):
        self.r.authorize(user,home,('Owner',));self.expire()
        require(isinstance(body,dict) and set(body)<={'kind','confirmation','idempotency_key'},'invalid_input')
        kind=body.get('kind');require(kind in KINDS,'maintenance_kind_unsupported',409)
        require(kind=='reboot' or body.get('confirmation') is True,'confirmation_required',409)
        require(isinstance(identifier,str) and re.fullmatch(r'(AB|SB)[0-9A-F]{12}',identifier),'invalid_device')
        node=self.r.one('SELECT * FROM registered_nodes WHERE factory_id=? AND home_id=?',('HC-'+identifier[2:],home))
        key=body.get('idempotency_key');require(isinstance(key,str) and 1<=len(key)<=200,'idempotency_required')
        fingerprint=hashlib.sha256(canonical({'device':identifier,**body})).hexdigest()
        old=self.r.db.execute('SELECT * FROM core_maintenance WHERE user_id=? AND request_key=?',(user,key)).fetchone()
        if old:
            require(old['fingerprint']==fingerprint,'idempotency_conflict',409);return self.view(old)
        require(node['registration']=='REGISTERED','registration_required',409)
        require(self.supported(node['node_id']),'maintenance_firmware_required',409)
        require(node['last_seen'] is not None and 0<=self.r.clock()-node['last_seen']<15,'offline',409)
        require(not self.r.db.execute("SELECT 1 FROM core_maintenance WHERE node_id=? AND state IN ('accepted','running')",(node['node_id'],)).fetchone(),'maintenance_busy',409)
        require(not self.r.db.execute("SELECT 1 FROM ota_targets WHERE node_id=? AND status IN ('QUEUED','TRANSFERRING','VERIFYING','REBOOTING','HEALTH_CHECK')",(node['node_id'],)).fetchone(),'ota_in_progress',409)
        if kind!='reboot':require(not self.r.db.execute('SELECT 1 FROM node_assignments WHERE parent_id=? AND active=1',(node['node_id'],)).fetchone(),'children_attached',409)
        with self.r.transaction():
            self.r.db.execute("UPDATE commands SET status='FAILED',reason='maintenance' WHERE node_id=? AND status IN ('RECEIVED','ACCEPTED')",(node['node_id'],))
            identifier_op=new_id('HCM-')
            self.r.db.execute('INSERT INTO core_maintenance(operation_id,home_id,user_id,node_id,device_uid,kind,request_key,fingerprint,state,wire_id,boot_id,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identifier_op,home,user,node['node_id'],identifier,kind,key,fingerprint,'accepted',secrets.randbits(63) or 1,node['boot_id'],self.r.clock(),self.r.clock()+(15 if kind=='reboot' else 8)))
            self.r.audit(user,home,'maintenance_requested',identifier_op)
        return self.get(user,home,identifier_op)

    def receive(self,frame):
        if frame.type==MessageType.CAPABILITY_REPORT:
            require(len(frame.payload) in (2,18) and frame.payload[:2]==b'M\x01','invalid_capability')
            if len(frame.payload)==18:
                version=frame.payload[2:].split(b'\0',1)[0]
                require(re.fullmatch(rb'[A-Za-z0-9_.-]{1,15}',version) is not None and version.ljust(16,b'\0')==frame.payload[2:],'invalid_capability')
                self.r.db.execute('UPDATE registered_nodes SET firmware=? WHERE node_id=? AND (firmware IS NULL OR firmware<>?)',(version.decode('ascii'),frame.source,version.decode('ascii')))
            self.r.db.execute('INSERT INTO core_maintenance_caps VALUES(?,?,?) ON CONFLICT(node_id) DO UPDATE SET boot_id=excluded.boot_id,seen=excluded.seen',(frame.source,str(frame.boot_id),self.r.clock()))
            for op in self.r.rows("SELECT * FROM core_maintenance WHERE node_id=? AND kind='reboot' AND state='running' AND boot_id<>? AND expires>?",(frame.source,str(frame.boot_id),self.r.clock())):
                self.r.db.execute("UPDATE core_maintenance SET state='succeeded' WHERE operation_id=?",(op['operation_id'],))
                self.r.audit(op['user_id'],op['home_id'],'maintenance_completed',op['operation_id'])
            return
        require(len(frame.payload)==RECEIPT.size,'invalid_maintenance_receipt')
        wire,state,error=RECEIPT.unpack(frame.payload);require(state in (1,2,3),'invalid_maintenance_receipt')
        row=self.r.one('SELECT * FROM core_maintenance WHERE node_id=? AND wire_id=?',(frame.source,wire))
        if row['state'] not in ('accepted','running'):return
        require(row['boot_id']==str(frame.boot_id),'maintenance_boot_changed',409)
        require(row['expires']>self.r.clock(),'expired',409)
        if state==1:
            self.r.db.execute("UPDATE core_maintenance SET state='running' WHERE operation_id=?",(row['operation_id'],));return
        if state==3 or error:
            self.r.db.execute("UPDATE core_maintenance SET state='failed',error_code='maintenance_failed' WHERE operation_id=?",(row['operation_id'],));return
        if row['kind']=='reboot':
            self.r.db.execute("UPDATE core_maintenance SET state='running',attempts=3 WHERE operation_id=?",(row['operation_id'],));return
        with self.r.transaction():
            if row['kind']!='reboot':
                self.r._revoke_node(row['user_id'],self.r.one('SELECT * FROM registered_nodes WHERE node_id=?',(frame.source,)))
                # The physical receipt proves enrollment was erased, so require a fresh setup proof to claim again.
                self.r.db.execute("UPDATE registered_nodes SET registration='PAIRING',boot_id=NULL,last_seen=NULL WHERE node_id=?",(frame.source,))
                self.r.db.execute('UPDATE factory_devices SET revoked=0 WHERE factory_id=(SELECT factory_id FROM registered_nodes WHERE node_id=?)',(frame.source,))
                if self.r.db.execute("SELECT 1 FROM sqlite_master WHERE name='ir_remotes'").fetchone():
                    self.r.db.execute('DELETE FROM ir_remotes WHERE node_id=?',(frame.source,))
                for table in ('core_node_labels','ir_receivers'):
                    if self.r.db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
                        self.r.db.execute('DELETE FROM '+table+' WHERE node_id=?',(frame.source,))
            self.r.db.execute("UPDATE core_maintenance SET state='succeeded' WHERE operation_id=?",(row['operation_id'],))
            self.r.audit(row['user_id'],row['home_id'],'maintenance_completed',row['operation_id'])

    def outgoing(self,bridge):
        self.expire();result=[]
        for row in self.r.rows("SELECT * FROM core_maintenance WHERE state IN ('accepted','running') AND attempts<3 AND next_try<=?",(self.r.clock(),)):
            try:self.r.authorize(row['user_id'],row['home_id'],('Owner',))
            except CoreError:
                self.r.db.execute("UPDATE core_maintenance SET state='failed',error_code='forbidden' WHERE operation_id=?",(row['operation_id'],));continue
            node=self.r.one('SELECT * FROM registered_nodes WHERE node_id=?',(row['node_id'],))
            if node['boot_id']!=row['boot_id']:
                if row['kind']=='reboot' and row['state']=='running':continue
                self.r.db.execute("UPDATE core_maintenance SET state='timed_out',error_code='maintenance_ack_unknown' WHERE operation_id=?",(row['operation_id'],));continue
            if row['node_id'] not in bridge.windows or row['node_id'] not in bridge.uptimes:continue
            uptime,observed=bridge.uptimes[row['node_id']]
            remaining=min(3000,max(0,int((row['expires']-self.r.clock())*1000)))
            if not remaining:continue
            deadline=uptime+int((self.r.clock()-observed)*1000)+remaining
            result.append((bridge.route(row['node_id']),bridge.frame(row['node_id'],MessageType.MAINTENANCE,PACKET.pack(KINDS[row['kind']],deadline),message_id=row['wire_id'])))
            self.r.db.execute('UPDATE core_maintenance SET attempts=attempts+1,next_try=? WHERE operation_id=?',(self.r.clock()+.6,row['operation_id']))
        return result
