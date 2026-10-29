"""Optional Firebase transport for the existing Gateway commissioning lifecycle."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from commissioning_rpc import CommissioningRpc
from commissioning_rules import validate_commissioning_rules

log = logging.getLogger(__name__)
KEY = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def read_config(filename):
    path = Path(filename)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Firebase configuration must be a private regular file (chmod 600)')
    data = json.loads(path.read_text())
    base = urlparse(data['database_url'])
    if (base.scheme != 'https' or not base.hostname or
            not base.hostname.endswith(('.firebasedatabase.app', '.firebaseio.com')) or
            base.path not in ('', '/') or base.query or base.fragment or base.username or base.port):
        raise ValueError('Invalid Firebase database URL')
    if not KEY.fullmatch(data['gateway_id']):
        raise ValueError('Invalid gateway ID')
    users = data['installer_uids']
    if (not isinstance(users, list) or not 1 <= len(users) <= 8 or
            any(not isinstance(uid, str) or not KEY.fullmatch(uid) for uid in users)):
        raise ValueError('Explicit Firebase installer UIDs are required (at most 8)')
    host = data['mqtt_host']
    if (not isinstance(host, str) or not host or '/' in host or re.search(r'\s', host) or
            host.endswith(('.firebasedatabase.app', '.firebaseio.com')) or
            type(data['mqtt_port']) is not int or not 1 <= data['mqtt_port'] <= 65535):
        raise ValueError('Configure the real SubBox MQTT broker')
    if data.get('credential_file'):
        credential = Path(data['credential_file'])
        if credential.is_symlink() or not credential.is_file() or credential.stat().st_mode & 0o077:
            raise ValueError('Firebase credentials must be a private regular file (chmod 600)')
    return data


def device_projection(node_id, node):
    """Whitelist registered metadata; never copy pending setup proofs or keys."""
    if (not isinstance(node_id, str) or re.search(r'[.#$\[\]/\x00-\x1f\x7f]', node_id) or
            not node_id or not isinstance(node, dict) or
            node.get('state') in ('FACTORY_NEW', 'PAIRING', 'REVOKED')):
        return None
    result = {key: node[key] for key in (
        'name', 'room', 'location', 'description', 'board_model', 'board_revision',
        'subbox_id', 'parent_subbox', 'capabilities') if key in node}
    result['firmware_version'] = node.get('fw', node.get('firmware_version', ''))
    result['online'] = node.get('status') == 'online'
    try:
        seen = datetime.fromisoformat(node.get('last_seen', ''))
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        result['last_updated'] = int(seen.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        result['online'] = False
    result['channels'] = {}
    channels = node.get('channels')
    channels = channels if isinstance(channels, dict) else {}
    for number in (1, 2, 3):
        key = f'ch{number}'
        channel = channels.get(key)
        if not isinstance(channel, dict):
            continue
        value = {field: channel[field] for field in ('name', 'device_type') if field in channel}
        state = channel.get('state')
        if type(state) is bool:
            value['state'] = state
        for field in ('voltage', 'current', 'power', 'energy_kwh'):
            measurement = channel.get(field)
            if type(measurement) in (int, float) and 0 <= measurement < float('inf'):
                value[field] = measurement
        result['channels'][key] = value
    return result


class AdminStore:
    def __init__(self, config):
        import firebase_admin
        from firebase_admin import credentials, db
        from google.auth.transport.requests import AuthorizedSession
        credential = (credentials.Certificate(config['credential_file'])
                      if config.get('credential_file') else credentials.ApplicationDefault())
        self.app = firebase_admin.initialize_app(credential,
            {'databaseURL': config['database_url'], 'httpTimeout': 10},
            name='commissioning-' + config['gateway_id'])
        self.root = db.reference('/', app=self.app)
        self.authorized = AuthorizedSession(self.app.credential.get_credential())
        self.rules_url = config['database_url'].rstrip('/') + '/.settings/rules.json'

    async def rules(self):
        def fetch():
            response = self.authorized.get(self.rules_url, timeout=10)
            response.raise_for_status()
            return response.json()
        return await asyncio.to_thread(fetch)

    async def read(self, path):
        return await asyncio.to_thread(self.root.child(path).get)

    async def write(self, path, value):
        reference = self.root.child(path)
        await asyncio.to_thread(reference.delete if value is None else reference.set,
                                *([] if value is None else [value]))

    async def patch(self, updates):
        if updates:
            await asyncio.to_thread(self.root.update, updates)


class FirebaseCommissioningBridge:
    def __init__(self, gateway, store, config, *, dispatcher=None, clock=time.time, core=None):
        self.gateway, self.store, self.config, self.clock = gateway, store, config, clock
        self.core = core
        self.dispatcher = dispatcher or CommissioningRpc(gateway, config['installer_uids'],core=core)
        self.task = None
        self.voice_task = None
        self._granted = False
        self._rules_checked = False
        self._next_status = 0
        self._state_seq = None
        self.ir_tasks = {}
        self.infrared = None

    def status(self, online):
        return {'online': online, 'last_seen': int(self.clock() * 1000),
                'mqtt_host': self.config['mqtt_host'], 'mqtt_port': self.config['mqtt_port']}

    async def tick(self):
        gid = self.config['gateway_id']
        requests = await self.store.read(f'gateway_rpc/{gid}/requests') or {}
        if not self._rules_checked or requests:
            # Recheck before every request batch; idle heartbeats do not download Rules repeatedly.
            validate_commissioning_rules(await self.store.rules())
            self._rules_checked = True
        if not self._granted:
            await self.store.patch({f'gateway_access/{uid}/{gid}': True
                                    for uid in self.config['installer_uids']})
            self._granted = True
        state_seq = (self.core.r.db.execute('SELECT coalesce(max(event_id),0) FROM state_events WHERE home_id=?',(self.core.home,)).fetchone()[0]
                     if self.core else None)
        if self.clock() >= self._next_status or state_seq != self._state_seq:
            updates = {f'gateways/{gid}/status': self.status(True)}
            for node_id, node in self.gateway.registry.get_all_nodes().items():
                projection = device_projection(node_id, node)
                if projection is not None:
                    updates[f'devices/{node_id}'] = projection
            if self.core:
                updates.update({f'devices/{node_id}':value for node_id,value in
                                self.core.projections(self.config['installer_uids'][0]).items()})
            await self.store.patch(updates)
            self._state_seq = state_seq
            self._next_status = self.clock() + 3
        if not isinstance(requests, dict):
            return
        for uid in self.config['installer_uids']:
            pending = requests.get(uid, {})
            if not isinstance(pending, dict):
                continue
            responses = await self.store.read(f'gateway_rpc/{gid}/responses/{uid}') or {}
            responses = responses if isinstance(responses, dict) else {}
            for request_id, envelope in list(pending.items())[:64]:
                if not KEY.fullmatch(request_id) or not isinstance(envelope, dict):
                    continue
                path = f'gateway_rpc/{gid}/responses/{uid}/{request_id}'
                if request_id in responses or await self.store.read(path) is not None:
                    await self.store.write(f'gateway_rpc/{gid}/requests/{uid}/{request_id}', None)
                    continue
                if self.infrared and str(envelope.get('path','')).startswith('/api/v1/ir/'):
                    key=(uid,request_id)
                    if key not in self.ir_tasks and len(self.ir_tasks)<4:
                        task=asyncio.create_task(self._ir_request(uid,request_id,envelope,path))
                        self.ir_tasks[key]=task
                        task.add_done_callback(lambda done,k=key:self.ir_tasks.pop(k,None))
                    continue
                try:
                    too_large = len(json.dumps(envelope, allow_nan=False).encode()) > 16384
                except (ValueError, TypeError):
                    too_large = True
                # Lifecycle calls stay on the MQTT loop; only Firebase I/O uses threads.
                response = ({'request_id': request_id, 'status_code': 413,
                             'body': {'success': False, 'error': 'REQUEST_TOO_LARGE'}}
                            if too_large else await self.dispatcher.dispatch(uid, request_id, envelope))
                response['completed_at'] = int(self.clock() * 1000)
                await self.store.write(path, response)
                await self.store.write(f'gateway_rpc/{gid}/requests/{uid}/{request_id}', None)
            for request_id, response in responses.items():
                if (KEY.fullmatch(request_id) and isinstance(response, dict) and
                        type(response.get('completed_at')) in (int, float) and
                        response['completed_at'] < self.clock() * 1000 - 300000):
                    await self.store.write(f'gateway_rpc/{gid}/responses/{uid}/{request_id}', None)

    async def _ir_request(self, uid, request_id, envelope, path):
        try:
            response=await self.dispatcher.dispatch(uid,request_id,envelope)
            response['completed_at']=int(self.clock()*1000)
            await self.store.write(path,response)
            gid=self.config['gateway_id']
            await self.store.write(f'gateway_rpc/{gid}/requests/{uid}/{request_id}',None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('IR mailbox deferred (%s)',type(exc).__name__)

    async def run(self):
        if self.core and hasattr(self.gateway,'audio_server'):
            self.voice_task=asyncio.create_task(self.core.kws.feedback(self.gateway.audio_server))
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error('Firebase commissioning unavailable (%s)', type(exc).__name__)
                self._next_status = 0
                self._rules_checked = False
                try:
                    await self.store.write(f'gateways/{self.config["gateway_id"]}/status', self.status(False))
                except Exception:
                    pass
                await asyncio.sleep(5)
            await asyncio.sleep(.5)

    async def close(self):
        tasks=list(self.ir_tasks.values())
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        if self.voice_task:
            self.voice_task.cancel()
            await asyncio.gather(self.voice_task,return_exceptions=True)
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.store.write(f'gateways/{self.config["gateway_id"]}/status', self.status(False))
        if self.core:
            self.core.r.close()


def configured_bridge(gateway):
    filename = os.environ.get('HOME_COMPETITION_FIREBASE_CONFIG')
    if not filename:
        return None
    config = read_config(filename)
    core=None
    if config.get('core'):
        from core_v1.firebase_commissioning import CoreCommissioning
        from core_v1.registry import Registry
        from core_v1.release import read_key
        data=Path(config['core']['data_dir'])
        if not (data/'core.db').is_file():
            raise ValueError('Core coordinator registry must already exist')
        registry=Registry(data/'core.db',read_key(data/'master.key'),recover=False)
        core=CoreCommissioning(registry,config['core'],config['installer_uids'])
    bridge=FirebaseCommissioningBridge(gateway, AdminStore(config), config,core=core)
    if core:
        from core_v1.infrared.service import InfraredService
        bridge.infrared=InfraredService(core,getattr(gateway,'audio_server',None))
        core.infrared=bridge.infrared
        bridge.dispatcher.infrared=bridge.infrared
    return bridge


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check Firebase commissioning configuration/Rules without controlling a device')
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    async def check():
        store = AdminStore(read_config(args.config))
        validate_commissioning_rules(await store.rules())
        print('Firebase commissioning credentials and protected Rules verified; no device operation sent.')
    asyncio.run(check())
