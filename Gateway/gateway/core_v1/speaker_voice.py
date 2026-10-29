"""Pi voice sessions for already-authenticated enrolled SubBox speakers."""
import asyncio
import json
import logging
import re
import time

from .registry import CoreError, require
from .voice import CoreVoice, normalize
from .infrared.voice import climate_intent

log = logging.getLogger('pi_voice')


class SpeakerVoice(CoreVoice):
    def __init__(self, core, parent, asr, lock):
        self.core = core
        member = 'CONTROL-' + next(iter(core.users.values()))
        super().__init__(core.r, {parent: member}, asr)
        self.user = member
        self.asr_lock = lock
        self.authorize(member, parent)

    def targets(self,user,parent,source):
        devices=super().targets(user,parent,source)
        ir=getattr(self.core,'infrared',None)
        if ir:
            for row in ir.r.rows("SELECT * FROM ir_remotes WHERE home_id=? AND node_id=?",(self.core.home,parent)):
                ir.parent(parent)
                devices.append({'device_id':row['remote_id'],'name':row['name'],'kind':'air_conditioner' if row['category']=='air_conditioner' else 'infrared',
                                'aliases':json.loads(row['aliases']),'settings':row['settings'],'seed':row['seed']})
        return devices

    async def execute(self,ws,user,parent,source,text,request_id):
        ir=getattr(self.core,'infrared',None);intent=climate_intent(text)
        if not ir or not intent:return await super().execute(ws,user,parent,source,text,request_id)
        self.authorize(user,parent,source)
        target,patch,kind=intent
        devices=self.targets(user,parent,source)
        named=[d for d in devices if target in {normalize(n) for n in [d['name'],*d['aliases']]}]
        matching=named or ([d for d in devices if d['kind']=='air_conditioner'] if target in ('dieu hoa','may lanh') else [])
        if not any(d['device_id'].startswith('REMOTE-') for d in matching):
            if kind!='power':require(False,'voice_no_target',409)
            return await super().execute(ws,user,parent,source,text,request_id)
        require(len(matching)==1,'voice_ambiguous',409)
        remote=ir.remote(matching[0]['device_id']);key='voice_'+str(parent)+'_'+request_id
        async def send():
            self.authorize(user,parent,source)
            desired=dict(patch)
            if 'delta' in desired:
                previous=ir.r.db.execute("SELECT result FROM ir_actions WHERE target=? AND status='SENT' ORDER BY created DESC,rowid DESC LIMIT 1",(remote['remote_id'],)).fetchone()
                temperature=json.loads(previous[0]).get('requested_temperature') if previous else None
                require(type(temperature) is int,'ir_temperature_unknown',409)
                desired={'power':True,'temperature':temperature+desired['delta']}
            if 'temperature' in desired:require(type(desired['temperature']) is int and 16<=desired['temperature']<=30,'ir_temperature_range',409)
            code,settings=ir.climate_code(ir.remote(remote['remote_id']),desired)
            result=await ir.transmit(ir.parent(parent),code)
            ir.r.db.execute('UPDATE ir_remotes SET settings=? WHERE remote_id=?',(json.dumps(settings),remote['remote_id']))
            reply=(f"Em đã gửi lệnh đặt {remote['name']} ở {settings['temperature']} độ." if kind!='power' else
                   f"Em đã gửi lệnh {'bật' if settings['power'] else 'tắt'} {remote['name']}.")
            return {**result,'voice_reply':reply,**({'requested_temperature':settings['temperature']} if remote['seed'] or 'temperature' in desired else {})}
        result=await ir.action(user,{'idempotency_key':key,'voice':normalize(text)},parent,remote['remote_id'],send)
        if not ws.closed:await ws.send_json(dict(type='command_result',verify='ack_only',delivery='ir_sent',voice_reply=result['voice_reply'],command_id=result['action_id'],status='SENT',state_confirmed=False,follow_up=False))

    def resolve(self, user, parent, source, text):
        try:
            return super().resolve(user, parent, source, text)
        except CoreError as error:
            if error.code != 'voice_ambiguous':
                raise
        scope = self.authorize(user, parent, source)
        phrase = normalize(text)
        action, target = re.fullmatch(r'(bat|tat|turn on|turn off) (.+)', phrase).groups()
        require(not any(target in {normalize(n) for n in [d['name'],*d['aliases']]}
                        for d in self.targets(user,parent,source)), 'voice_ambiguous', 409)
        role = {'den': 'LIGHT', 'light': 'LIGHT', 'quat': 'FAN', 'fan': 'FAN',
                'o cam': 'OUTLET', 'outlet': 'OUTLET'}.get(target)
        require(role is not None, 'voice_ambiguous', 409)
        config = self.core.kws.stored(scope['home_id'])
        factory = self.registry.one('SELECT factory_id FROM registered_nodes WHERE node_id=?', (parent,))['factory_id']
        own = [s for s in config['sources'] if s['node_id'] == 'SB' + factory[3:]]
        require(len(own) == 1, 'voice_ambiguous', 409)
        bindings = [b for b in config['bindings'] if b['room'] == own[0]['room'] and b['device'] == role]
        require(len(bindings) == 1, 'voice_ambiguous', 409)
        binding = bindings[0]
        device = self.registry.one(
            'SELECT d.device_id FROM devices d JOIN device_bindings b USING(device_id) '
            'JOIN channels c USING(channel_id) JOIN registered_nodes n USING(node_id) '
            'JOIN node_assignments a USING(node_id) WHERE n.factory_id=? AND c.number=? '
            "AND b.active=1 AND a.active=1 AND a.parent_id=? AND a.room_id=? AND d.home_id=? "
            "AND n.registration='REGISTERED' AND d.kind=?",
            ('HC-' + binding['node_id'][2:], binding['channel'], parent, scope['room_id'], scope['home_id'], role.lower()))
        return device['device_id'], action in ('bat', 'turn on')


