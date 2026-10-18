"""Home Assistant MQTT projection. Registry remains the only command authority."""
from dataclasses import dataclass
import json
import secrets
import time
from .registry import require

@dataclass(frozen=True)
class Publish:
    topic: str
    payload: bytes
    qos: int = 1
    retain: bool = True

class HomeAssistantAdapter:
    def __init__(self, registry, user_id, home_id):
        self.registry, self.user, self.home = registry, user_id, home_id
        self.root = f'hc/v1/ha/{home_id}'
        self.subscriptions = (f'{self.root}/+/set', 'homeassistant/status')
        self.cache = {}
        self.known = set()
        self.force = True
        self.last_command = {}
        self._authorize()

    def _authorize(self):
        self.registry.authorize(self.user, self.home, ('Member',))

    def outgoing(self, force=False):
        self._authorize()
        snapshot = self.registry.snapshot(self.user, self.home)
        channels = {c['channel_id']: c for c in snapshot['channels']}
        messages = {}
        present = set()
        for device in snapshot['devices']:
            did = device['device_id']
            present.add(did)
            root = f'{self.root}/{did}'
            channel = channels.get(device['channel_id'])
            component = {'light': 'light', 'fan': 'fan'}.get(device['kind'], 'switch')
            for domain in ('light', 'fan', 'switch', 'sensor'):
                suffix = 'current' if domain == 'sensor' else 'relay'
                topic = f'homeassistant/{domain}/hc_{did}/{suffix}/config'
                if not channel or domain not in (component, 'sensor'):
                    messages[topic] = b''
                    continue
                config = dict(name='Current' if domain == 'sensor' else None,
                              unique_id=f'hc_{did}_{suffix}',
                              device=dict(identifiers=[f'hc_{did}'], name=device['name'], manufacturer='Home Competition'),
                              state_topic=f'{root}/{suffix}',
                              availability=[dict(topic='hc/v1/gateway/availability'),
                                            dict(topic=f'{root}/availability')], availability_mode='all')
                if domain == 'sensor':
                    config.update(device_class='current', state_class='measurement', unit_of_measurement='A',
                                  availability=config['availability'] + [dict(topic=f'{root}/current_available')])
                else:
                    config.update(command_topic=f'{root}/set', payload_on='ON', payload_off='OFF', optimistic=False)
                messages[topic] = json.dumps(config, separators=(',', ':')).encode()
            online = channel is not None and channel['availability'] == 'ONLINE'
            messages[f'{root}/availability'] = b'online' if online else b'offline'
            valid = online and channel['ct_valid'] and channel['current_rms_a'] is not None
            messages[f'{root}/current_available'] = b'online' if valid else b'offline'
            messages[f'{root}/current'] = str(channel['current_rms_a']).encode() if valid else b''
            state = channel['relay_state'] if online else None
            messages[f'{root}/relay'] = (b'ON' if state else b'OFF') if state is not None else b''
        for did in self.known - present:
            for domain in ('light', 'fan', 'switch', 'sensor'):
                suffix = 'current' if domain == 'sensor' else 'relay'
                messages[f'homeassistant/{domain}/hc_{did}/{suffix}/config'] = b''
            for suffix in ('availability', 'current_available', 'relay', 'current'):
                messages[f'{self.root}/{did}/{suffix}'] = b''
        result = [Publish(topic, payload) for topic, payload in messages.items()
                  if force or self.force or self.cache.get(topic) != payload]
        self.known, self.cache, self.force = present, messages, False
        return result

    def receive(self, topic, payload, retained=False):
        self._authorize()
        if topic == 'homeassistant/status':
            if payload == b'online':
                self.force = True
            return None
        require(not retained, 'retained_command', 400)
        require(isinstance(payload, bytes) and payload in (b'ON', b'OFF'), 'invalid_ha_command')
        parts = topic.split('/')
        require(len(parts) == 6 and '/'.join(parts[:4]) == self.root and parts[5] == 'set', 'invalid_ha_topic')
        device = parts[4]
        require(any(d['device_id'] == device and d['channel_id'] is not None
                    for d in self.registry.devices(self.user, self.home)), 'not_found', 404)
        now = time.monotonic()
        require(now - self.last_command.get(device, -1) >= .1, 'rate_limited', 429)
        self.last_command[device] = now

        return self.registry.command(self.user, device, payload == b'ON', 'ha-' + secrets.token_hex(16), ttl=5)
