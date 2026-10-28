"""SubBox resolves KWS targets; authenticated Core commands remain authoritative."""
import asyncio
import hashlib
import json
import logging
import re
import secrets
import struct
from .registry import CoreError, canonical, require

ROOMS = ('BEDROOM', 'LIVING_ROOM', 'KITCHEN')
ROOM_NAMES = ('Phòng ngủ', 'Phòng khách', 'Bếp')
ROLES = ('LIGHT', 'FAN')
SNAPSHOT = struct.Struct('<BIBBB')
TARGET = struct.Struct('<BBBIII')
INTENT = struct.Struct('<BQIIII4BQ')
ERROR = struct.Struct('<BQIBQ')
log = logging.getLogger('core_kws')


class CoreKws:
    def __init__(self, registry):
        self.r = registry
        registry.db.execute('CREATE TABLE IF NOT EXISTS core_kws_config(home_id TEXT PRIMARY KEY REFERENCES homes,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
        registry.db.execute('CREATE TABLE IF NOT EXISTS core_kws_sync(node_id INTEGER PRIMARY KEY REFERENCES registered_nodes,digest BLOB NOT NULL,boot_id TEXT NOT NULL)')

    def scope(self, node):
        return self.r.one("SELECT n.*,a.room_id,a.parent_id,a.primary_subbox,f.product_type FROM registered_nodes n "
                          "JOIN node_assignments a USING(node_id) JOIN factory_devices f USING(factory_id) "
                          "WHERE n.node_id=? AND n.registration='REGISTERED' AND a.active=1", (node,))

    def identity(self, identifier, home, product):
        prefix = 'SB' if product == 'SUB_BOX' else 'AB'
        require(isinstance(identifier,str) and re.fullmatch(prefix+'[0-9A-F]{12}',identifier), 'invalid_node')
        row=self.r.one('SELECT node_id FROM registered_nodes WHERE factory_id=?',('HC-'+identifier[2:],))
        node=self.scope(row['node_id'])
        require(node['home_id']==home and node['product_type']==product,'forbidden',403)
        return node

    def stored(self, home):
        row=self.r.db.execute('SELECT * FROM core_kws_config WHERE home_id=?',(home,)).fetchone()
        return json.loads(row['payload']) if row else dict(revision=0,sources=[],bindings=[])

    def config(self, user, home):
        self.r.authorize(user,home)
        result=self.stored(home);result['sync']={};result['profile']='core-v1'
        for source in result['sources']:
            node=self.identity(source['node_id'],home,'SUB_BOX')
            packet=self.snapshot(node['node_id'])
            ack=self.r.db.execute('SELECT * FROM core_kws_sync WHERE node_id=?',(node['node_id'],)).fetchone()
            online=node['last_seen'] is not None and 0<=self.r.clock()-node['last_seen']<15
            applied=ack and ack['boot_id']==node['boot_id'] and bytes(ack['digest'])==hashlib.sha256(packet).digest()[:16]
            result['sync'][source['node_id']]={'revision':result['revision'],'status':'applied' if applied and online else 'pending' if online else 'offline'}
        return result

    def configure(self, user, home, body):
        self.r.authorize(user,home,('Owner','Installer'))
        require(isinstance(body,dict) and 'revision' in body and set(body)<={'revision','sources','bindings'})
        old=self.stored(home)
        require(type(body['revision']) is int and body['revision']==old['revision'],'revision_conflict',409)
        # RTDB omits empty arrays; an omitted list is an explicit empty configuration.
        sources,bindings=body.get('sources',[]),body.get('bindings',[])
        require(isinstance(sources,list) and len(sources)<=8 and isinstance(bindings,list) and len(bindings)<=6)
        rooms={};seen=set();targets=set();validated=[]
        for source in sources:
            require(isinstance(source,dict) and set(source)=={'node_id','room'} and source['room'] in ROOMS,'invalid_room')
            node=self.identity(source['node_id'],home,'SUB_BOX')
            require(node['node_id'] not in rooms and source['room'] not in rooms.values(),'duplicate_room')
            rooms[node['node_id']]=source['room'];validated.append((node,source['room']))
        for binding in bindings:
            require(isinstance(binding,dict) and set(binding)=={'node_id','channel','room','device'})
            require(binding['room'] in ROOMS and binding['device'] in ROLES and type(binding['channel']) is int and binding['channel'] in (1,2,3),'invalid_binding')
            node=self.identity(binding['node_id'],home,'ACTION_BOX')
            require(rooms.get(node['parent_id'])==binding['room'],'room_belongs_to_subbox')
            key=(binding['room'],binding['device']);target=(node['node_id'],binding['channel'])
            require(key not in seen and target not in targets,'duplicate_binding');seen.add(key);targets.add(target)
            device=self.r.one('SELECT d.* FROM device_bindings b JOIN devices d USING(device_id) WHERE b.channel_id=? AND b.active=1',
                              (node['factory_id']+':CH'+str(binding['channel']),))
            require(device['kind']==binding['device'].lower(),'device_type_mismatch')
        new=dict(revision=old['revision']+1,sources=sources,bindings=bindings)
        require(new['revision']<2**32,'revision_exhausted')
        with self.r.transaction():
            for node,room in validated:
                self.r.db.execute('UPDATE rooms SET name=? WHERE room_id=?',(ROOM_NAMES[ROOMS.index(room)],node['room_id']))
                user_id='KWS-'+str(node['node_id'])
                self.r.db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',(user_id,'SubBox KWS',hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
                self.r.db.execute("INSERT OR IGNORE INTO home_members VALUES(?,?,'Member')",(home,user_id))
            self.r.db.execute('INSERT OR REPLACE INTO core_kws_config VALUES(?,?,?)',(home,new['revision'],canonical(new).decode()))
            self.r.audit(user,home,'kws_config',str(new['revision']))
        return self.config(user,home)

    def snapshot(self, parent):
        scope=self.scope(parent);require(scope['product_type']=='SUB_BOX','invalid_parent')
        cfg=self.stored(scope['home_id'])
        own=next((s for s in cfg['sources'] if s['node_id']=='SB'+scope['factory_id'][3:]),None)
        if own is None:return b''
        sources=[n['node_id'] for n in self.r.rows("SELECT n.node_id FROM registered_nodes n JOIN node_assignments a USING(node_id) WHERE a.parent_id=? AND a.active=1 AND n.registration='REGISTERED' ORDER BY n.node_id",(parent,))]
        require(len(sources)<=4,'peer_capacity')
        targets=[]
        for b in cfg['bindings']:
            try:
                n=self.identity(b['node_id'],scope['home_id'],'ACTION_BOX')
                device=self.r.one('SELECT d.kind FROM device_bindings b JOIN devices d USING(device_id) WHERE b.channel_id=? AND b.active=1',(n['factory_id']+':CH'+str(b['channel']),))
                source=next((s for s in cfg['sources'] if self.identity(s['node_id'],scope['home_id'],'SUB_BOX')['node_id']==n['parent_id']),None)
                if not source or source['room']!=b['room'] or device['kind']!=b['device'].lower():continue
                targets.append(TARGET.pack(ROOMS.index(b['room']),ROLES.index(b['device']),b['channel'],n['node_id'],n['config_rev'],n['parent_id']))
            except CoreError:continue
        packet=SNAPSHOT.pack(1,cfg['revision'],ROOMS.index(own['room']),len(sources),len(targets))+b''.join(struct.pack('<I',s) for s in sources)+b''.join(targets)
        require(len(packet)<=196,'config_too_large');return packet

    def receive(self, frame):
        parent=frame.source;scope=self.scope(parent)
        require(scope['product_type']=='SUB_BOX' and scope['primary_subbox']==1,'voice_identity_denied',403)
        require(frame.config_rev==scope['config_rev'],'config_mismatch')
        data=frame.payload
        if len(data)==17 and data[0]==2:
            packet=self.snapshot(parent)
            require(packet and data[1:]==hashlib.sha256(packet).digest()[:16],'config_mismatch')
            self.r.db.execute('INSERT OR REPLACE INTO core_kws_sync VALUES(?,?,?)',(parent,data[1:],str(frame.boot_id)));return
        require(len(data) in (INTENT.size,ERROR.size),'invalid_kws_event')
        if len(data)==INTENT.size:
            kind,request,source,target,target_rev,revision,room,role,channel,desired,expires=INTENT.unpack(data)
            require(kind==1 and room<len(ROOMS) and role<len(ROLES) and channel in (1,2,3) and desired in (0,1))
        else:
            kind,request,source,reason,expires=ERROR.unpack(data);require(kind==3 and 1<=reason<=4)
        child=self.scope(source)
        require(child['product_type']=='ACTION_BOX' and child['parent_id']==parent and child['home_id']==scope['home_id'],'voice_source_denied',403)
        now=self.r.clock()*1000;require(request>0 and now<expires<=now+5000,'expired')
        key=f'kws:{parent}:{frame.boot_id}:{request}'
        if self.r.db.execute('SELECT 1 FROM commands WHERE user_id=? AND idempotency_key=?',('KWS-'+str(parent),key)).fetchone():return
        result=dict(parent=parent,source=source,request_key=key,expires=self.r.clock()+15)
        if kind==3:result['reason']=('','no_command','incomplete_command','missing_binding','config_pending')[reason]
        else:
            cfg=self.stored(scope['home_id']);require(revision==cfg['revision'],'config_mismatch')
            node=self.scope(target);require(node['config_rev']==target_rev,'config_mismatch')
            expected=dict(node_id='AB'+node['factory_id'][3:],channel=channel,room=ROOMS[room],device=ROLES[role])
            require(expected in cfg['bindings'] and node['home_id']==scope['home_id'],'missing_binding')
            packet=self.snapshot(parent)
            require(packet and TARGET.pack(room,role,channel,target,target_rev,node['parent_id']) in
                    [packet[i:i+TARGET.size] for i in range(SNAPSHOT.size+4*packet[6],len(packet),TARGET.size)],'config_mismatch')
            device=self.r.one('SELECT d.* FROM device_bindings b JOIN devices d USING(device_id) WHERE b.channel_id=? AND b.active=1',(node['factory_id']+':CH'+str(channel),))
            require(device['kind']==ROLES[role].lower(),'config_mismatch')
            try:
                command=self.r.command('KWS-'+str(parent),device['device_id'],bool(desired),key,ttl=min(4,(expires-now)/1000))
                result.update(command_id=command['command_id'],name=device['name'],desired=bool(desired))
            except CoreError as error:result['reason']=error.code
        self.r.event(scope['home_id'],'core_kws_result',result)

    async def feedback(self, audio):
        cursor=self.r.db.execute('SELECT coalesce(max(event_id),0) FROM state_events').fetchone()[0]
        tasks=set()
        async def respond(event):
            try:
                if event['expires']<=self.r.clock():return
                command=None
                if event.get('command_id'):
                    while event['expires']>self.r.clock():
                        command=self.r.one('SELECT * FROM commands WHERE command_id=?',(event['command_id'],))
                        if command['status'] not in ('ACCEPTED','RECEIVED') or command['expires']<=self.r.clock():break
                        await asyncio.sleep(.05)
                if event['expires']<=self.r.clock():return
                node=self.scope(event['parent'])
                text=(f"Relay của {event['name']} đã {'bật' if event['desired'] else 'tắt'}." if command and command['status']=='APPLIED'
                      else 'Chưa xác nhận được lệnh điều khiển. Bạn hãy thử lại.')
                async with asyncio.timeout(event['expires']-self.r.clock()):
                    await audio.speak_proactive(text,'SB'+node['factory_id'][3:])
            except (CoreError,TimeoutError):pass
            except Exception:log.exception('Core KWS feedback failed')
        try:
            while True:
                for row in self.r.rows("SELECT * FROM state_events WHERE event_id>? AND kind='core_kws_result' ORDER BY event_id LIMIT 64",(cursor,)):
                    cursor=row['event_id']
                    if len(tasks)<8:
                        task=asyncio.create_task(respond(json.loads(row['data'])));tasks.add(task);task.add_done_callback(tasks.discard)
                await asyncio.sleep(.1)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
