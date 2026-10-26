"""Validated local-KWS configuration and responses; never dispatches relay commands."""
import asyncio
import copy
import json
import logging
import re
import time

logger = logging.getLogger('kws')
ROOMS = {'BEDROOM', 'LIVING_ROOM', 'KITCHEN'}
QUESTIONS = {'missing_action': 'Bạn muốn bật hay tắt?', 'missing_device': 'Bạn muốn điều khiển đèn hay quạt?',
             'missing_room': 'Bạn muốn điều khiển ở phòng nào?'}


class KwsService:
    def __init__(self, gateway):
        self.gateway = gateway
        self.registry = gateway.registry
        self.max_pending = 16
        self.response_ttl = 15.0
        self._tasks = set()
        self._seen = {}
        self._speakers = {}
        self._synthesis = asyncio.Semaphore(2)
        self._config_lock = asyncio.Lock()
        with self.registry._get_db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS kws_config (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            row = db.execute('SELECT payload FROM kws_config WHERE id=1').fetchone()
        self._config = json.loads(row[0]) if row else {'revision': 0, 'bindings': [], 'sources': [], 'sync': {}}

    def _save(self):
        with self.registry._get_db() as db:
            db.execute('INSERT OR REPLACE INTO kws_config VALUES(1,?)', (json.dumps(self._config),))

    def _identity(self, node_id):
        if not isinstance(node_id, str) or not re.fullmatch(r'AB[0-9A-F]{12}', node_id):
            raise ValueError('invalid_node')
        nodes = self.registry.get_all_nodes()
        node = nodes.get(node_id, {})
        parent = node.get('subbox_id')
        uid = node.get('hardware_uid') or node.get('serial') or node_id[2:]
        version = node.get('desired_config_version', node.get('cfg_version'))
        epoch = node.get('owner_epoch')
        if (node_id in self.registry.get_pending() or node.get('status') not in ('online', 'offline')
                or not isinstance(parent, str) or not re.fullmatch(r'SB[0-9A-F]{12}', parent)
                or nodes.get(parent, {}).get('status') not in ('online', 'offline')
                or uid != node_id[2:] or type(version) is not int or version < 1
                or type(epoch) is not int or epoch < 1):
            raise ValueError('unregistered_identity')
        return dict(node_id=node_id, subbox_id=parent, hardware_uid=uid, config_version=version, owner_epoch=epoch)

    def _current(self, row):
        try:
            identity = self._identity(row.get('node_id'))
            return all(row.get(k) == v for k, v in identity.items()) and (
                'channel' not in row or f"ch{row['channel']}" in self.registry.get_all_nodes()[row['node_id']].get('channels', {}))
        except ValueError:
            return False

    def get_config(self):
        changed = False
        for field in ('bindings', 'sources'):
            valid = [row for row in self._config[field] if self._current(row)]
            changed |= valid != self._config[field]
            self._config[field] = valid
        if changed:
            self._config['revision'] += 1
            self._config['sync'] = {sb: {'revision':self._config['revision'], 'status':'pending'} for sb in self._subboxes()}
            self._save()
        return copy.deepcopy(self._config)

    def _subboxes(self):
        return [nid for nid, node in self.registry.get_all_nodes().items()
                if re.fullmatch(r'SB[0-9A-F]{12}', nid) and node.get('status') in ('online', 'offline')
                and nid not in self.registry.get_pending()]

    async def set_config(self, body):
        async with self._config_lock:
            snapshot = self.get_config()
            if not isinstance(body, dict) or type(body.get('revision')) is not int:
                raise ValueError('revision_required')
            if body['revision'] != snapshot['revision']:
                raise ValueError('revision_conflict')
            new = {'revision': snapshot['revision'] + 1, 'bindings': [], 'sources': [], 'sync': {}}
            for field in ('sources', 'bindings'):
                rows = body.get(field)
                if not isinstance(rows, list) or len(rows) > (32 if field == 'sources' else 6):
                    raise ValueError('invalid_' + field)
                seen = set(); targets = set()
                for row in rows:
                    if not isinstance(row, dict) or row.get('room') not in ROOMS:
                        raise ValueError('invalid_room')
                    identity = self._identity(row.get('node_id'))
                    enriched = {**identity, 'room':row['room']}
                    key = row['node_id']
                    if field == 'bindings':
                        channel = row.get('channel')
                        if type(channel) is not int or channel not in (1, 2, 3) or row.get('device') not in ('LIGHT', 'FAN'):
                            raise ValueError('invalid_binding')
                        if f'ch{channel}' not in self.registry.get_all_nodes()[row['node_id']].get('channels', {}):
                            raise ValueError('unknown_channel')
                        target = (row['node_id'], channel)
                        if target in targets: raise ValueError('duplicate_target')
                        targets.add(target)
                        key = (row['room'], row['device'])
                        enriched.update(channel=channel, device=row['device'])
                    if key in seen: raise ValueError('duplicate_' + field)
                    seen.add(key); new[field].append(enriched)
            if len(json.dumps({'cmd':'KWS_CONFIG', **new}, separators=(',', ':')).encode()) > 16384:
                raise ValueError('config_too_large')
            self._config = new
            self._save()
            await self.sync_config()
            self.gateway.broadcast_event('kws_config', self.get_config())
            return self.get_config()

    async def sync_config(self, subbox=None):
        config = self.get_config()
        if config['revision'] == 0:
            if self._config['sync']:
                self._config['sync'] = {}
                self._save()
            return
        payload = {k:config[k] for k in ('revision','sources','bindings')}
        payload['cmd'] = 'KWS_CONFIG'
        for sb in self._subboxes():
            if subbox is not None and sb != subbox: continue
            self._config['sync'][sb] = {'revision':config['revision'], 'status':'pending'}
            self._save()
            try:
                sent = await self.gateway.mqtt.publish(f'home/subbox/{sb}/command', payload, qos=1, retain=False)
            except Exception:
                logger.exception('KWS config publish failed for %s', sb)
                sent = False
            if not sent:
                self._config['sync'][sb]['status'] = 'offline'
        self._save()

    def _topic_source(self, topic, event):
        parts = topic.split('/')
        if len(parts) == 5 and parts[:2] == ['home','subbox'] and parts[3:] == ['event', event] and parts[2] in self._subboxes():
            return parts[2]
        return None

    async def on_config_ack(self, topic, payload):
        sb = self._topic_source(topic, 'kws_config')
        if (not sb or not isinstance(payload, dict) or type(payload.get('revision')) is not int or payload['revision'] < 1
                or payload['revision'] != self.get_config()['revision'] or payload.get('status') not in ('applied','error')):
            return False
        self._config['sync'][sb] = {'revision':payload['revision'], 'status':payload['status']}
        self._save()
        self.gateway.broadcast_event('kws_config', self.get_config())
        return True

    async def on_result(self, topic, payload):
        sb = self._topic_source(topic, 'kws_result')
        if not sb or not isinstance(payload, dict) or type(payload.get('schema_version')) is not int or payload['schema_version'] != 1:
            return False
        issued = payload.get('issued_at')
        wall_now = time.time()
        if type(issued) is not int or issued < 1600000000 or issued > wall_now + 1 or wall_now - issued >= self.response_ttl:
            return False
        for key in ('session_id','request_id'):
            if type(payload.get(key)) is not int or not 0 < payload[key] <= 0xffffffff: return False
        if (payload.get('status') not in ('success','error','incomplete') or type(payload.get('follow_up')) is not bool
                or not isinstance(payload.get('reason'), str) or not re.fullmatch(r'[a-z_]{1,48}', payload['reason'])):
            return False
        snapshot = self.get_config()
        origin = payload.get('origin_node')
        if not any(row['node_id'] == origin and row['subbox_id'] == sb for row in snapshot['sources']): return False
        if payload['follow_up'] and (payload['status'] != 'incomplete' or payload['reason'] not in QUESTIONS): return False
        if payload['status'] == 'success' or payload.get('target_node'):
            matches = [row for row in snapshot['bindings'] if row['node_id'] == payload.get('target_node')
                       and row['subbox_id'] == payload.get('target_subbox') and type(payload.get('channel')) is int
                       and row['channel'] == payload['channel']]
            if len(matches) != 1: return False
        if payload['status'] == 'success':
            if payload.get('action') not in ('TURN_ON','TURN_OFF') or payload.get('state') != payload['action'][5:]: return False
        now = time.monotonic()
        self._seen = {key:expiry for key,expiry in self._seen.items() if expiry > now}
        key = (sb, origin, payload['session_id'], payload['request_id'])
        if key in self._seen or len(self._seen) >= 2048 or len(self._tasks) >= self.max_pending: return False
        self._seen[key] = now + 120
        remaining = min(self.response_ttl, issued + self.response_ttl - wall_now)
        task = asyncio.create_task(self._respond(sb, copy.deepcopy(payload), now + remaining))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def _reply(self, result):
        if result['status'] == 'incomplete' and result['follow_up']:
            return QUESTIONS[result['reason']]
        if result['status'] == 'success':
            channel = self.registry.get_all_nodes()[result['target_node']]['channels'][f"ch{result['channel']}"]
            name = str(channel.get('name') or 'thiết bị')[:64]
            return f"Relay của {name} đã {'bật' if result['state'] == 'ON' else 'tắt'}."
        return 'Chưa xác nhận được lệnh điều khiển. Bạn hãy thử lại.'

    async def _respond(self, sb, result, deadline):
        lock = self._speakers.setdefault(sb, asyncio.Lock())
        try:
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                async with lock:
                    if not any(row['node_id'] == result['origin_node'] and row['subbox_id'] == sb for row in self.get_config()['sources']): return
                    # Synthesis slots are released before playback, so a slow speaker cannot starve another room.
                    await self.gateway.audio_server.speak_kws(sb, self._reply(result), result, self._synthesis)
        except TimeoutError:
            logger.info('Expired KWS response for %s', sb)
        except Exception:
            logger.exception('KWS response failed for %s', sb)

    async def drain(self):
        if self._tasks: await asyncio.gather(*tuple(self._tasks))

    async def stop(self):
        for task in self._tasks: task.cancel()
        if self._tasks: await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
