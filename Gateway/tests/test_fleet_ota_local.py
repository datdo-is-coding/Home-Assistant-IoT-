import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric import ec,utils
from cryptography.hazmat.primitives import hashes
from gateway.core_v1.registry import Registry
from gateway.fleet_ota.manifest import target_header,key_id
from gateway.fleet_ota.local import LocalOtaManager

class LocalOta(unittest.TestCase):
 def test_second_coordinator_fails_before_recovering_jobs(self):
  import asyncio,fcntl
  from unittest.mock import patch
  from gateway.fleet_ota.local import serve
  with tempfile.TemporaryDirectory() as d:
   with (Path(d)/'.coordinator.lock').open('wb') as guard:
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch('gateway.fleet_ota.local.initialize') as initialize:
     with self.assertRaises(BlockingIOError):asyncio.run(serve(d,{}))
     initialize.assert_not_called()

 def test_rejected_mqtt_suback_stops_before_publishing(self):
  import asyncio
  from types import SimpleNamespace
  from unittest.mock import AsyncMock,Mock,patch
  from gateway.core_v1.bridge import run_mqtt
  class MqttError(Exception):pass
  client=Mock();client.subscribe=AsyncMock(return_value=[128]);client.publish=AsyncMock()
  context=Mock();context.__aenter__=AsyncMock(return_value=client);context.__aexit__=AsyncMock(return_value=False)
  mqtt=SimpleNamespace(Client=Mock(return_value=context),Will=Mock(),MqttError=MqttError)
  with patch('gateway.core_v1.bridge.aiomqtt',mqtt),patch('gateway.core_v1.bridge.asyncio.sleep',AsyncMock(side_effect=asyncio.CancelledError)):
   with self.assertRaises(asyncio.CancelledError):asyncio.run(run_mqtt(Mock(),'localhost',8883,'user','private',None))
  client.publish.assert_not_awaited()

 def test_factory_roster_channels_receive_real_registry_reports(self):
  from gateway.fleet_ota.local import initialize
  from cryptography.hazmat.primitives import serialization
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'public.pem';key=ec.generate_private_key(ec.SECP256R1())
   path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
   targets=[{'factory_id':f'HC-00000000000{node}','role':node,'model':'HC-S1' if node==1 else 'HC-A1','node_id':node,'parent_id':0 if node==1 else 1,'factory_secret':'ab'*32,'key':'cd'*32,'setup':'private-setup'} for node in (1,2)]
   registry,manager=initialize(Path(d)/'data',{'release_public_key':str(path),'targets':targets})
   registry.db.execute("UPDATE registered_nodes SET boot_id='9' WHERE node_id=2")
   registry.report_state(2,{'node_id':2,'boot_id':9,'config_rev':1,'state_seq':1,'channels':[{'number':n,'relay_state':False,'ct_valid':False,'current_rms_a':None,'fault_flags':0} for n in (1,2,3)]})
   rows=registry.rows('SELECT relay_state FROM channel_states')
   self.assertEqual([r['relay_state'] for r in rows],[0,0,0]);registry.close()

 def test_legacy_ca_option_keeps_certificate_and_hostname_checks(self):
  import asyncio,ssl
  from unittest.mock import AsyncMock,Mock,patch
  from gateway.fleet_ota.local import serve
  for legacy in (False,True):
   registry=Mock();transport=AsyncMock()
   with tempfile.TemporaryDirectory() as d,patch('gateway.fleet_ota.local.initialize',return_value=(registry,Mock())),patch('gateway.fleet_ota.local.Bridge'),patch('gateway.fleet_ota.local.run_mqtt',transport):
    asyncio.run(serve(d,{'mqtt':{'host':'localhost','port':8883,'username':'user','password':'private','ca':None,'legacy_ca':legacy}}))
   context=transport.call_args.kwargs['tls_context']
   self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(context.check_hostname)
   if legacy:self.assertFalse(context.verify_flags&ssl.VERIFY_X509_STRICT)
   registry.close.assert_called_once()

 def test_upload_requires_pinned_target_and_exact_image_version_and_preserves_v2_packet(self):
  with tempfile.TemporaryDirectory() as d:
   registry=Registry(Path(d)/'core.db',b'x'*32)
   private=ec.generate_private_key(ec.SECP256R1())
   manager=LocalOtaManager(registry,Path(d)/'images',private.public_key(),{'node1':{'compatibility_id':'ab'*32,'role':2,'model':'HC-A1','node_id':2}})
   image=bytearray(512);image[0]=0xe9;image[1]=1;image[12]=9
   image[32:36]=(0xabcd5432).to_bytes(4,'little');image[48:54]=b'1.0.1\0';image=bytes(image)
   m=dict(schema=2,role=2,artifact_type=1,flags=0,compatibility_id='ab'*32,version='1.0.1',size=len(image),sha256=hashlib.sha256(image).hexdigest(),min_agent=2,min_bootloader=1,protocol_min=1,protocol_max=1,release_counter=1,security_epoch=0,key_id=key_id(private.public_key()))
   raw=target_header(m);r,s=utils.decode_dss_signature(private.sign(raw,ec.ECDSA(hashes.SHA256())));packet=raw+r.to_bytes(32,'big')+s.to_bytes(32,'big')
   artifact=manager.upload_target('node1',packet,image)
   self.assertEqual(manager.start_payload(artifact,2),packet)
   self.assertEqual(manager.upload_target('node1',packet,image),artifact)
   m['release_counter']=2
   raw2=target_header(m);r,s=utils.decode_dss_signature(private.sign(raw2,ec.ECDSA(hashes.SHA256())))
   with self.assertRaisesRegex(ValueError,'target_metadata_conflict'):
    manager.upload_target('node1',raw2+r.to_bytes(32,'big')+s.to_bytes(32,'big'),image)
   with self.assertRaises(ValueError):manager.upload_target('unknown',packet,image)
   with self.assertRaises(ValueError):manager.upload_target('node1',packet,image+b'x')
   registry.close()

 def test_status_preserves_transfer_and_retry_resumes_with_bounded_timeout(self):
  from gateway.fleet_ota.local import initialize
  from cryptography.hazmat.primitives import serialization
  with tempfile.TemporaryDirectory() as d:
   key=ec.generate_private_key(ec.SECP256R1());path=Path(d)/'public.pem'
   path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
   config={'release_public_key':str(path),'targets':[{'factory_id':'HC-000000000001','role':1,'model':'HC-S1','node_id':1,'factory_secret':'ab'*32,'key':'cd'*32,'setup':'private-setup'}]}
   registry,manager=initialize(Path(d)/'data',config)
   image=Path(d)/'image.bin';image.write_bytes(b'x'*512)
   manifest=json.dumps({'model':'HC-S1','version':'1.0.1','size':512,'sha256':'ab'*32})
   registry.db.execute("INSERT INTO firmware_artifacts VALUES('fw','HC-S1','1.0.1',512,?,?,?, ?,0)",('ab'*32,manifest,'00'*64,str(image)))
   job=manager.create_job('ota-local-operator','local-pilot','fw',[1])
   manager.update(job['job_id'],1,'TRANSFERRING',offset=192)
   registry.close()
   registry,manager=initialize(Path(d)/'data',config)
   row=manager.job('ota-local-operator',job['job_id'])['targets'][0]
   self.assertEqual((row['status'],row['offset']),('TRANSFERRING',192))
   from types import SimpleNamespace
   from gateway.core_v1.protocol import MessageType
   from unittest.mock import Mock
   import struct
   now=[1000.0];registry.clock=lambda:now[0]
   manager.update(job['job_id'],1,'QUEUED',offset=0)
   bridge=SimpleNamespace(route=lambda _:1,windows={1:True},frame=Mock(return_value=b'wire'))
   self.assertEqual(len(manager.outgoing(bridge)),1)
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',192,0)))
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['offset'],192)
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',192,0)))
   self.assertEqual(len(manager.outgoing(bridge)),2)
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',0,0)))
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',384,0)))
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['offset'],384)
   now[0]+=manager.retry_interval-.001;self.assertEqual(manager.outgoing(bridge),[])
   now[0]+=.002;self.assertEqual(len(manager.outgoing(bridge)),1)
   from gateway.core_v1.registry import CoreError
   with self.assertRaises(CoreError):
    manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',513,0)))
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',512,0)))
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['offset'],512)
   self.assertEqual(len(manager.outgoing(bridge)),1)
   for _ in range(manager.retry_attempts):now[0]+=manager.retry_interval+.001;manager.outgoing(bridge)
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['status'],'VERIFYING')
   registry.db.execute("UPDATE registered_nodes SET boot_id='9' WHERE node_id=1")
   self.assertEqual(manager.outgoing(bridge),[])
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['status'],'REBOOTING')
   self.assertNotIn((job['job_id'],1),manager.waiting)
   registry.db.execute("UPDATE ota_targets SET old_boot='9' WHERE job_id=?",(job['job_id'],))
   manager.update(job['job_id'],1,'VERIFYING',offset=512)
   now[0]+=301;manager.outgoing(bridge)
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['reason'],'verification_timeout')
   manager.update(job['job_id'],1,'TRANSFERRING',offset=192);manager.outgoing(bridge)
   for _ in range(manager.retry_attempts):now[0]+=manager.retry_interval+.001;manager.outgoing(bridge)
   row=manager.job('ota-local-operator',job['job_id'])['targets'][0]
   self.assertEqual((row['status'],row['reason']),('FAILED','transfer_timeout'))
   manager.update(job['job_id'],1,'REBOOTING',offset=512)
   now[0]+=299;manager.outgoing(bridge)
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['status'],'REBOOTING')
   now[0]+=2;manager.outgoing(bridge)
   self.assertEqual(manager.job('ota-local-operator',job['job_id'])['targets'][0]['reason'],'health_timeout')
   manager.update(job['job_id'],1,'QUEUED',offset=0);manager.outgoing(bridge)
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_PROGRESS,payload=struct.pack('<IB',0xffffffff,2)))
   row=manager.job('ota-local-operator',job['job_id'])['targets'][0]
   self.assertEqual((row['status'],row['offset'],row['reason']),('FAILED',0,'device_verification_failed'))
   manager.update(job['job_id'],1,'FAILED',offset=512,reason='transfer_timeout')
   registry.db.execute("UPDATE ota_targets SET old_boot='8' WHERE job_id=?",(job['job_id'],))
   payload=b'1.0.1'.ljust(16,b'\0')+bytes.fromhex('ab'*32)+b'\x01'
   with self.assertRaises(CoreError):manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_RESULT,boot_id=8,payload=payload))
   with self.assertRaises(CoreError):manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_RESULT,boot_id=9,payload=payload[:16]+b'h'*32+b'\x01'))
   manager.receive(SimpleNamespace(source=1,type=MessageType.OTA_RESULT,boot_id=9,payload=payload))
   row=manager.job('ota-local-operator',job['job_id'])['targets'][0]
   self.assertEqual((row['status'],row['reason']),('SUCCEEDED','late_boot_confirmation'))
   registry.close()
