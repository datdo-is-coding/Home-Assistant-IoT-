"""Authenticated local OTA pilot coordinator, independent of the control Gateway.

No Internet server and no command endpoint; factory roster contains per-device
keys. The only operations exposed by the local CLI are inventory and signed OTA.
"""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import ssl
from pathlib import Path
import struct
from cryptography.hazmat.primitives import serialization
from gateway.core_v1.registry import Registry,uid,canonical
from gateway.core_v1.ota import OtaManager
from gateway.core_v1.bridge import Bridge,run_mqtt
from gateway.core_v1.release import private_write,read_key
from .manifest import verify_target

class LocalOtaManager(OtaManager):
    def __init__(self,registry,directory,public_key,targets,*,recover=True):
        super().__init__(registry,directory,public_key,recover=recover,retry_interval=.5,chunk_window=4)
        self.targets=targets
        registry.db.execute("CREATE TABLE IF NOT EXISTS ota_v2_targets(artifact_id TEXT NOT NULL, node_id INTEGER NOT NULL, target BLOB NOT NULL, PRIMARY KEY(artifact_id,node_id))")

    def upload_target(self,target_id,packet,image):
        policy=self.targets.get(target_id)
        if policy is None:raise ValueError('unknown_target')
        m=verify_target(packet,self.public_key,compatibility_id=policy['compatibility_id'],role=policy['role'],image=image)
        if len(image)<288 or image[0]!=0xe9 or not 1<=image[1]<=16 or struct.unpack_from('<H',image,12)[0]!=9 or struct.unpack_from('<I',image,32)[0]!=0xabcd5432:
            raise ValueError('invalid_image')
        version=image[48:80].split(b'\0',1)[0].decode('ascii')
        if version!=m['version']:raise ValueError('image_version_mismatch')
        existing=self.r.db.execute('SELECT artifact_id FROM firmware_artifacts WHERE sha256=?',(m['sha256'],)).fetchone()
        if existing:
            old=self.artifact(existing[0])
            if old['model']!=policy['model'] or old['version']!=m['version'] or not json.loads(old['manifest']).get('target_v2'):raise ValueError('artifact_metadata_conflict')
            prior=self.r.db.execute('SELECT target FROM ota_v2_targets WHERE artifact_id=? AND node_id=?',(old['artifact_id'],policy['node_id'])).fetchone()
            if prior and bytes(prior[0])!=packet:raise ValueError('target_metadata_conflict')
            self.r.db.execute('INSERT OR IGNORE INTO ota_v2_targets VALUES(?,?,?)',(old['artifact_id'],policy['node_id'],packet))
            return old
        manifest={'model':policy['model'],'version':m['version'],'size':m['size'],'sha256':m['sha256'],'target_v2':True}
        artifact=uid('FW-');path=self.directory/(m['sha256']+'.bin')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as out:out.write(image);out.flush();os.fsync(out.fileno())
        self.r.db.execute('INSERT INTO firmware_artifacts VALUES(?,?,?,?,?,?,?,?,?)',
          (artifact,policy['model'],m['version'],m['size'],m['sha256'],canonical(manifest).decode(),packet[112:].hex(),str(path),self.r.clock()))
        self.r.db.execute('INSERT INTO ota_v2_targets VALUES(?,?,?)',(artifact,policy['node_id'],packet))
        return self.artifact(artifact)

    def start_payload(self,artifact,node=None):
        if json.loads(artifact['manifest']).get('target_v2'):
            row=self.r.one('SELECT target FROM ota_v2_targets WHERE artifact_id=? AND node_id=?',(artifact['artifact_id'],node))
            return bytes(row['target'])
        return super().start_payload(artifact,node)

