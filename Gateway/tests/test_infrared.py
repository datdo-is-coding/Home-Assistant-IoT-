import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gateway.core_v1.registry import Registry, CoreError
from gateway.core_v1.infrared.codec import encode, decode, panasonic_seed, panasonic_climate, nec, relative_panasonic_button
from gateway.core_v1.infrared.service import InfraredService


class InfraredTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Registry(Path(self.tmp.name)/'core.db',b'k'*32)
        self.owner,_=self.r.create_user('Owner');self.home=self.r.create_home(self.owner,'Home');room=self.r.create_room(self.owner,self.home,'Bedroom')
        self.r.add_factory_device('HC-001122334455','SUB_BOX','HC-S1',b's'*32,'setup-code-unique')
        self.r.db.execute("INSERT INTO registered_nodes(node_id,factory_id,home_id,registration,connectivity,boot_id) VALUES(1,'HC-001122334455',?,'REGISTERED','ONLINE','boot')",(self.home,))
        self.r.db.execute('INSERT INTO node_assignments(node_id,room_id,parent_id,primary_subbox) VALUES(1,?,NULL,1)',(room,))
        self.ws=SimpleNamespace(core_token='token',infrared_capabilities={'version':2,'tx':True,'rx':True})
        self.sent=[];self.reply=True;self.prepare_mono=1000;self.capture=None
        async def send(text):
            msg=json.loads(text)
            if msg['type']!='ir_prepare':self.sent.append(msg)
            if self.reply:
                result={'id':msg['id'],'ok':True,'type':'ir_result'}
                if msg['type']=='ir_prepare':result['mono_ms']=self.prepare_mono
                if msg['type']=='ir_learn':
                    code=next(iter(self.s.profiles['panasonic-cwa75c4179']['commands'].values()))
                    result['data']=encode(self.capture or code['pulses'],38000)
                asyncio.get_running_loop().call_soon(self.s.accept,self.ws,result)
        self.ws.send=send
        self.audio=SimpleNamespace(_ws_nodes={'SB001122334455':self.ws},_is_ws_alive=lambda ws:True,_is_token_valid=lambda token,target:token=='token')
        self.core=SimpleNamespace(r=self.r,home=self.home,actor=lambda uid:self.owner if uid=='owner' else uid)
        self.s=InfraredService(self.core,self.audio)

    def tearDown(self):self.r.close();self.tmp.cleanup()
    async def request(self,path,body=None,method='POST',uid='owner'):
        return await self.s.request(uid,method,'/api/v1/ir/'+path,body or {})
    async def saved(self):
        await self.request('test',{'node_id':1,'profile_id':'panasonic-cwa75c4179','idempotency_key':'test_code_123'})
        return await self.request('remotes',{'node_id':1,'profile_id':'panasonic-cwa75c4179','name':'Điều hòa Panasonic','confirmed':True})

    async def test_catalog_codes_are_bounded_and_climate_preserves_model_bits(self):
        for profile in self.s.profiles.values():
            for code in profile['commands'].values():
                restored=decode(encode(code['pulses'],code['frequency']),code['frequency'])
                self.assertTrue(all(abs(a-b)<=5 for a,b in zip(restored,code['pulses'])))
        seed=self.s.profiles['panasonic-cwa75c4179']['panasonic216_seed']
        for mode in ('cool','heat','dry','auto','fan'):
            for power in (False,True):
                data=panasonic_climate(seed,{'power':power,'temperature':26,'mode':mode,'fan':0,'swing':True})
                out=bytes.fromhex(panasonic_seed(data));self.assertEqual(out[13]&1,int(power));self.assertEqual(out[13]&6,0)
                self.assertEqual(out[13]&8,bytes.fromhex(seed)[13]&8)
                self.assertEqual((out[14]>>1)&31,27 if mode=='fan' else 26)
        with self.assertRaises(CoreError):decode('AAAA',38000)
        with self.assertRaises(CoreError):encode([200000]*10,38000)

    async def test_save_requires_real_transmission_and_user_confirmation(self):
        body={'node_id':1,'profile_id':'panasonic-cwa75c4179','name':'AC','confirmed':True}
        with self.assertRaises(CoreError):await self.request('remotes',body)
        remote=await self.saved();self.assertTrue(remote['climate']);self.assertFalse(remote['state_confirmed'])
        test=decode(self.sent[0]['data'],self.sent[0]['frequency']);self.assertEqual(bytes.fromhex(panasonic_seed(test))[13]&1,0)

    async def test_send_is_deduplicated_and_never_reports_appliance_state(self):
        remote=await self.saved();self.sent.clear()
        body={'state':{'power':True,'temperature':24,'mode':'cool','fan':2,'swing':False},'idempotency_key':'send_once_123'}
        first=await self.request('remotes/'+remote['remote_id']+'/send',body)
        second=await self.request('remotes/'+remote['remote_id']+'/send',body)
        self.assertEqual(len(self.sent),1);self.assertEqual(first,second);self.assertFalse(first['state_confirmed'])
        with self.assertRaises(CoreError):await self.request('remotes/'+remote['remote_id']+'/send',{**body,'key':'off'})

    async def test_wrong_socket_and_offline_firmware_cannot_claim_success(self):
        remote=await self.saved();self.ws.infrared_capabilities={}
        with self.assertRaises(CoreError):await self.request('remotes/'+remote['remote_id']+'/send',{'key':'off','idempotency_key':'not_supported'})
        self.assertEqual(len(self.sent),1)
        with self.assertRaises(CoreError):await self.request('bootstrap',method='GET',uid='stranger')
        future=asyncio.get_running_loop().create_future();self.s.pending['job']=(self.ws,future)
        self.s.accept(object(),{'id':'job','ok':True});self.assertFalse(future.done());future.cancel()

    async def test_learning_keeps_full_frame_and_delete_removes_codes(self):
        remote=await self.request('remotes',{'node_id':1,'profile_id':'learned','category':'air_conditioner','name':'Điều hòa Nhật'})
        result=await self.request('remotes/'+remote['remote_id']+'/learn',{'key':'off','label':'Tắt'})
        self.assertTrue(result['climate']);self.assertEqual(result['buttons'],[{'key':'off','label':'Tắt'}])
        await self.request('remotes/'+remote['remote_id'],method='DELETE')
        self.assertEqual(self.r.db.execute('SELECT count(*) FROM ir_learned').fetchone()[0],0)

    async def test_transmit_only_and_bad_freshness_reply_never_send_or_learn(self):
        self.ws.infrared_capabilities['rx']=False
        with self.assertRaises(CoreError):
            await self.request('remotes',{'node_id':1,'profile_id':'learned','category':'air_conditioner','name':'AC'})
        self.prepare_mono=None
        body={'node_id':1,'profile_id':'panasonic-cwa75c4179','idempotency_key':'bad_freshness_123'}
        with self.assertRaises(CoreError):await self.request('test',body)
        self.assertEqual(self.sent,[])
        self.prepare_mono=1000
        with self.assertRaises(CoreError):await self.request('test',body)
        self.assertEqual(self.sent,[])
        self.assertEqual(self.s.pending,{})

    async def test_receiver_is_explicit_and_learned_absolute_states_use_exact_codes(self):
        self.ws.infrared_capabilities.update(rx=False,rx_supported=True)
        self.assertFalse((await self.request('bootstrap',method='GET'))['subboxes'][0]['rx'])
        result=await self.request('receivers/1',{'enabled':True})
        self.assertTrue(result['subboxes'][0]['rx']);self.assertEqual(self.sent,[])
        remote=await self.request('remotes',{'node_id':1,'profile_id':'learned','category':'air_conditioner','name':'Máy lạnh'})
        codes={key:nec(16,command) for key,command in (('on',1),('off',2),('temp_26',3))}
        for key,pulses in codes.items():
            self.capture=pulses
            remote=await self.request('remotes/'+remote['remote_id']+'/learn',{'key':key,'label':key})
        self.assertTrue(remote['climate']);self.assertFalse(remote['full_climate']);self.assertEqual(remote['temperatures'],[26])
        for i,(patch,key) in enumerate((({'power':True},'on'),({'power':False},'off'),({'temperature':26},'temp_26'))):
            await self.request('remotes/'+remote['remote_id']+'/send',{'state':patch,'idempotency_key':'absolute_state_'+str(i)})
            self.assertEqual(decode(self.sent[-1]['data'],38000),codes[key])
        sent=len(self.sent)
        with self.assertRaises(CoreError):await self.request('remotes/'+remote['remote_id']+'/send',{'state':{'temperature':25},'idempotency_key':'missing_25'})
        self.assertEqual(len(self.sent),sent)

    async def test_relative_button_cannot_be_learned_as_an_absolute_temperature(self):
        remote=await self.request('remotes',{'node_id':1,'profile_id':'learned','category':'air_conditioner','name':'AC'})
        self.capture=self.s.profiles['panasonic-a75c4187']['commands']['tmp_up']['pulses']
        self.assertEqual(relative_panasonic_button(self.capture),'temperature_up')
        with self.assertRaises(CoreError) as error:
            await self.request('remotes/'+remote['remote_id']+'/learn',{'key':'temp_26','label':'26°C'})
        self.assertEqual(error.exception.code,'ir_relative_code')
        self.assertEqual(self.r.db.execute('SELECT count(*) FROM ir_learned').fetchone()[0],0)

    async def test_member_can_control_but_cannot_change_receiver_or_voice_names(self):
        remote=await self.saved();member,_=self.r.create_user('Member');self.r.add_member(self.owner,self.home,member,'Member')
        with self.assertRaises(CoreError):await self.s.for_user(member,'POST','/api/v1/ir/receivers/1',{'enabled':True})
        with self.assertRaises(CoreError):await self.s.for_user(member,'POST','/api/v1/ir/remotes/'+remote['remote_id']+'/configure',{'name':'Changed','aliases':['Changed']})
        result=await self.s.for_user(member,'POST','/api/v1/ir/remotes/'+remote['remote_id']+'/send',{'state':{'power':True,'temperature':24},'idempotency_key':'member_control'})
        self.assertEqual(result['status'],'sent')
