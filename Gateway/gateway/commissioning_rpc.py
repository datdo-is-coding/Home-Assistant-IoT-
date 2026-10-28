"""Narrow Firebase mailbox adapter for the running Gateway's commissioning flow."""
from collections import OrderedDict
import copy
import hashlib
import json
import re
import time

from device_lifecycle import ClaimError, OperationError


class CommissioningRpc:
    def __init__(self, gateway, allowed_uids, *, clock=time.time, core=None):
        self.gateway = gateway
        self.allowed_uids = frozenset(allowed_uids)
        self.clock = clock
        self._responses = OrderedDict()
        self.core = core

    async def dispatch(self, uid, request_id, envelope):
        """The caller supplies UID from a protected RTDB path, never request data."""
        def response(status, body):
            return {'request_id': request_id, 'status_code': status, 'body': body}

        def error(status, code, message):
            return response(status, {'success': False, 'error': code,
                                     'error_code': code, 'message': message})

        if not isinstance(uid, str) or uid not in self.allowed_uids:
            return error(403, 'ADMIN_REQUIRED', 'Firebase account is not authorized for commissioning')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id):
            return error(400, 'INVALID_REQUEST', 'Invalid request ID')
        try:
            serialized = json.dumps(envelope, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError):
            return error(400, 'INVALID_REQUEST', 'Request must contain valid JSON')
        if len(serialized.encode('utf-8')) > 16384:
            return error(413, 'REQUEST_TOO_LARGE', 'Commissioning request is too large')
        now = self.clock()
        while self._responses and next(iter(self._responses.values()))[0] <= now:
            self._responses.popitem(last=False)
        key = (uid, request_id)
        fingerprint = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
        cached = self._responses.get(key)
        if cached:
            if cached[1] != fingerprint:
                return error(409, 'REQUEST_ID_CONFLICT', 'Request ID was already used with different data')
            return copy.deepcopy(cached[2])

        result = None
        required = {'request_id', 'method', 'path', 'created_at', 'expires_at'}
        if (not isinstance(envelope, dict)
                or not required <= set(envelope) <= required | {'body'}
                or envelope.get('request_id') != request_id
                or not isinstance(envelope.get('body', {}), dict)):
            result = error(400, 'INVALID_REQUEST', 'Invalid commissioning request envelope')
        else:
            created, expires = envelope['created_at'], envelope['expires_at']
            if (any(type(value) not in (int, float) or not 0 < value < 1e15
                    for value in (created, expires))
                    or not 0 < expires - created <= 30000 or created > now * 1000 + 5000):
                result = error(400, 'INVALID_REQUEST', 'Invalid request deadline')
            elif expires <= now * 1000:
                result = error(408, 'REQUEST_EXPIRED', 'Commissioning request expired before processing')

        if result is None:
            method, path, body = envelope['method'], envelope['path'], envelope.get('body', {})
            lifecycle = getattr(self.gateway, 'lifecycle', None)
            if not isinstance(method, str) or not isinstance(path, str):
                result = error(400, 'INVALID_REQUEST', 'Method and path must be strings')
            elif lifecycle is None:
                result = error(503, 'GATEWAY_UNAVAILABLE', 'Lifecycle manager is not ready')
            else:
                user = {'id': 'firebase:' + uid, 'username': 'firebase:' + uid, 'role': 'admin'}
                try:
                    if method == 'GET' and path == '/api/commissioning/context' and not body:
                        result = response(200, self.core.context(uid) if self.core else {'profile':'legacy'})
                    elif self.core and (path.startswith('/api/v1/') or path in ('/api/kws/config','/api/device/update')):
                        result = response(200, self.core.request(uid,method,path,body))
                    elif method == 'GET' and path == '/api/commissioning/candidates' and not body:
                        result = response(200, {'success': True, 'candidates': [
                            candidate.to_api_dict() for candidate in lifecycle.get_candidates(now)]})
                    elif method == 'POST' and path == '/api/commissioning/claims':
                        self._validate_claim(body)
                        request = dict(body, idempotency_key=self._idempotency(uid, request_id, path, body))
                        operation = lifecycle.start_claim(user, request, now)
                        result = response(202, {'success': True, 'operation': operation.to_dict(), **operation.to_dict()})
                    elif method == 'POST' and re.fullmatch(r'/api/devices/[A-Za-z0-9_:-]{1,128}/operations', path):
                        if body.get('kind') != 'identify':
                            result = error(403, 'OPERATION_DENIED', 'Only identify is available through commissioning')
                        else:
                            if set(body) - {'kind', 'idempotency_key'}:
                                raise ValueError('Invalid identify request fields')
                            operation = lifecycle.start_operation(
                                user=user, device_uid=path.split('/')[3], kind='identify',
                                idempotency_key=self._idempotency(uid, request_id, path, body), now_sec=now)
                            result = response(202, {'success': True, 'operation': operation.to_dict(), **operation.to_dict()})
                    elif method == 'GET' and re.fullmatch(r'/api/operations/[A-Za-z0-9_-]{1,128}', path) and not body:
                        operation = lifecycle.get_operation(path.split('/')[3], now_sec=now)
                        if operation is None or operation.requested_by != user['id']:
                            result = error(404, 'OPERATION_NOT_FOUND', 'Operation not found')
                        else:
                            result = response(200, {'success': True, 'operation': operation.to_dict(), **operation.to_dict()})
                    else:
                        result = error(403, 'ENDPOINT_DENIED', 'Endpoint is unavailable through commissioning')
                except (ClaimError, OperationError) as exc:
                    result = error(exc.status_code, exc.error_code, exc.message)
                except (ValueError, TypeError):
                    result = error(400, 'INVALID_REQUEST', 'Invalid commissioning request fields')
                except Exception as exc:
                    if self.core and isinstance(getattr(exc,'code',None),str) and type(getattr(exc,'status',None)) is int:
                        result = error(exc.status,exc.code,str(exc))
                    else:
                        result = error(500, 'GATEWAY_ERROR', 'Gateway could not process commissioning request')

        self._responses[key] = (now + 60, fingerprint, copy.deepcopy(result))
        while len(self._responses) > 256:
            self._responses.popitem(last=False)
        return result

    @staticmethod
    def _idempotency(uid, request_id, path, body):
        logical_key = body.get('idempotency_key', request_id)
        if not isinstance(logical_key, str) or not 0 < len(logical_key) <= 256:
            raise ValueError('Invalid idempotency key')
        return 'firebase:' + hashlib.sha256(json.dumps([uid, path, logical_key]).encode()).hexdigest()

    @staticmethod
    def _validate_claim(body):
        if set(body) - {'candidate_id', 'device_uid', 'subbox_id', 'room_id', 'room',
                        'name', 'channels', 'setup_proof', 'config_revision', 'idempotency_key'}:
            raise ValueError('Invalid claim fields')
        candidate = body.get('candidate_id') or body.get('device_uid')
        if not isinstance(candidate, str) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,128}', candidate):
            raise ValueError('Invalid candidate')
        if body.get('device_uid', candidate) != candidate:
            raise ValueError('Conflicting candidate identifiers')
        for field in ('subbox_id', 'room_id', 'room', 'name', 'setup_proof'):
            if field in body and (not isinstance(body[field], str) or len(body[field]) > 256):
                raise ValueError('Invalid claim text field')
        if 'config_revision' in body and (type(body['config_revision']) is not int or not 0 < body['config_revision'] <= 0xffffffff):
            raise ValueError('Invalid configuration revision')
        channels = body.get('channels', {})
        if not isinstance(channels, dict) or set(channels) - {'ch1', 'ch2', 'ch3'}:
            raise ValueError('Invalid channels')
        for channel in channels.values():
            if not isinstance(channel, dict) or set(channel) - {'type', 'name', 'aliases'}:
                raise ValueError('Invalid channel configuration')
            for field in ('type', 'name'):
                if field in channel and (not isinstance(channel[field], str) or len(channel[field]) > 256):
                    raise ValueError('Invalid channel text field')
            aliases = channel.get('aliases', [])
            if not isinstance(aliases, list) or len(aliases) > 32 or any(not isinstance(alias, str) or len(alias) > 256 for alias in aliases):
                raise ValueError('Invalid channel aliases')
