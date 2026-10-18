"""HC-WIFI carries the same authenticated binary frames as HC-NOW.

The SubBox forwards them unchanged. Broker ACLs restrict each SubBox to its own
hc/v1/subbox/<node>/up and down topics; the tag is additionally verified here.
"""
import asyncio
import hmac
import logging
import secrets
import ssl
import struct
import time
import aiomqtt
from .protocol import Frame, MessageType, ReplayWindow
from .registry import CoreError, canonical, require
from .provisioning import Provisioning

CHANNEL = struct.Struct('<BBfH')
COMMAND = struct.Struct('<BBQQ')
ACK = struct.Struct('<QBB')

class Bridge:
    def __init__(self,registry):
        self.registry=registry
        self.boot=secrets.randbits(63) or 1
        self.sequence=0
        self.windows={}
        self.challenges={}
        self.command_ids={}
        self.uptimes={}
        self.ota=None
        self.ha=None
        self.last_heartbeat=0
        self.provisioning=Provisioning(registry)
        self.last_grant=0

    def key(self,node,typ):
        n=self.registry.one('SELECT registration FROM registered_nodes WHERE node_id=?',(node,))
        if n['registration']=='REGISTERED':
            return self.registry.node_key(node)
        require(typ in (MessageType.HELLO,MessageType.IDENTITY_CHALLENGE,MessageType.IDENTITY_RESPONSE,
                       MessageType.PAIR_REQUEST,MessageType.PAIR_ACCEPT),'registration_required',403)
        return self.provisioning.pending(node)[0]

    def frame(self,node,typ,payload=b'',revision=None,message_id=None):
        self.sequence+=1
        if self.sequence>=2**32: raise RuntimeError('Gateway session renewal required')
        n=self.registry.one('SELECT * FROM registered_nodes WHERE node_id=?',(node,))
        return Frame(typ,message_id or secrets.randbits(63) or 1,0,node,self.boot,self.sequence,
                     n['config_rev'] if revision is None else revision,payload).encode(self.key(node,typ))

    def route(self,node):
        n=self.registry.one('SELECT registration FROM registered_nodes WHERE node_id=?',(node,))
        if n['registration'] in ('PAIRING','TRANSFER_PENDING'):
            return self.provisioning.pending(node)[1] or node
        a=self.registry.one('SELECT * FROM node_assignments WHERE node_id=? AND active=1',(node,))
        return a['parent_id'] or node

    def receive(self,parent,data):
        require(isinstance(data,bytes) and 54<=len(data)<=250,'bad_frame')
        node=struct.unpack_from('<I',data,14)[0]
        require(self.route(node)==parent,'wrong_parent',403)
        f=Frame.decode(data,self.key(node,data[3]))
        require(f.destination==0,'wrong_destination')
        n=self.registry.one('SELECT * FROM registered_nodes WHERE node_id=?',(node,))
        if f.type==MessageType.HELLO:
            require(len(f.payload)==16)

            current=self.windows.get(node)
            old=self.challenges.get(node)
            if old and old[0]==f.boot_id and old[3]==f.payload and time.monotonic()<old[2]:
                nonce=old[1]
            else:
                require(n['boot_id']==str(f.boot_id) or not self.registry.db.execute('SELECT 1 FROM admitted_boots WHERE node_id=? AND boot_id=?',(node,str(f.boot_id))).fetchone(),'boot_replay',409)
                nonce=secrets.token_bytes(16)
                self.challenges[node]=(f.boot_id,nonce,time.monotonic()+30,f.payload)
            return [(parent,self.frame(node,MessageType.IDENTITY_CHALLENGE,f.payload+nonce))]
        if f.type==MessageType.IDENTITY_RESPONSE:
            c=self.challenges.get(node)
            require(c is not None and c[0]==f.boot_id and time.monotonic()<c[2] and hmac.compare_digest(c[1],f.payload),'challenge_failed',403)

            if n['registration']=='REGISTERED':
                challenge=self.registry.session_challenge(node,f.boot_id)
                self.registry.admit_session(node,challenge['nonce'],hmac.digest(self.registry.node_key(node),canonical(challenge),'sha256').hex())
            window=self.windows.get(node,ReplayWindow()); window.admit(f.boot_id); window.check(f.boot_id,f.sequence)
            self.windows[node]=window
            del self.challenges[node]
            if n['registration']!='REGISTERED': return []
            return [(parent,self.frame(node,MessageType.CONFIG_PUSH,struct.pack('<I',n['config_rev'])))]
        w=self.windows.get(node)
        require(w is not None,'session_required',403)
        replay=w.check(f.boot_id,f.sequence)
        if replay in ('DUPLICATE','STALE'): return []
        require(replay=='NEW','session_required',403)
        if f.type==MessageType.PAIR_REQUEST:
            enrolled=self.provisioning.accept_receipt(f.payload)
            if enrolled:
                target=enrolled['node_id']
                return [(self.route(target),self.frame(target,MessageType.PAIR_ACCEPT,f.payload[4:36]))]
            return []
        require(n['registration']=='REGISTERED','registration_required',403)
        if f.type==MessageType.CONFIG_ACK:
            require(len(f.payload)==4 and struct.unpack('<I',f.payload)[0]==n['config_rev'],'config_mismatch',409)
            self.registry.db.execute('UPDATE registered_nodes SET reported_rev=?,last_seen=? WHERE node_id=?',(n['config_rev'],self.registry.clock(),node))
        elif f.type in (MessageType.STATE_REPORT,MessageType.TELEMETRY_REPORT):
            require(len(f.payload)==8+3*CHANNEL.size)
            self.uptimes[node]=(struct.unpack_from('<Q',f.payload)[0],self.registry.clock())
            channels=[]
            for number,flags,current,fault in CHANNEL.iter_unpack(f.payload[8:]):
                require(flags&~3==0)
                channels.append(dict(number=number,relay_state=bool(flags&1),ct_valid=bool(flags&2),current_rms_a=current if flags&2 else None,fault_flags=fault))
            self.registry.report_state(node,dict(node_id=node,boot_id=f.boot_id,state_seq=f.sequence,config_rev=f.config_rev,channels=channels))
        elif f.type==MessageType.COMMAND_ACK:
            require(len(f.payload)==ACK.size)
            wire_id,status,reported=ACK.unpack(f.payload)
            require(status in (0,1,2,3) and reported in (0,1))
            command=self.command_ids.get((node,wire_id))
            require(command is not None,'unknown_command')
            self.registry.ack(node,command,('RECEIVED','ACCEPTED','APPLIED','FAILED')[status],f.config_rev,bool(reported))
        elif f.type==MessageType.HEARTBEAT:
            require(len(f.payload)==8)
            self.uptimes[node]=(struct.unpack('<Q',f.payload)[0],self.registry.clock())
            self.registry.db.execute("UPDATE registered_nodes SET last_seen=?,connectivity='ONLINE' WHERE node_id=?",(self.registry.clock(),node))
        elif f.type in (MessageType.OTA_PROGRESS,MessageType.OTA_CHUNK_ACK,MessageType.OTA_RESULT) and self.ota:
            self.ota.receive(f)
            if f.type==MessageType.OTA_RESULT:
                return [(parent,self.frame(node,MessageType.OTA_RESULT))]
        elif f.type==MessageType.STATE_SYNC_REQUEST:
            return [(parent,self.frame(node,MessageType.CONFIG_PUSH,struct.pack('<I',n['config_rev'])))]
        return []

    def outgoing(self):
        result=[]
        active=set()
        for c in self.registry.due_commands():
            wire_id=int.from_bytes(bytes.fromhex(c['command_id'][4:20]),'little') or 1
            self.command_ids[(c['node_id'],wire_id)]=c['command_id']
            remaining=max(0,int((c['expires']-self.registry.clock())*1000))
            if not remaining or c['node_id'] not in self.uptimes: continue
            uptime,observed=self.uptimes[c['node_id']]
            deadline=uptime+int((self.registry.clock()-observed)*1000)+remaining
            number=int(c['channel_id'].rsplit('CH',1)[1])
            result.append((c['parent_id'],self.frame(c['node_id'],MessageType.COMMAND,COMMAND.pack(number,c['desired'],deadline,c['generation']),c['config_rev'],wire_id)))
        live={r['command_id'] for r in self.registry.rows("SELECT command_id FROM commands WHERE status IN ('RECEIVED','ACCEPTED')")}
        self.command_ids={k:v for k,v in self.command_ids.items() if v in live}

        for n in self.registry.rows("SELECT * FROM registered_nodes WHERE registration='REGISTERED' AND reported_rev<config_rev"):
            if n['node_id'] in self.windows:
                result.append((self.route(n['node_id']),self.frame(n['node_id'],MessageType.CONFIG_PUSH,struct.pack('<I',n['config_rev']))))
        if self.registry.clock()-self.last_heartbeat>=5:
            self.last_heartbeat=self.registry.clock()
            for node in self.windows:
                try: result.append((self.route(node),self.frame(node,MessageType.HEARTBEAT)))
                except CoreError: pass
        if self.ota: result.extend(self.ota.outgoing(self))
        if self.registry.clock()-self.last_grant>=2:
            self.last_grant=self.registry.clock()
            for parent,grant in self.provisioning.outgoing_grants():
                if parent in self.windows:
                    result.append((parent,self.frame(parent,MessageType.PAIR_ACCEPT,grant)))
        return result