def private_config(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:raise ValueError('configuration must be a private regular file')
    return json.loads(path.read_text())

def initialize(data,config,*,recover=False):
    data=Path(data);data.mkdir(mode=0o700,parents=True,exist_ok=True)
    keypath=data/'master.key'
    if keypath.exists():master=read_key(keypath)
    else:
        master=os.urandom(32);private_write(keypath,master)
        fd=os.open(data,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    registry=Registry(data/'core.db',master,recover=recover)
    if not registry.db.execute('SELECT 1 FROM homes').fetchone():
        registry.db.execute('INSERT INTO users VALUES(?,?,?)',('ota-local-operator','Local factory OTA operator',hashlib.sha256(os.urandom(32)).hexdigest()))
        registry.db.execute('INSERT INTO homes VALUES(?,?)',('local-pilot','Authorized local OTA pilot'))
        registry.db.execute('INSERT INTO home_members VALUES(?,?,?)',('local-pilot','ota-local-operator','Owner'))
        registry.db.execute('INSERT INTO rooms VALUES(?,?,?)',('local-room','local-pilot','Local OTA pilot'))
        for target in sorted(config['targets'],key=lambda x:x['role']):
            node=target['node_id'];factory=target['factory_id']
            registry.add_factory_device(factory,'SUB_BOX' if target['role']==1 else 'ACTION_BOX',target['model'],bytes.fromhex(target['factory_secret']),target['setup'])
            registry.db.execute('INSERT INTO registered_nodes(node_id,factory_id,home_id,registration,config_rev) VALUES(?,?,?,?,?)',(node,factory,'local-pilot','REGISTERED',1))
            registry.db.execute('INSERT INTO node_assignments(node_id,room_id,parent_id,primary_subbox) VALUES(?,?,?,?)',(node,'local-room',target.get('parent_id') or None,1 if target['role']==1 else 0))
            registry.db.execute('INSERT INTO node_credentials(node_id,key_cipher) VALUES(?,?)',(node,registry.cipher.encrypt(bytes.fromhex(target['key']))))
            if target['role']==2:
                for channel in (1,2,3):
                    cid=f'{factory}:CH{channel}'
                    registry.db.execute('INSERT INTO channels(channel_id,node_id,number) VALUES(?,?,?)',(cid,node,channel))
                    registry.db.execute('INSERT INTO channel_states(channel_id) VALUES(?)',(cid,))
    public=serialization.load_pem_public_key(Path(config['release_public_key']).read_bytes())
    manager=LocalOtaManager(registry,data/'images',public,{t['factory_id']:t for t in config['targets']},recover=recover)
    return registry,manager

async def serve(data,config):
    data=Path(data);data.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(data/'.coordinator.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'rb') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        registry,manager=initialize(data,config,recover=True);bridge=Bridge(registry);bridge.ota=manager
        mqtt=config['mqtt']
        context=ssl.create_default_context(cafile=mqtt['ca'])
        if mqtt.get('legacy_ca') is True:
            # shortcut: pilot CA lacks KeyUsage; remove this option when the broker CA rotates.
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        task=asyncio.create_task(run_mqtt(bridge,mqtt['host'],mqtt['port'],mqtt['username'],mqtt['password'],mqtt['ca'],poll_interval=.01,client_id='homecompetition-ota-local',tls_context=context))
        try:await task
        finally:task.cancel();registry.close()

def main():
    p=argparse.ArgumentParser(description='Local-only signed OTA pilot; no relay control API')
    p.add_argument('--config',required=True);p.add_argument('--data',required=True)
    sub=p.add_subparsers(dest='action',required=True);sub.add_parser('serve');sub.add_parser('status')
    install=sub.add_parser('queue');install.add_argument('factory_id');install.add_argument('target');install.add_argument('image')
    args=p.parse_args();config=private_config(args.config)
    if args.action=='serve':asyncio.run(serve(args.data,config));return
    registry,manager=initialize(args.data,config)
    try:
        if args.action=='status':
            print(json.dumps({'nodes':registry.rows('SELECT node_id,registration,connectivity,firmware,boot_id FROM registered_nodes'),
              'updates':registry.rows('SELECT job_id,node_id,status,offset,reason FROM ota_targets')},indent=2));return
        target=next((t for t in config['targets'] if t['factory_id']==args.factory_id),None)
        if target is None:raise ValueError('unknown target')
        artifact=manager.upload_target(args.factory_id,Path(args.target).read_bytes(),Path(args.image).read_bytes())
        print(json.dumps(manager.create_job('ota-local-operator','local-pilot',artifact['artifact_id'],[target['node_id']]),indent=2))
    finally:registry.close()

if __name__=='__main__':main()
