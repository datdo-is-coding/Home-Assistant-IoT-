"""Bounded local-ASR voice ingress; all actuation uses the Core command queue.

Each SubBox uses a unique Member bearer token, pinned TLS and a server-side
node-to-user mapping. Source IDs are enrolled radio identities, never names.
"""
import asyncio
import math
import re
import time
import unicodedata
from aiohttp import web
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
                 'o cam': 'outlet', 'outlet': 'outlet'}
        devices = self.registry.rows(
            "SELECT d.device_id,d.name,d.kind FROM devices d JOIN device_bindings b USING(device_id) "
            "JOIN channels c USING(channel_id) JOIN registered_nodes n USING(node_id) "
            "JOIN node_assignments a USING(node_id) WHERE d.home_id=? AND a.room_id=? "
            "AND a.parent_id=? AND a.active=1 AND b.active=1 AND n.registration='REGISTERED'",
            (scope['home_id'], scope['room_id'], parent))
        matches = [d for d in devices if normalize(d['name']) == target or d['kind'] == kinds.get(target)]
        require(len(matches) == 1, 'voice_ambiguous' if matches else 'voice_no_target', 409)
        return matches[0]['device_id'], action in ('bat', 'turn on')

    def request_key(self, parent, request_id):
        require(isinstance(request_id, str) and re.fullmatch('[a-f0-9]{32}', request_id), 'voice_request_id')
        return f'voice:{parent}:{request_id}'

    def submit(self, user, parent, source, text, request_id):
        device, desired = self.resolve(user, parent, source, text)
        return self.registry.command(user, device, desired, self.request_key(parent, request_id), ttl=5)

    def result(self, command):
        status = command['status']
        if status == 'APPLIED':
            verify, reply = 'success', 'Đã thực hiện lệnh.'
        elif status in ('RECEIVED', 'ACCEPTED') and command['expires'] > self.registry.clock():
            verify, reply = 'pending', 'Đang chờ thiết bị xác nhận.'
        elif status in ('RECEIVED', 'ACCEPTED', 'TIMEOUT'):
            verify, reply = 'timeout', 'Chưa xác nhận được trạng thái thiết bị.'
        else:
            verify, reply = 'failed', 'Thiết bị chưa thực hiện được lệnh.'
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
                inference = asyncio.create_task(asyncio.to_thread(self.asr.transcribe_with_confidence, samples, 16000))
                try:
                    text, confidence = await asyncio.shield(inference)
                except asyncio.CancelledError:
                    await inference
                    raise
            require(not ws.closed and time.monotonic() - started < self.MAX_AGE, 'expired', 409)
            require(type(confidence) in (int, float) and math.isfinite(confidence) and confidence >= .7,
                    'low_confidence', 409)
            await ws.send_json(dict(type='transcript', text=text, confidence=confidence, accepted=True))
            command = self.submit(user, parent, source, text, request_id)
            await self.wait_result(ws, user, parent, source, command)
        except CoreError as error:
            if not ws.closed:
                try:
                    await ws.send_json(dict(type='command_result', verify=error.code,
                                           voice_reply='Chưa thực hiện lệnh. Vui lòng nói lại rõ tên thiết bị.', follow_up=False))
                except (ConnectionResetError, RuntimeError):
                    pass
        except (RuntimeError, ValueError, OSError):
            if not ws.closed:
                try:
                    await ws.send_json(dict(type='command_result', verify='asr_unavailable', follow_up=False))
                except (ConnectionResetError, RuntimeError):
                    pass

    async def websocket(self, request, user):
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