async def run_mqtt(bridge,host,port,username,password,ca):
    context=ssl.create_default_context(cafile=ca)
    delay=1
    while True:
        try:
            async with aiomqtt.Client(hostname=host,port=port,username=username,password=password,tls_context=context,
                                      identifier='home-competition-core',max_queued_incoming_messages=128,max_queued_outgoing_messages=128,
                                      will=aiomqtt.Will('hc/v1/gateway/availability',b'offline',qos=1,retain=True)) as client:
                await client.subscribe('hc/v1/subbox/+/up',qos=1)
                if bridge.ha:
                    for topic in bridge.ha.subscriptions:
                        await client.subscribe(topic,qos=1)
                    bridge.ha.force=True
                await client.publish('hc/v1/gateway/availability',b'online',qos=1,retain=True)
                delay=1
                async def publish_due():
                    while True:
                        for parent,data in bridge.outgoing():
                            await client.publish(f'hc/v1/subbox/{parent}/down',data,qos=1,retain=False)
                        if bridge.ha:
                            try:
                                messages=bridge.ha.outgoing()
                            except CoreError:
                                messages=[]
                            for message in messages:
                                await client.publish(message.topic,message.payload,qos=message.qos,retain=message.retain)
                        await asyncio.sleep(.25)
                async def receive_messages():
                    async for message in client.messages:
                        try:
                            topic=str(message.topic)
                            if bridge.ha and (topic=='homeassistant/status' or topic.startswith(bridge.ha.root+'/')):
                                bridge.ha.receive(topic,bytes(message.payload),retained=message.retain)
                                continue
                            require(not message.retain,'retained_control',400)
                            parts=topic.split('/')
                            require(len(parts)==5 and parts[:3]==['hc','v1','subbox'] and parts[4]=='up','invalid_topic')
                            parent=int(parts[3])
                            for target,data in bridge.receive(parent,bytes(message.payload)):
                                await client.publish(f'hc/v1/subbox/{target}/down',data,qos=1,retain=False)
                        except (CoreError,ValueError,TypeError,IndexError):
                            logging.getLogger(__name__).warning('Rejected HC frame')
                sender=asyncio.create_task(publish_due())
                receiver=asyncio.create_task(receive_messages())
                try:
                    done,_=await asyncio.wait((sender,receiver),return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    sender.cancel();receiver.cancel()
                    await asyncio.gather(sender,receiver,return_exceptions=True)
        except aiomqtt.MqttError:
            await asyncio.sleep(delay)
            delay=min(30,delay*2)
