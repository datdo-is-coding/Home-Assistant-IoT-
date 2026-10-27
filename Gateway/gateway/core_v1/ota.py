"""Signed, model-bound OTA artifacts and serialized room update jobs.

Only public verification keys are accepted here. The offline signer is external
and never runs on the production gateway.
"""
import hashlib
import math
from pathlib import Path
import re
import secrets
import struct
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec,utils
from .registry import CoreError,require,uid,canonical
from .protocol import MessageType

MANIFEST=struct.Struct('<16s16sI32s')
ACTIVE=('QUEUED','TRANSFERRING','VERIFYING','REBOOTING','HEALTH_CHECK')

def manifest_bytes(m):
    require(isinstance(m,dict) and set(m)=={'model','version','size','sha256'})
    for field in ('model','version'):
        require(isinstance(m[field],str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,15}',m[field]) is not None)
    require(type(m['size'])==int and 0<m['size']<=0x2f0000)
    require(isinstance(m['sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',m['sha256']) is not None)
    return MANIFEST.pack(m['model'].encode(),m['version'].encode(),m['size'],bytes.fromhex(m['sha256']))

class OtaManager:
    def __init__(self,registry,directory,public_key,*,recover=True,retry_interval=1,chunk_window=1):
        require(isinstance(public_key,ec.EllipticCurvePublicKey) and isinstance(public_key.curve,ec.SECP256R1))
        self.r=registry; self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.public_key=public_key; self.waiting={}
        require(type(retry_interval) in (int,float) and .05<=retry_interval<=1)
        self.retry_interval=retry_interval;self.retry_attempts=math.ceil(5/retry_interval)
        require(type(chunk_window) is int and 1<=chunk_window<=4)
        self.chunk_window=chunk_window

        if recover:self.r.db.execute("UPDATE ota_targets SET status='FAILED',reason='gateway_restart' WHERE status IN ('TRANSFERRING','VERIFYING')")

    def upload(self,manifest,signature,image):
        raw=manifest_bytes(manifest)
        require(isinstance(signature,str) and re.fullmatch(r'[0-9a-f]{128}',signature) is not None)
        sig=bytes.fromhex(signature)
        try:self.public_key.verify(utils.encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big')),raw,ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as e:raise CoreError('invalid_signature',status=400) from e
        require(isinstance(image,bytes) and len(image)==manifest['size'] and hashlib.sha256(image).hexdigest()==manifest['sha256'],'hash_mismatch')
        require(len(image)>=288 and image[0]==0xe9 and 1<=image[1]<=16
                and struct.unpack_from('<H',image,12)[0]==9
                and struct.unpack_from('<I',image,32)[0]==0xabcd5432,'invalid_esp32s3_image')
        image_version=image[48:80].split(b'\0',1)[0].decode('ascii')
        require(image_version==manifest['version'],'image_version_mismatch')
        existing=self.r.db.execute('SELECT artifact_id FROM firmware_artifacts WHERE sha256=?',(manifest['sha256'],)).fetchone()
        if existing:return self.artifact(existing[0])
        artifact=uid('FW-');path=self.directory/(manifest['sha256']+'.bin')
        with path.open('xb') as f:f.write(image)
        path.chmod(0o600)
        self.r.db.execute('INSERT INTO firmware_artifacts VALUES(?,?,?,?,?,?,?,?,?)',(artifact,manifest['model'],manifest['version'],manifest['size'],manifest['sha256'],canonical(manifest).decode(),signature,str(path),self.r.clock()))
        return self.artifact(artifact)

    def artifact(self,artifact):
        return self.r.one('SELECT artifact_id,model,version,size,sha256,manifest,signature FROM firmware_artifacts WHERE artifact_id=?',(artifact,))

    def artifacts(self):
        return self.r.rows('SELECT artifact_id,model,version,size,sha256,created FROM firmware_artifacts ORDER BY created DESC')

    def read_chunk(self,artifact,offset):
        a=self.r.one('SELECT * FROM firmware_artifacts WHERE artifact_id=?',(artifact,))
        require(type(offset)==int and 0<=offset<a['size'])
        with open(a['path'],'rb') as f:f.seek(offset);return f.read(192)

    def create_job(self,user,home,artifact,nodes):
        self.r.authorize(user,home,('Owner',))
        require(isinstance(nodes,list) and 1<=len(nodes)<=16 and all(type(n)==int for n in nodes) and len(set(nodes))==len(nodes))
        a=self.artifact(artifact)
        selected=[self.r.get_node(user,n) for n in nodes]
        for n in selected:require(n['home_id']==home and n['model']==a['model'] and n['registration']=='REGISTERED','wrong_target')
        job=uid('OTA-')
        with self.r.transaction():
            self.r.db.execute('INSERT INTO ota_jobs VALUES(?,?,?,?,?)',(job,home,artifact,self.r.clock(),user))
            for n in selected:self.r.db.execute('INSERT INTO ota_targets(job_id,node_id,status,old_boot,updated) VALUES(?,?,?,?,?)',(job,n['node_id'],'QUEUED',n['boot_id'],self.r.clock()))
            self.r.audit(user,home,'ota_created',job)
        return self.job(user,job)

    def job(self,user,job):
        j=self.r.one('SELECT * FROM ota_jobs WHERE job_id=?',(job,));self.r.authorize(user,j['home_id'])
        a=self.artifact(j['artifact_id'])
        j['targets']=self.r.rows('SELECT * FROM ota_targets WHERE job_id=?',(job,))
        for target in j['targets']:
            target['transfer_percent']=round(100*target['offset']/a['size'],1)
            target['version']=a['version'];target['model']=a['model']
        return j

    def update(self,job,node,status,offset=None,reason=None):
        with self.r.transaction():
            self.r.db.execute('UPDATE ota_targets SET status=?,offset=coalesce(?,offset),reason=?,updated=? WHERE job_id=? AND node_id=?',(status,offset,reason,self.r.clock(),job,node))
            j=self.r.one('SELECT home_id FROM ota_jobs WHERE job_id=?',(job,))
            self.r.event(j['home_id'],'ota',{'job_id':job,'node_id':node,'status':status,'offset':offset,'reason':reason})

    def start_payload(self,artifact,node=None):
        import json
        return manifest_bytes(json.loads(artifact['manifest']))+bytes.fromhex(artifact['signature'])

    def outgoing(self,bridge):
        import json
        targets=self.r.rows("SELECT t.*,j.artifact_id FROM ota_targets t JOIN ota_jobs j USING(job_id) WHERE t.status IN ('QUEUED','TRANSFERRING','VERIFYING','REBOOTING','HEALTH_CHECK') ORDER BY j.created,t.node_id")
        busy=set();result=[]
        for t in targets:
            node=t['node_id'];parent=bridge.route(node)
            if parent in busy:continue
            busy.add(parent)
            if node not in bridge.windows:continue
            key=(t['job_id'],node)
            if t['status']=='VERIFYING':
                current=self.r.one('SELECT boot_id FROM registered_nodes WHERE node_id=?',(node,))['boot_id']
                if current is not None and current!=t['old_boot']:
                    self.update(t['job_id'],node,'REBOOTING');self.waiting.pop(key,None);continue
                if self.r.clock()-t['updated']>300:
                    self.update(t['job_id'],node,'FAILED',reason='verification_timeout');self.waiting.pop(key,None);continue
            if t['status'] in ('REBOOTING','HEALTH_CHECK'):
                # Device health can take 120 s to fail, then reboot and report rollback.
                if self.r.clock()-t['updated']>300:self.update(t['job_id'],node,'FAILED',reason='health_timeout')
                continue
            pending=self.waiting.get(key)
            if pending:
                if self.r.clock()<pending[0]:continue
                if pending[1]>=self.retry_attempts and pending[3]!=MessageType.OTA_OFFER:
                    self.update(t['job_id'],node,'FAILED',reason='transfer_timeout');self.waiting.pop(key,None)
                    result.append((parent,bridge.frame(node,MessageType.OTA_ABORT)));continue
            a=self.artifact(t['artifact_id']);attempts=pending[1]+1 if pending else 1
            if t['status']=='QUEUED':
                if pending is None:
                    self.r.db.execute('UPDATE ota_targets SET old_boot=(SELECT boot_id FROM registered_nodes WHERE node_id=?) WHERE job_id=? AND node_id=?',(node,t['job_id'],node))
                payloads=[self.start_payload(a,node)]
                typ=MessageType.OTA_START
            elif t['offset']<a['size']:
                payloads=[struct.pack('<I',at)+self.read_chunk(t['artifact_id'],at)
                          for at in range(t['offset'],min(a['size'],t['offset']+192*self.chunk_window),192)]
                typ=MessageType.OTA_CHUNK
            else:
                payloads=[b''];typ=MessageType.OTA_OFFER
                if t['status']!='VERIFYING':self.update(t['job_id'],node,'VERIFYING')
            expected=0 if typ==MessageType.OTA_START else (t['offset']+sum(len(p)-4 for p in payloads) if typ==MessageType.OTA_CHUNK else a['size'])
            interval=max(1,self.retry_interval) if typ==MessageType.OTA_OFFER else self.retry_interval
            self.waiting[key]=(self.r.clock()+interval,attempts,expected,typ)
            result.extend((parent,bridge.frame(node,typ,payload)) for payload in payloads)
        return result

    def receive(self,frame):
        rows=self.r.rows("SELECT t.*,j.artifact_id FROM ota_targets t JOIN ota_jobs j USING(job_id) WHERE node_id=? AND status IN ('QUEUED','TRANSFERRING','VERIFYING','REBOOTING','HEALTH_CHECK')",(frame.source,))
        late=False
        if not rows and frame.type==MessageType.OTA_RESULT:
            rows=self.r.rows('SELECT t.*,j.artifact_id FROM ota_targets t JOIN ota_jobs j USING(job_id) WHERE node_id=? ORDER BY j.created DESC LIMIT 1',(frame.source,))
            late=bool(rows and rows[0]['status']=='FAILED' and rows[0]['reason'] in ('transfer_timeout','verification_timeout','health_timeout','gateway_restart'))
            require(late,'not_found',404)
        require(bool(rows),'not_found',404);t=rows[0]
        a=self.artifact(t['artifact_id']); key=(t['job_id'],frame.source)
        if late:require(t['offset']==a['size'],'boot_unconfirmed')
        if frame.type in (MessageType.OTA_PROGRESS,MessageType.OTA_CHUNK_ACK):
            require(len(frame.payload)==5)
            offset,status=struct.unpack('<IB',frame.payload)
            require(status==2 or 0<=offset<=a['size'],'invalid_progress')
            if status==0 and t['status']!='QUEUED' and offset<=t['offset']:return
            require(status==2 or offset>=t['offset'],'invalid_progress')
            pending=self.waiting.get(key)
            require(pending is not None,'unsolicited_progress')
            require(status==2 or offset<=pending[2] or pending[3]==MessageType.OTA_START,'invalid_progress')
            if status==1:require(pending[3]==MessageType.OTA_OFFER and offset==a['size'],'invalid_progress')
            if status==0:
                self.update(t['job_id'],frame.source,'TRANSFERRING',offset)
                if pending[3]==MessageType.OTA_CHUNK and offset<pending[2]:
                    self.waiting[key]=(pending[0],0,pending[2],pending[3])
                    return
            elif status==1:self.update(t['job_id'],frame.source,'REBOOTING',offset)
            elif status==2:self.update(t['job_id'],frame.source,'FAILED',reason='device_verification_failed')
            else:raise CoreError('invalid_progress')
            self.waiting.pop(key,None)
        elif frame.type==MessageType.OTA_RESULT:
            require(len(frame.payload)==49)
            version=frame.payload[:16].split(b'\0',1)[0].decode('ascii');digest=frame.payload[16:48].hex();health=frame.payload[48]
            require((late or t['status'] in ('VERIFYING','REBOOTING','HEALTH_CHECK')) and str(frame.boot_id)!=t['old_boot'],'boot_unconfirmed')
            if health==1 and version==a['version'] and digest==a['sha256']:
                self.update(t['job_id'],frame.source,'SUCCEEDED',a['size'],reason='late_boot_confirmation' if late else None)
                self.r.db.execute('UPDATE registered_nodes SET firmware=? WHERE node_id=?',(version,frame.source))
            elif health==2:self.update(t['job_id'],frame.source,'ROLLED_BACK',reason='boot_health_failed')
            elif late:raise CoreError('boot_unconfirmed')
            else:self.update(t['job_id'],frame.source,'FAILED',reason='boot_result_mismatch')
            self.waiting.pop(key,None)
