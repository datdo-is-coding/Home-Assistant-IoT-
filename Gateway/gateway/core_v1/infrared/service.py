"""Authorized IR remotes over the existing enrolled SubBox WSS connection."""
import asyncio
import hashlib
import json
import re
from pathlib import Path

from ..registry import require, canonical, name, uid as new_id
from .codec import decode, encode, panasonic_climate, panasonic_seed, relative_panasonic_button


class InfraredService:
    def __init__(self, core, audio):
        self.core, self.r, self.audio = core, core.r, audio
        self.profiles = {p['id']: p for p in json.loads((Path(__file__).parent / 'data/catalog.json').read_text())['profiles']}
        self.pending = {}
        self.locks = {}
        self.r.db.executescript('''
          CREATE TABLE IF NOT EXISTS ir_remotes(
            remote_id TEXT PRIMARY KEY, home_id TEXT NOT NULL REFERENCES homes,
            node_id INTEGER NOT NULL REFERENCES registered_nodes,
            name TEXT NOT NULL, category TEXT NOT NULL, profile_id TEXT NOT NULL,
            settings TEXT NOT NULL, seed TEXT, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS ir_learned(
            remote_id TEXT NOT NULL REFERENCES ir_remotes ON DELETE CASCADE,
            key TEXT NOT NULL, label TEXT NOT NULL, frequency INTEGER NOT NULL,
            encoded TEXT NOT NULL, PRIMARY KEY(remote_id,key));
          CREATE TABLE IF NOT EXISTS ir_actions(
            action_id TEXT PRIMARY KEY, home_id TEXT NOT NULL, user_id TEXT NOT NULL,
            node_id INTEGER NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
            target TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created REAL NOT NULL,
            UNIQUE(user_id,request_key));
          CREATE TABLE IF NOT EXISTS ir_receivers(
            node_id INTEGER PRIMARY KEY REFERENCES registered_nodes,
            enabled INTEGER NOT NULL CHECK(enabled IN (0,1)));
        ''')
        if 'aliases' not in {r[1] for r in self.r.db.execute('PRAGMA table_info(ir_remotes)')}:
            self.r.db.execute("ALTER TABLE ir_remotes ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
        # Never retry physical IR after a crash: the appliance may already have acted.
        self.r.db.execute("UPDATE ir_actions SET status='UNKNOWN',result=? WHERE status='PENDING'",
                          (json.dumps({'status':'unknown','message':'Gateway restarted; IR was not resent.'}),))

    def parent(self, node):
        require(type(node) is int, 'ir_subbox')
        row = self.r.one('SELECT n.*,f.product_type,r.name AS room FROM registered_nodes n '
                         'JOIN factory_devices f USING(factory_id) JOIN node_assignments a USING(node_id) '
                         'JOIN rooms r USING(room_id) WHERE n.node_id=? AND a.active=1', (node,))
        require(row['home_id'] == self.core.home and row['registration'] == 'REGISTERED'
                and row['product_type'] == 'SUB_BOX', 'forbidden', 403)
        return row

    def remote(self, identifier):
        row = self.r.one('SELECT * FROM ir_remotes WHERE remote_id=?', (identifier,))
        require(row['home_id'] == self.core.home, 'forbidden', 403)
        self.parent(row['node_id'])
        return row

    def profile(self, identifier):
        require(isinstance(identifier, str) and identifier in self.profiles, 'ir_profile', 404)
        return self.profiles[identifier]

    def view(self, row):
        profile = self.profiles.get(row['profile_id'])
        power_keys={'off','power_off','power_on','power','pwr_sw','on_off','power_onoff','power_toggle'}
        buttons = [{ 'key':key, 'label':v['label']} for key,v in profile['commands'].items() if profile['category']!='air_conditioner' or key in power_keys or relative_panasonic_button(v['pulses']) in ('temperature_up','temperature_down')] if profile else []
        buttons += self.r.rows('SELECT key,label FROM ir_learned WHERE remote_id=?', (row['remote_id'],))
        temperatures=(list(range(16,31)) if row['seed'] else sorted({int(b['key'][5:]) for b in buttons if re.fullmatch(r'temp_(1[6-9]|2[0-9]|30)',b['key'])}))
        return {**{k:row[k] for k in ('remote_id','node_id','name','category','profile_id')},
                'brand':profile['brand'] if profile else 'Remote đã học',
                'model':profile['model'] if profile else '',
                'climate':bool(temperatures), 'full_climate':bool(row['seed']),
                'temperatures':temperatures, 'aliases':json.loads(row['aliases']),
                'can_power_on':bool(row['seed']) or any(b['key'] in ('on','power_on') for b in buttons),
                'can_power_off':bool(row['seed']) or any(b['key'] in ('off','power_off') for b in buttons),
                'requested_state':json.loads(row['settings']),
                'buttons':buttons, 'state_confirmed':False}

    def receiver(self, node, ws):
        configured=self.r.db.execute('SELECT enabled FROM ir_receivers WHERE node_id=?',(node,)).fetchone()
        caps=getattr(ws,'infrared_capabilities',{})
        return bool(caps.get('rx') or (caps.get('rx_supported') and configured and configured[0]))

    def bootstrap(self):
        parents = self.r.rows("SELECT n.node_id FROM registered_nodes n JOIN factory_devices f USING(factory_id) "
                             "WHERE n.home_id=? AND n.registration='REGISTERED' AND f.product_type='SUB_BOX'", (self.core.home,))
        nodes=[]
        for n in parents:
            p=self.parent(n['node_id']);ws=self.socket(p, required=False)
            nodes.append({'node_id':p['node_id'],'name':p['factory_id'],'room':p['room'],
                          'online':ws is not None,'tx':bool(ws and ws.infrared_capabilities.get('tx')),
                          'rx_supported':bool(ws and (ws.infrared_capabilities.get('rx_supported') or ws.infrared_capabilities.get('rx'))),
                          'rx':bool(ws and self.receiver(p['node_id'],ws))})
        profiles=[{k:p[k] for k in ('id','category','brand','model')} |
                  {'climate':bool(p.get('panasonic216_seed'))} for p in self.profiles.values()]
        remotes=[self.view(row) for row in self.r.rows('SELECT * FROM ir_remotes WHERE home_id=? ORDER BY created', (self.core.home,))
                 if self.r.db.execute("SELECT 1 FROM registered_nodes WHERE node_id=? AND registration='REGISTERED'", (row['node_id'],)).fetchone()]
        return {'subboxes':nodes,'profiles':profiles,'remotes':remotes}

    def socket(self, parent, required=True):
        target='SB'+parent['factory_id'][3:]
        ws=self.audio._ws_nodes.get(target) if self.audio else None
        valid=bool(ws and self.audio._is_ws_alive(ws)
                   and self.audio._is_token_valid(getattr(ws,'core_token',None),target))
        if required:require(valid,'ir_subbox_offline',503)
        return ws if valid else None

    def accept(self, ws, message):
        pending=self.pending.get(message.get('id'))
        if pending and pending[0] is ws and not pending[1].done():
            pending[1].set_result(message)

    async def exchange(self, parent, kind, payload):
        ws=self.socket(parent)
        require(self.receiver(parent['node_id'],ws) if kind=='ir_learn' else getattr(ws,'infrared_capabilities',{}).get('tx') is True,
                'ir_receiver_unavailable' if kind=='ir_learn' else 'ir_firmware_required',409)
        lock=self.locks.setdefault(parent['node_id'],asyncio.Lock())
        require(not lock.locked(),'ir_busy',409)
        async with lock:
            async def call(message_type, fields, timeout):
                identifier=new_id('IR-')
                future=asyncio.get_running_loop().create_future()
                self.pending[identifier]=(ws,future)
                try:
                    await asyncio.wait_for(ws.send(json.dumps({'type':message_type,'id':identifier,**fields},separators=(',',':'))),1.0)
                    result=await asyncio.wait_for(future,timeout)
                    self.parent(parent['node_id'])
                    require(self.socket(parent) is ws,'ir_session_changed',409)
                    require(result.get('ok') is True,'ir_'+str(result.get('error','failed'))[:40],409)
                    return identifier,result
                finally:
                    self.pending.pop(identifier,None)
            try:
                # A fresh device nonce/monotonic deadline prevents delayed TCP frames
                # from switching an appliance after the app has already timed out.
                nonce,prepared=await call('ir_prepare',{},.75)
                mono=prepared.get('mono_ms')
                require(type(mono) is int and 0 <= mono < 2**53,'ir_prepare')
                _,result=await call(kind,{**payload,**({'receiver_enabled':True} if kind=='ir_learn' else {}),'prepare_id':nonce,'deadline_ms':mono+2000},10 if kind=='ir_learn' else 3)
                return result
            except asyncio.TimeoutError:
                require(False,'ir_ack_unknown',504)

    async def action(self, user, body, node, target, callback):
        key=body.get('idempotency_key')
        require(isinstance(key,str) and re.fullmatch(r'[A-Za-z0-9_-]{8,128}',key),'idempotency_required')
        fingerprint=hashlib.sha256(canonical(body)).hexdigest()
        prior=self.r.db.execute('SELECT * FROM ir_actions WHERE user_id=? AND request_key=?',(user,key)).fetchone()
        if prior:
            require(prior['fingerprint']==fingerprint,'idempotency_conflict',409)
            require(prior['status']!='PENDING','ir_busy',409)
            result=json.loads(prior['result']);require(result.get('status')=='sent','ir_previous_unknown',409)
            return result
        identifier=new_id('IRA-')
        self.r.db.execute('INSERT INTO ir_actions VALUES(?,?,?,?,?,?,?,?,?,?)',
            (identifier,self.core.home,user,node,key,fingerprint,target,'PENDING',None,self.r.clock()))
        try:
            result=await callback()
            result={'action_id':identifier,**result,'state_confirmed':False}
            self.r.db.execute("UPDATE ir_actions SET status='SENT',result=? WHERE action_id=?",(json.dumps(result),identifier))
            self.r.audit(user,self.core.home,'ir_sent',target)
            return result
        except BaseException:
            self.r.db.execute("UPDATE ir_actions SET status='UNKNOWN',result=? WHERE action_id=?",(json.dumps({'status':'unknown'}),identifier))
            raise

    async def transmit(self, parent, code):
        await self.exchange(parent,'ir_send',{'frequency':code['frequency'],'data':encode(code['pulses'],code['frequency'])})
        return {'status':'sent','message':'Đã phát lệnh hồng ngoại.'}

    async def request(self, uid, method, path, body):
        return await self.for_user(self.core.actor(uid),method,path,body)

    def climate_code(self, remote, patch):
        require(isinstance(patch,dict) and patch and set(patch)<={'power','temperature','mode','fan','swing'},'ir_state')
        settings={**json.loads(remote['settings']),**patch}
        if remote['seed']:
            return {'frequency':36700,'pulses':panasonic_climate(remote['seed'],settings)},settings
        require(set(patch) in ({'power'},{'temperature'},{'power','temperature'}),'ir_climate_unsupported')
        if 'temperature' in patch:
            require(type(patch['temperature']) is int and 16<=patch['temperature']<=30 and patch.get('power',True) is True,'ir_state')
            key='temp_'+str(patch['temperature']);settings['power']=True
        else:
            require(type(patch['power']) is bool,'ir_state');key='on' if patch['power'] else 'off'
        learned=self.r.db.execute('SELECT * FROM ir_learned WHERE remote_id=? AND key IN (?,?) ORDER BY key LIMIT 1',
                (remote['remote_id'],key,'power_'+key if key in ('on','off') else key)).fetchone()
        require(learned is not None,'ir_temperature_not_learned' if key.startswith('temp_') else 'ir_power_not_learned',409)
        return {'frequency':learned['frequency'],'pulses':decode(learned['encoded'],learned['frequency'])},settings

    async def for_user(self, user, method, path, body):
        self.r.authorize(user,self.core.home)
        require(isinstance(body,dict),'invalid_input')
        if method=='GET' and path=='/api/v1/ir/bootstrap' and not body:return self.bootstrap()
        receiver=re.fullmatch(r'/api/v1/ir/receivers/([1-9][0-9]*)',path)
        if method=='POST' and receiver:
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            parent=self.parent(int(receiver[1]));ws=self.socket(parent)
            require(set(body)=={'enabled'} and type(body['enabled']) is bool,'invalid_input')
            require(not body['enabled'] or getattr(ws,'infrared_capabilities',{}).get('rx_supported') or getattr(ws,'infrared_capabilities',{}).get('rx'),'ir_receiver_firmware_required',409)
            self.r.db.execute('INSERT INTO ir_receivers VALUES(?,?) ON CONFLICT(node_id) DO UPDATE SET enabled=excluded.enabled',(parent['node_id'],int(body['enabled'])))
            self.r.audit(user,self.core.home,'ir_receiver_configured',str(parent['node_id']))
            return self.bootstrap()
        if method=='POST' and path=='/api/v1/ir/test':
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            require(set(body)=={'node_id','profile_id','idempotency_key'},'invalid_input')
            p=self.profile(body['profile_id']);parent=self.parent(body['node_id'])
            if p.get('panasonic216_seed'):
                code={'frequency':36700,'pulses':panasonic_climate(p['panasonic216_seed'],{'power':False,'temperature':26,'mode':'cool','fan':0,'swing':False})}
            else:
                candidates=[v for k,v in p['commands'].items() if k in ('off','power_off','power','pwr_sw','on_off','power_onoff','power_toggle')]
                require(candidates,'ir_no_test_button');code=candidates[0]
            return await self.action(user,body,parent['node_id'],'test:'+p['id'],lambda:self.transmit(parent,code))
        if method=='POST' and path=='/api/v1/ir/remotes':
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            require(set(body)<= {'node_id','profile_id','name','category','confirmed','aliases'} and {'node_id','profile_id','name'}<=set(body),'invalid_input')
            parent=self.parent(body['node_id']);profile=None;category=body.get('category','custom')
            require(category in ('air_conditioner','tv','fan','custom'),'ir_category')
            if body['profile_id']=='learned':
                ws=self.socket(parent);require(self.receiver(parent['node_id'],ws),'ir_receiver_unavailable',409)
            if body['profile_id']!='learned':
                profile=self.profile(body['profile_id']);category=profile['category']
                require(body.get('confirmed') is True and self.r.db.execute(
                    "SELECT 1 FROM ir_actions WHERE user_id=? AND node_id=? AND target=? AND status='SENT' AND created>?",
                    (user,parent['node_id'],'test:'+profile['id'],self.r.clock()-300)).fetchone(),'ir_test_required')
            rid=new_id('REMOTE-');settings={'power':False,'temperature':26,'mode':'cool','fan':0,'swing':False}
            aliases=body.get('aliases',[body['name']]);require(isinstance(aliases,list) and len(aliases)<=8,'invalid_voice_aliases')
            self.r.db.execute('INSERT INTO ir_remotes(remote_id,home_id,node_id,name,category,profile_id,settings,seed,created,aliases) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (rid,self.core.home,parent['node_id'],name(body['name']),category,body['profile_id'],json.dumps(settings),profile.get('panasonic216_seed') if profile else None,self.r.clock(),json.dumps([name(a) for a in aliases])))
            self.r.audit(user,self.core.home,'ir_remote_created',rid)
            return self.view(self.remote(rid))
        match=re.fullmatch(r'/api/v1/ir/remotes/(REMOTE-[0-9a-f]{24})(?:/(send|learn|configure))?',path)
        require(match is not None,'endpoint_denied',403)
        remote=self.remote(match[1]);parent=self.parent(remote['node_id'])
        if method=='DELETE' and not match[2] and not body:
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            self.r.db.execute('DELETE FROM ir_remotes WHERE remote_id=?',(remote['remote_id'],));return {'success':True}
        if method=='GET' and not match[2] and not body:return self.view(remote)
        if method=='POST' and match[2]=='configure':
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            require(set(body)=={'name','aliases'} and isinstance(body['aliases'],list) and len(body['aliases'])<=8,'invalid_voice_aliases')
            self.r.db.execute('UPDATE ir_remotes SET name=?,aliases=? WHERE remote_id=?',(name(body['name']),json.dumps([name(a) for a in body['aliases']]),remote['remote_id']))
            return self.view(self.remote(remote['remote_id']))
        if method=='POST' and match[2]=='send':
            require(set(body)<= {'key','state','idempotency_key'} and 'idempotency_key' in body and ('key' in body)!=('state' in body),'invalid_input')
            settings=None
            if 'state' in body:
                code,settings=self.climate_code(remote,body['state'])
            else:
                key=body['key'];require(isinstance(key,str),'invalid_input')
                learned=self.r.db.execute('SELECT * FROM ir_learned WHERE remote_id=? AND key=?',(remote['remote_id'],key)).fetchone()
                if learned:
                    code={'frequency':learned['frequency'],'pulses':decode(learned['encoded'],learned['frequency'])}
                    if key in ('on','off','power_on','power_off') or re.fullmatch(r'temp_(1[6-9]|2[0-9]|30)',key):
                        settings=json.loads(remote['settings'])
                        if key.startswith('temp_'):settings.update(power=True,temperature=int(key[5:]))
                        else:settings['power']=key in ('on','power_on')
                else:
                    profile=self.profile(remote['profile_id']);require(key in profile['commands'],'ir_button',404);code=profile['commands'][key]
            async def send():
                result=await self.transmit(parent,code)
                if settings is not None:self.r.db.execute('UPDATE ir_remotes SET settings=? WHERE remote_id=?',(json.dumps(settings),remote['remote_id']))
                if settings is not None and (remote['seed'] or 'temperature' in body.get('state',{}) or str(body.get('key','')).startswith('temp_')):
                    result['requested_temperature']=settings['temperature']
                return result
            return await self.action(user,body,parent['node_id'],remote['remote_id'],send)
        if method=='POST' and match[2]=='learn':
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            require(set(body)=={'key','label'},'invalid_input')
            key=body['key'];require(isinstance(key,str) and re.fullmatch(r'[a-z0-9_]{1,50}',key),'ir_button')
            label=name(body['label']);result=await self.exchange(parent,'ir_learn',{})
            self.r.authorize(user,self.core.home,('Owner','Installer'))
            pulses=decode(result.get('data'),38000)
            if key in ('on','off','power_on','power_off') or key.startswith('temp_'):
                require(relative_panasonic_button(pulses) is None,'ir_relative_code',409)
            self.r.db.execute('INSERT INTO ir_learned VALUES(?,?,?,?,?) ON CONFLICT(remote_id,key) DO UPDATE SET label=excluded.label,frequency=excluded.frequency,encoded=excluded.encoded',
                (remote['remote_id'],key,label,38000,encode(pulses,38000)))
            seed=panasonic_seed(pulses) if remote['category']=='air_conditioner' else None
            if seed:self.r.db.execute('UPDATE ir_remotes SET seed=? WHERE remote_id=?',(seed,remote['remote_id']))
            return self.view(self.remote(remote['remote_id']))
        require(False,'endpoint_denied',403)
