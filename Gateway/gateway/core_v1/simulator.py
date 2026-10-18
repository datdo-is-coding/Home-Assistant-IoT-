"""Deterministic multi-Box transport simulation; never accesses GPIO or radio."""
import ctypes
import hashlib
import hmac
from pathlib import Path
import struct
import subprocess
import tempfile
from .registry import Registry,canonical
from .bridge import Bridge,CHANNEL,COMMAND,ACK
from .protocol import Frame,MessageType,ReplayWindow


class SimBox:
    def __init__(self,node,parent,key,clock,guard,subbox=False):
        self.node=node;self.parent=parent;self.key=key;self.clock=clock;self.guard=guard
        self.subbox=subbox;self.boot=node*100+1;self.sequence=0;self.revision=1
        self.nonce=bytes([node%256])*16;self.gateway=ReplayWindow();self.generations=(ctypes.c_uint64*3)()
        self.states=[False]*3;self.applied=0;self.acks={}

    def send(self,typ,payload=b'',message_id=None):
        self.sequence+=1
        return Frame(typ,message_id or self.sequence,self.node,0,self.boot,self.sequence,self.revision,payload).encode(self.key)

    def hello(self):return self.send(MessageType.HELLO,self.nonce)

    def report(self):
        payload=struct.pack('<Q',int(self.clock()*1000))
        if not self.subbox:payload+=b''.join(CHANNEL.pack(i+1,2|int(on),.25 if on else 0.,0) for i,on in enumerate(self.states))
        return self.send(MessageType.HEARTBEAT if self.subbox else MessageType.STATE_REPORT,payload)

    def receive(self,data):
        f=Frame.decode(data,self.key)
        if f.type==MessageType.IDENTITY_CHALLENGE:
            if f.payload[:16]!=self.nonce:return []
            self.gateway.admit(f.boot_id)
            return [self.send(MessageType.IDENTITY_RESPONSE,f.payload[16:])]
        replay=self.gateway.check(f.boot_id,f.sequence)
        if replay not in ('NEW','DUPLICATE'):return []
        if f.type==MessageType.CONFIG_PUSH:
            rev=struct.unpack('<I',f.payload)[0]
            if rev<self.revision:return []
            self.revision=rev
            return [self.send(MessageType.CONFIG_ACK,f.payload),self.report()]
        if f.type==MessageType.COMMAND:
            channel,desired,deadline,generation=COMMAND.unpack(f.payload)
            if f.message_id in self.acks:return [self.send(MessageType.COMMAND_ACK,self.acks[f.message_id])]
            if f.config_rev!=self.revision or replay!='NEW':return []
            if not self.guard(self.generations,channel,desired,generation,deadline,int(self.clock()*1000)):return []
            self.states[channel-1]=bool(desired);self.applied+=1
            ack=ACK.pack(f.message_id,2,desired);self.acks[f.message_id]=ack
            return [self.send(MessageType.COMMAND_ACK,ack),self.report()]
        return []


class Simulation:
    def __init__(self,root):
        self.now=1000.;self.root=Path(root)
        croot=Path(__file__).resolve().parents[3]/'Firmware/firmware_esp/common/hc_core'
        lib=self.root/'hc-policy.so'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',str(croot/'hc_protocol.c'),'-I',str(croot),'-o',str(lib)],check=True)
        self.lib=ctypes.CDLL(str(lib));self.guard=self.lib.hc_command_admit
        self.guard.argtypes=[ctypes.POINTER(ctypes.c_uint64),ctypes.c_uint8,ctypes.c_uint8,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64]
        self.registry=Registry(self.root/'core.db',b'k'*32,clock=lambda:self.now)
        self.owner,self.token=self.registry.create_user('Simulation Owner')
        self.home=self.registry.create_home(self.owner,'Simulated Home')
        self.bridge=Bridge(self.registry);self.boxes={};self.factory_index=0

    def add(self,room,parent=None):
        self.factory_index+=1;factory=f'HC-020000{self.factory_index:06X}'
        secret=hashlib.sha256(factory.encode()).digest();kind='ACTION_BOX' if parent else 'SUB_BOX'
        self.registry.add_factory_device(factory,kind,'HC-A1' if parent else 'HC-S1',secret,'simulation-setup-'+factory)
        claim=self.registry.claim(self.owner,factory,'simulation-setup-'+factory,room,parent)
        confirm=dict(claim=claim,stored=True,peer_confirmed=True,channels=3 if parent else 0)
        node=self.registry.confirm_claim(claim['claim_id'],hmac.digest(secret,canonical(confirm),'sha256').hex(),stored=True,peer_confirmed=True,channels=confirm['channels'])['node_id']
        box=SimBox(node,parent or node,self.registry.node_key(node),lambda:self.now,self.guard,not parent)
        self.boxes[node]=box;self.deliver_up(box,box.hello());return box

    def deliver_up(self,box,data):
        for parent,reply in self.bridge.receive(box.parent,data):
            self.deliver_down(reply)

    def deliver_down(self,data,drop_ack=False):
        node=struct.unpack_from('<I',data,18)[0];box=self.boxes[node]
        responses=box.receive(data)
        for response in responses:
            f=Frame.decode(response,box.key)
            if drop_ack and f.type==MessageType.COMMAND_ACK:continue
            self.deliver_up(box,response)
        return responses

    def pump(self):
        for parent,data in self.bridge.outgoing():self.deliver_down(data)

    def close(self):self.registry.close()


def main():
    with tempfile.TemporaryDirectory() as directory:
        sim=Simulation(directory)
        try:
            for index in range(2):
                room=sim.registry.create_room(sim.owner,sim.home,f'Room {index+1}')
                parent=sim.add(room)
                for child in range(2):
                    box=sim.add(room,parent.node)
                    channel=sim.registry.channels(sim.owner,box.node)[0]['channel_id']
                    device=sim.registry.create_device(sim.owner,sim.home,f'Light {box.node}','light',channel)
                    sim.pump();sim.registry.command(sim.owner,device['device_id'],True,f'cmd-{box.node}');sim.pump()
            commands=sim.registry.rows('SELECT status FROM commands')
            assert all(c['status']=='APPLIED' for c in commands)
            print(f'SIMULATION PASS: 2 SubBoxes, 4 ActionBoxes, {len(commands)} APPLIED commands; no radio or hardware tested.')
        finally:sim.close()


if __name__=='__main__':main()
