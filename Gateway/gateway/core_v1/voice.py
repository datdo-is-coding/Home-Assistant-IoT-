"""Bounded local-ASR voice ingress; all actuation uses the Core command queue.

Each SubBox uses a unique Member bearer token, pinned TLS and a server-side
node-to-user mapping. Source IDs are enrolled radio identities, never names.
"""
import asyncio
import json
import math
import re
import time
import unicodedata
try:
    from aiohttp import web
except ImportError:
    web = None
from .registry import CoreError, require

def normalize(value):
    value = unicodedata.normalize('NFD', value.casefold().replace('đ', 'd'))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())

class CoreVoice:
    MAX_AUDIO = 16000 * 2 * 6
    MAX_AGE = 15

    def __init__(self, registry, node_users, asr, tts=None):
        self.registry = registry
        self.node_users = {int(node): user for node, user in node_users.items()}
        require(len(set(self.node_users.values())) == len(self.node_users), 'voice_unique_member_required')
        self.asr, self.tts = asr, tts
        self.active = set()
        self.asr_lock = asyncio.Lock()

    def authorize(self, user, parent, source=None):
        require(type(parent) is int and self.node_users.get(parent) == user, 'voice_identity_denied', 403)
        r = self.registry
        p = r.one("SELECT n.home_id,a.room_id FROM registered_nodes n JOIN node_assignments a USING(node_id) "
                  "JOIN factory_devices f USING(factory_id) WHERE n.node_id=? AND n.registration='REGISTERED' "
                  "AND a.active=1 AND a.primary_subbox=1 AND f.product_type='SUB_BOX'", (parent,))
        member = r.one('SELECT role FROM home_members WHERE home_id=? AND user_id=?', (p['home_id'], user))
        require(member['role'] == 'Member', 'voice_member_required', 403)
        if source is not None:
            require(type(source) is int, 'voice_source_denied', 403)
            child = r.one("SELECT n.home_id,a.room_id,a.parent_id FROM registered_nodes n "
                          "JOIN node_assignments a USING(node_id) JOIN factory_devices f USING(factory_id) "
                          "WHERE n.node_id=? AND n.registration='REGISTERED' AND a.active=1 "
                          "AND f.product_type='ACTION_BOX'", (source,))
            require(child['parent_id'] == parent and child['room_id'] == p['room_id'] and
                    child['home_id'] == p['home_id'], 'voice_source_denied', 403)
        return p

    def resolve(self, user, parent, source, text):
        scope = self.authorize(user, parent, source)
        require(isinstance(text, str) and 0 < len(text) <= 200, 'voice_unrecognized')
        phrase = normalize(text)
        match = re.fullmatch(r'(bat|tat|turn on|turn off) (.+)', phrase)
        require(match is not None, 'voice_unrecognized')
        action, target = match.groups()

        kinds = {'den': 'light', 'light': 'light', 'quat': 'fan', 'fan': 'fan',
                 'o cam': 'outlet', 'outlet': 'outlet', 'dieu hoa':'air_conditioner', 'may lanh':'air_conditioner'}
        devices = self.targets(user,parent,source)
        named = [d for d in devices if target in {normalize(n) for n in [d['name'],*d['aliases']]}]
        matches = named or [d for d in devices if d['kind'] == kinds.get(target)]
        require(len(matches) == 1, 'voice_ambiguous' if matches else 'voice_no_target', 409)
        return matches[0]['device_id'], action in ('bat', 'turn on')

    def targets(self,user,parent,source):
        scope=self.authorize(user,parent,source)
        devices=self.registry.rows(
            "SELECT d.device_id,d.name,d.kind,n.node_id,c.number FROM devices d JOIN device_bindings b USING(device_id) "
            "JOIN channels c USING(channel_id) JOIN registered_nodes n USING(node_id) "
            "JOIN node_assignments a USING(node_id) WHERE d.home_id=? AND a.room_id=? "
            "AND a.parent_id=? AND a.active=1 AND b.active=1 AND n.registration='REGISTERED'",
            (scope['home_id'], scope['room_id'], parent))
        has_labels=self.registry.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='core_node_labels'").fetchone()
        for device in devices:
            labels=self.registry.db.execute('SELECT payload FROM core_node_labels WHERE node_id=?',(device['node_id'],)).fetchone() if has_labels else None
            metadata=json.loads(labels[0]) if labels else {}
            if metadata.get('channel_types',{}).get('ch'+str(device['number']))=='air_conditioner':
                device['kind']='air_conditioner'
            aliases=metadata.get('channel_aliases',{}).get('ch'+str(device['number']),[])
            device['aliases']=[a for a in aliases if isinstance(a,str)] if isinstance(aliases,list) else []
        return devices

    def request_key(self, parent, request_id):
        require(isinstance(request_id, str) and re.fullmatch('[a-f0-9]{32}', request_id), 'voice_request_id')
        return f'voice:{parent}:{request_id}'

    def submit(self, user, parent, source, text, request_id):
        device, desired = self.resolve(user, parent, source, text)
        return self.registry.command(user, device, desired, self.request_key(parent, request_id), ttl=5)

    def result(self, command):
        status = command['status']
        device=self.registry.db.execute('SELECT name FROM devices WHERE device_id=? AND home_id=?',
                                        (command['device_id'],command['home_id'])).fetchone()
        label=device['name'] if device else 'thiết bị'
        if status == 'APPLIED':
            verify, reply = 'success', f"Em đã {'bật' if command['desired'] else 'tắt'} {label}."
        elif status in ('RECEIVED', 'ACCEPTED') and command['expires'] > self.registry.clock():
            verify, reply = 'pending', f'Em đang chờ {label} xác nhận.'
        elif status in ('RECEIVED', 'ACCEPTED', 'TIMEOUT'):
            verify, reply = 'timeout', f'Em chưa nhận được xác nhận từ {label}.'
        else:
            verify, reply = 'failed', f'Em chưa xác nhận thực hiện được lệnh với {label}.'
        return dict(type='command_result', verify=verify, voice_reply=reply,
                    command_id=command['command_id'], status=status, follow_up=False)

    async def wait_result(self, ws, user, parent, source, command):
        deadline = time.monotonic() + 5.1
        while command['status'] in ('RECEIVED', 'ACCEPTED') and command['expires'] > self.registry.clock():
            self.authorize(user, parent, source)
            if ws.closed or time.monotonic() >= deadline:
                break
            await asyncio.sleep(.05)
            command = self.registry.get_command(user, command['command_id'])
        if not ws.closed:
            try:
                await ws.send_json(self.result(command))
            except (ConnectionResetError, RuntimeError):
                pass

    async def execute(self, ws, user, parent, source, text, request_id):
        command=self.submit(user,parent,source,text,request_id)
        await self.wait_result(ws,user,parent,source,command)

    async def process(self, ws, user, parent, source, request_id, pcm, started):
        try:
            self.authorize(user, parent, source)
            key = self.request_key(parent, request_id)
            require(time.monotonic() - started < self.MAX_AGE, 'expired', 409)
            old = self.registry.db.execute('SELECT * FROM commands WHERE user_id=? AND idempotency_key=?', (user, key)).fetchone()
            if old:
                await ws.send_json(self.result(dict(old)))
                return
            require(not self.asr_lock.locked(), 'asr_busy', 429)
            require(self.asr is not None, 'asr_unavailable', 503)
            import numpy as np
            samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.

            async with self.asr_lock:
                scoped=getattr(self.asr,'transcribe_scoped',None)
                targets=self.targets(user,parent,source)
                vocabulary=[name for d in targets for name in [d['name'],*d['aliases']]]
                inference = asyncio.create_task(asyncio.to_thread(scoped,samples,16000,vocabulary) if scoped else
                                                asyncio.to_thread(self.asr.transcribe_with_confidence,samples,16000))
                try:
                    text, confidence = await asyncio.shield(inference)
                except asyncio.CancelledError:
                    await inference
                    raise
            require(not ws.closed and time.monotonic() - started < self.MAX_AGE, 'expired', 409)
            require(targets==self.targets(user,parent,source),'configuration_changed',409)
            require(type(confidence) in (int, float) and math.isfinite(confidence) and confidence >= .7,
                    'low_confidence', 409)
            await ws.send_json(dict(type='transcript', text=text, confidence=confidence, accepted=True))
            await self.execute(ws,user,parent,source,text,request_id)
        except CoreError as error:
            if not ws.closed:
                try:
                    await ws.send_json(dict(type='command_result', verify=error.code,
                                           voice_reply={
                                               'voice_no_target':'Em chưa tìm thấy thiết bị này trong phòng. Bạn kiểm tra tên gọi trên app nhé.',
                                               'voice_ambiguous':'Có nhiều thiết bị trùng tên gọi. Bạn nói rõ tên thiết bị nhé.',
                                               'config_pending':'Thiết bị đang đồng bộ cấu hình mới. Bạn chờ một chút rồi thử lại nhé.',
                                               'configuration_changed':'Cấu hình vừa thay đổi. Bạn nói lại lệnh giúp mình nhé.',
                                               'offline':'Thiết bị đang mất kết nối. Bạn kiểm tra nguồn giúp mình nhé.',
                                               'ir_subbox_offline':'SubBox đang mất kết nối. Bạn kiểm tra nguồn giúp em nhé.',
                                               'ir_climate_unsupported':'Remote này chưa có mã đặt nhiệt độ. Bạn học mã trên app giúp em nhé.',
                                               'ir_temperature_not_learned':'Em chưa có mã cho nhiệt độ này. Bạn học mức nhiệt độ đó trên app nhé.',
                                               'ir_power_not_learned':'Em chưa có mã bật hoặc tắt riêng. Bạn học lệnh đó từ remote trên app nhé.',
                                               'ir_ack_unknown':'Em chưa nhận được xác nhận phát hồng ngoại. Bạn kiểm tra điều hòa trước khi thử lại nhé.',
                                               'ir_busy':'Remote đang bận. Bạn thử lại sau một chút nhé.',
                                               'ir_temperature_unknown':'Em chưa biết nhiệt độ đã đặt. Bạn nói rõ mức nhiệt độ mong muốn nhé.',
                                               'ir_temperature_range':'Mức nhiệt độ này ngoài phạm vi từ 16 đến 30 độ. Bạn chọn lại giúp em nhé.',
                                           }.get(error.code,'Em chưa nghe rõ tên thiết bị. Bạn nói lại giúp em nhé.'), follow_up=False))
                except (ConnectionResetError, RuntimeError):
                    pass
        except (RuntimeError, ValueError, OSError):
            if not ws.closed:
                try:
                    await ws.send_json(dict(type='command_result', verify='asr_unavailable', follow_up=False))
                except (ConnectionResetError, RuntimeError):
                    pass

    async def handle_ws(self, request, user=None):
        if web is None:
            raise RuntimeError('aiohttp is required for voice web sockets')
        return await self.websocket(request, user)

    async def websocket(self, request, user):
        if web is None:
            raise RuntimeError('aiohttp is required for voice web sockets')
        header = request.headers.get('X-Device-ID', '')
        require(header.isascii() and header.isdecimal(), 'voice_identity_denied', 403)
        parent = int(header)
        self.authorize(user, parent)
        require(parent not in self.active and len(self.active) < 8, 'voice_busy', 429)
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4096)
        await ws.prepare(request)
        self.active.add(parent)
        pcm, recording, started, source, request_id = bytearray(), False, 0., None, None
        processing = None
        try:
            while not ws.closed:
                try:
                    message = await ws.receive(timeout=7 if recording else 45)
                except asyncio.TimeoutError:
                    break
                if message.type == web.WSMsgType.TEXT:
                    data = message.json()
                    require(isinstance(data, dict))
                    kind = data.get('type')
                    if kind == 'start':
                        if recording or (processing is not None and not processing.done()):
                            await ws.send_json(dict(type='command_result', verify='voice_busy', follow_up=False))
                            continue
                        require(data.get('codec') == 'pcm' and data.get('sample_rate') == 16000, 'audio_format')
                        source = data.get('source_node_id')
                        self.authorize(user, parent, source)
                        request_id = data.get('request_id')
                        self.request_key(parent, request_id)
                        pcm.clear()
                        recording, started = True, time.monotonic()
                        await ws.send_json(dict(type='status', state='recording'))
                    elif kind == 'cancel':
                        recording = False
                        pcm.clear()
                        if processing is not None:
                            processing.cancel()
                    elif kind == 'stop' and recording:
                        recording = False
                        require(320 <= len(pcm) <= self.MAX_AUDIO, 'audio_length')
                        processing = asyncio.create_task(self.process(ws, user, parent, source, request_id, bytes(pcm), started))
                        pcm.clear()
                    elif kind == 'ping':
                        await ws.send_json(dict(type='pong'))
                elif message.type == web.WSMsgType.BINARY:
                    require(recording and len(message.data) % 2 == 0 and
                            len(pcm) + len(message.data) <= self.MAX_AUDIO and time.monotonic() - started < 7,
                            'audio_length')
                    pcm.extend(message.data)
                elif message.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
                    break
        except (CoreError, ValueError, TypeError, ConnectionError):

            pass
        finally:
            try:
                if processing is not None:
                    processing.cancel()
                    await asyncio.gather(processing, return_exceptions=True)
            finally:
                self.active.discard(parent)
                await ws.close()
        return ws