class SpeakerVoiceSession:
    def __init__(self, server, socket, core, parent, node_id, token):
        self.server, self.socket = server, socket
        self.node_id, self.token, self.parent = node_id, token, parent
        self.voice = SpeakerVoice(core, parent, server.gateway.asr, server._asr_lock)
        self.pcm = bytearray()
        self.recording, self.started = False, 0.
        self.source = self.request = None
        self.processing = None

    @property
    def closed(self):
        return (not self.server._is_ws_alive(self.socket) or
                not self.server._is_token_valid(self.token, self.node_id))

    async def send_json(self, result):
        if result.get('type') == 'command_result':
            result = {**result, 'has_tts': True}
        if result.get('type') == 'transcript':
            log.info('Pi ASR parent=%d text=%r confidence=%.3f', self.parent,
                     result.get('text'), result.get('confidence', 0))
        await self.socket.send(json.dumps(result))
        if result.get('type') == 'command_result':
            log.info('Pi voice parent=%d verify=%s command=%s', self.parent,
                     result.get('verify'), result.get('command_id'))
            reply = result.get('voice_reply') or 'Em chưa xử lý được lệnh. Bạn hãy thử lại nhé.'
            await self.server._send_voice_reply(self.socket, reply, follow_up=False, broadcast=False)

    async def text(self, data):
        kind = data.get('type')
        if kind == 'start':
            require(not self.recording and (self.processing is None or self.processing.done()), 'voice_busy', 429)
            require(data.get('codec') == 'pcm' and data.get('sample_rate') == 16000, 'audio_format')
            source = data.get('source_node_id')
            self.voice.authorize(self.voice.user, self.parent, source)
            request = data.get('request_id')
            self.voice.request_key(self.parent, request)
            self.source, self.request = source, request
            self.pcm.clear()
            self.recording, self.started = True, time.monotonic()
            await self.send_json(dict(type='status', state='recording'))
        elif kind == 'stop' and self.recording:
            self.recording = False
            require(320 <= len(self.pcm) <= self.voice.MAX_AUDIO, 'audio_length')
            self.processing = asyncio.create_task(self.voice.process(
                self, self.voice.user, self.parent, self.source, self.request, bytes(self.pcm), self.started))
            self.pcm.clear()
        elif kind == 'cancel':
            self.recording = False
            self.pcm.clear()
            if self.processing:
                self.processing.cancel()

    def audio(self, data):
        require(not self.closed and self.recording and len(data) % 2 == 0 and
                len(self.pcm) + len(data) <= self.voice.MAX_AUDIO and
                time.monotonic() - self.started < 7, 'audio_length')
        self.pcm.extend(data)

    async def close(self):
        self.recording = False
        self.pcm.clear()
        if self.processing:
            self.processing.cancel()
            await asyncio.gather(self.processing, return_exceptions=True)
