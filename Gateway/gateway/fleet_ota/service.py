"""Small authenticated fleet OTA service; run with python -m gateway.fleet_ota.service."""
import asyncio
import hashlib
from datetime import timedelta
import json
import os
import re
import secrets
import time
from pathlib import Path

from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .identity import FirebaseAuth, GrantSigner, b64, canonical_json, verify_bytes
from .policy import OtaError, digest, fields, identifier, integer, may_install, require, validate_policy
from .store import FirebaseStore

TERMINAL = {'SUCCEEDED', 'FAILED', 'ROLLED_BACK', 'CANCELLED', 'NEEDS_SERVICE'}
INFLIGHT = {'INSTALLING', 'REBOOTING', 'LOCAL_VALIDATING', 'REPORT_PENDING'}
TRANSITIONS = {
    'OFFERED': {'WAITING_WINDOW', 'PRECHECK', 'DOWNLOADING', 'DEFERRED_OFFLINE', 'BLOCKED_INCOMPATIBLE', 'BLOCKED_POLICY'},
    'WAITING_WINDOW': {'PRECHECK', 'DOWNLOADING', 'DEFERRED_OFFLINE', 'BLOCKED_POLICY'},
    'PRECHECK': {'DOWNLOADING', 'STAGED', 'WAITING_WINDOW', 'DEFERRED_OFFLINE', 'BLOCKED_INCOMPATIBLE', 'BLOCKED_POLICY'},
    'DOWNLOADING': {'STAGED', 'DEFERRED_OFFLINE'},
    'STAGED': {'WAITING_WINDOW', 'PRECHECK', 'DEFERRED_OFFLINE', 'BLOCKED_POLICY'},
    'DEFERRED_OFFLINE': {'PRECHECK', 'DOWNLOADING', 'STAGED', 'WAITING_WINDOW'},
    'BLOCKED_POLICY': {'PRECHECK', 'DOWNLOADING', 'STAGED', 'WAITING_WINDOW'},
    'BLOCKED_INCOMPATIBLE': {'PRECHECK'},
    'INSTALLING': {'REBOOTING', 'REPORT_PENDING'},
    'REBOOTING': {'LOCAL_VALIDATING', 'REPORT_PENDING', 'ROLLED_BACK'},
    'LOCAL_VALIDATING': {'SUCCEEDED', 'ROLLED_BACK', 'REPORT_PENDING'},
    'REPORT_PENDING': {'REBOOTING', 'LOCAL_VALIDATING', 'SUCCEEDED', 'ROLLED_BACK'},
}


def create_app(store, auth, signer, *, clock=time.time, download_signer=None):
    """Inject store/auth/signer explicitly. Production startup below has no fallback."""
    @web.middleware
    async def errors(request, handler):
        try:
            return await handler(request)
        except OtaError as error:
            return web.json_response({'error': error.code}, status=error.status)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({'error': 'invalid_json'}, status=400)

    app = web.Application(middlewares=[errors], client_max_size=128 * 1024)

    async def body(request):
        value = await request.json()
        require(isinstance(value, dict), 'invalid_body', 400)
        return value

    async def principal(request):
        authorization = request.headers.get('Authorization', '')
        require(authorization.startswith('Bearer ') and len(authorization) <= 16384, 'authentication_required', 401)
        try:
            result = await auth(authorization[7:])
            require(bool(result.uid), 'authentication_required', 401)
            return result
        except OtaError:
            raise
        except Exception:
            raise OtaError('invalid_credentials', 401)

    def vendor(who, role='vendor_release_operator'):
        require(not who.gateway_id and role in who.roles, 'forbidden', 403)

    def home_for(root, who, home_id, *, device=False, owner=False):
        identifier(home_id)
        if who.gateway_id:
            require(not owner, 'customer_identity_required', 403)
            require(who.home_id == home_id, 'forbidden', 403)
        home = root.get('homes', {}).get(home_id)
        require(home is not None, 'forbidden', 403)
        if who.gateway_id:
            require(home['gateway_id'] == who.gateway_id and home['tenant_id'] == who.tenant_id and home['owner_epoch'] == who.owner_epoch and not root.get('devices', {}).get(who.gateway_id, {}).get('revoked', True), 'stale_device_identity', 403)
        else:
            require(not device, 'device_identity_required', 403)
            role = home.get('members', {}).get(hashlib.sha256(who.uid.encode()).hexdigest())
            require(role == 'home_owner' if owner else role in {'home_owner', 'home_member'} or 'vendor_release_operator' in who.roles, 'forbidden', 403)
        return home

    def audit(root, who, action, home_id='', reason=''):
        root.setdefault('audit', {})[secrets.token_hex(16)] = {'at': int(clock()), 'actor': who.uid, 'action': action, 'home_id': home_id, 'reason': str(reason)[:500]}

    def lease_for(home, data, now):
        lease = home.get('lease', {})
        require(lease.get('worker_id') == data.get('worker_id') and type(data.get('lease_fence')) is int and lease.get('fence') == data['lease_fence'] and lease.get('expires_at', 0) > now, 'stale_lease')
        return lease

    def job_for(home, data, job_id):
        job = home.get('jobs', {}).get(identifier(job_id))
        require(job is not None and type(data.get('generation')) is int and data['generation'] == job['generation'] and job['owner_epoch'] == home['owner_epoch'], 'stale_job')
        return job

    def target_for(home, job, target_id, root):
        target = job['targets'].get(identifier(target_id))
        require(target is not None, 'unknown_target')
        artifact = root['artifacts'][target['artifact_id']]
        inventory = home.get('inventory', {}).get(target_id)
        require(inventory and inventory['compatibility_id'] == artifact['compatibility_id'], 'inventory_changed')
        return target, artifact

    async def enrollment(request):
        who = await principal(request)
        vendor(who)
        home_id = identifier(request.match_info['home'])
        data = await body(request)
        fields(data, ('tenant_id', 'gateway_id', 'owner_uid', 'public_key_pem'), ('tenant_id', 'gateway_id', 'owner_uid', 'public_key_pem'))
        identifier(data['tenant_id']); identifier(data['gateway_id'])
        require(isinstance(data['owner_uid'], str) and 0 < len(data['owner_uid']) <= 128, 'invalid_owner', 400)
        require(isinstance(data['public_key_pem'], str) and len(data['public_key_pem']) <= 2048, 'invalid_device_key', 400)
        try:
            public_key = serialization.load_pem_public_key(data['public_key_pem'].encode())
            require(isinstance(public_key, ec.EllipticCurvePublicKey) and isinstance(public_key.curve, ec.SECP256R1), 'invalid_device_key', 400)
        except ValueError:
            raise OtaError('invalid_device_key', 400)

        def update(root):
            homes, devices = root.setdefault('homes', {}), root.setdefault('devices', {})
            home = homes.get(home_id)
            existing = devices.get(data['gateway_id'])
            require(not existing or existing['home_id'] == home_id or existing.get('revoked'), 'gateway_already_owned')
            same = home and all(home.get(key) == data[key] for key in ('tenant_id', 'gateway_id', 'owner_uid')) and existing and existing['public_key_pem'] == data['public_key_pem']
            if same:
                return {'home_id': home_id, 'gateway_id': home['gateway_id'], 'owner_epoch': home['owner_epoch']}
            epoch = (home or {}).get('owner_epoch', 0) + 1
            if home:
                devices[home['gateway_id']]['revoked'] = True
                for job in home.get('jobs', {}).values():
                    for target in job['targets'].values():
                        if target['state'] not in TERMINAL | INFLIGHT:
                            target['state'] = 'CANCELLED'
            home = dict(home or {}, tenant_id=data['tenant_id'], gateway_id=data['gateway_id'], owner_uid=data['owner_uid'], members={hashlib.sha256(data['owner_uid'].encode()).hexdigest(): 'home_owner'}, owner_epoch=epoch, policy={'revision': (home or {}).get('policy', {}).get('revision', 0), 'consent': False}, grants={}, lease={}, inventory={})
            homes[home_id] = home
            devices[data['gateway_id']] = dict(data, home_id=home_id, owner_epoch=epoch, revoked=False)
            audit(root, who, 'enrollment', home_id)
            return {'home_id': home_id, 'gateway_id': home['gateway_id'], 'owner_epoch': epoch}
        return web.json_response(await store.transaction(update))

    async def artifact(request):
        who = await principal(request); vendor(who)
        data = await body(request)
        required = ('artifact_id', 'sha256', 'size', 'compatibility_id', 'version', 'storage_key', 'storage_generation', 'signing_key_id')
        fields(data, required + ('signed_target', 'signed_manifest'), required)
        identifier(data['artifact_id']); identifier(data['signing_key_id']); digest(data['sha256']); digest(data['compatibility_id'])
        integer(data['size'], 1, 2**32 - 1)
        require(isinstance(data['version'], str) and 0 < len(data['version']) <= 100, 'invalid_version', 400)
        require(data['storage_key'] == 'sha256/' + data['sha256'] and isinstance(data['storage_generation'], str) and re.fullmatch(r'[0-9]{1,30}', data['storage_generation']) is not None, 'immutable_storage_required', 400)
        box = data.get('signed_target')
        runtime = data.get('signed_manifest')
        require(bool(box) != bool(runtime), 'signed_metadata_required', 400)
        if box:
            require(isinstance(box, str) and re.fullmatch(r'[0-9a-fA-F]{352}', box) is not None, 'invalid_signed_target', 400)
        else:
            require(isinstance(runtime, dict) and bool(runtime.get('signature')) and len(canonical_json(runtime)) <= 65536, 'invalid_signed_manifest', 400)

        def update(root):
            catalog = root.setdefault('artifacts', {})
            current = catalog.get(data['artifact_id'])
            require(current is None or current == data, 'artifact_immutable')
            catalog[data['artifact_id']] = data
            audit(root, who, 'artifact_stage')
            return data
        return web.json_response(await store.transaction(update))

    async def release(request):
        who = await principal(request); vendor(who)
        data = await body(request)
        fields(data, ('release_id', 'artifacts', 'notes', 'dependencies'), ('release_id', 'artifacts', 'dependencies'))
        identifier(data['release_id'])
        ids = data['artifacts']; dependencies = data['dependencies']
        require(isinstance(ids, list) and 0 < len(ids) <= 256 and all(isinstance(item, str) for item in ids) and len(set(ids)) == len(ids), 'invalid_artifacts', 400)
        for item in ids: identifier(item)
        require(isinstance(dependencies, dict) and set(dependencies) <= set(ids), 'invalid_dependencies', 400)
        for item, needs in dependencies.items():
            require(isinstance(needs, list) and all(isinstance(need, str) and need in ids and need != item for need in needs), 'invalid_dependencies', 400)
        visiting, visited = set(), set()
        def visit(item):
            require(item not in visiting, 'cyclic_dependencies', 400)
            if item in visited: return
            visiting.add(item)
            for dependency in dependencies.get(item, []): visit(dependency)
            visiting.remove(item); visited.add(item)
        for item in ids: visit(item)
        require(isinstance(data.get('notes', ''), str) and len(data.get('notes', '')) <= 10000, 'invalid_notes', 400)

        def update(root):
            require(all(item in root.get('artifacts', {}) for item in ids), 'unknown_artifact')
            releases = root.setdefault('releases', {})
            current = releases.get(data['release_id'])
            require(current is None or current['definition'] == data, 'release_immutable')
            if current is None:
                releases[data['release_id']] = {'definition': data, 'approved': False, 'created_by': who.uid}
                audit(root, who, 'release_stage')
            return releases[data['release_id']]
        return web.json_response(await store.transaction(update))

    async def approve(request):
        who = await principal(request); vendor(who, 'vendor_release_approver')
        data = await body(request); fields(data, ('reason',), ('reason',))
        require(isinstance(data['reason'], str) and 0 < len(data['reason']) <= 500, 'approval_reason_required', 400)
        release_id = identifier(request.match_info['release'])
        def update(root):
            value = root.get('releases', {}).get(release_id)
            require(value is not None, 'unknown_release')
            if not value['approved']:
                value.update(approved=True, approved_by=who.uid, approved_at=int(clock()))
                audit(root, who, 'release_approve', reason=data['reason'])
            return value
        return web.json_response(await store.transaction(update))

    async def campaign(request):
        who = await principal(request); vendor(who)
        data = await body(request)
        fields(data, ('campaign_id', 'release_id', 'seed', 'percentage'), ('campaign_id', 'release_id', 'seed', 'percentage'))
        identifier(data['campaign_id']); identifier(data['release_id']); identifier(data['seed']); integer(data['percentage'], 1, 100)
        def update(root):
            require(root.get('releases', {}).get(data['release_id'], {}).get('approved'), 'release_not_approved')
            campaigns = root.setdefault('campaigns', {})
            require(data['campaign_id'] not in campaigns, 'campaign_exists')
            campaigns[data['campaign_id']] = dict(data, state='ACTIVE', created_at=int(clock()))
            audit(root, who, 'campaign_create')
            return campaigns[data['campaign_id']]
        return web.json_response(await store.transaction(update))

    async def campaign_state(request):
        who = await principal(request); vendor(who)
        data = await body(request); fields(data, ('state', 'reason'), ('state', 'reason'))
        require(isinstance(data['state'], str) and data['state'] in {'ACTIVE', 'PAUSED', 'CANCELLED'} and isinstance(data['reason'], str) and 0 < len(data['reason']) <= 500, 'invalid_campaign_state', 400)
        campaign_id = identifier(request.match_info['campaign'])
        def update(root):
            value = root.get('campaigns', {}).get(campaign_id)
            require(value is not None and value['state'] != 'CANCELLED', 'campaign_cancelled_or_missing')
            value['state'] = data['state']
            if data['state'] == 'CANCELLED':
                for home in root.get('homes', {}).values():
                    for job in home.get('jobs', {}).values():
                        if job['campaign_id'] == campaign_id:
                            for target in job['targets'].values():
                                if target['state'] not in TERMINAL | INFLIGHT:
                                    target['state'] = 'CANCELLED'
            audit(root, who, 'campaign_' + data['state'].lower(), reason=data['reason'])
            return value
        return web.json_response(await store.transaction(update))

    async def policy(request):
        who = await principal(request); home_id = request.match_info['home']
        if request.method == 'GET':
            home = await store.read('homes/' + identifier(home_id))
            # Use the same ownership checks as mutations, without loading fleet data.
            device = await store.read('devices/' + identifier(who.gateway_id)) if who.gateway_id else {}
            home_for({'homes': {home_id: home} if home else {}, 'devices': {who.gateway_id: device}}, who, home_id)
            return web.json_response(home['policy'])
        data = validate_policy(await body(request))
        def update(root):
            home = home_for(root, who, home_id, owner=True)
            require(data['revision'] == home['policy'].get('revision', 0) + 1, 'stale_policy')
            home['policy'] = data
            audit(root, who, 'policy_update', home_id)
            return data
        return web.json_response(await store.transaction(update))

    async def inventory(request):
        who = await principal(request); home_id = request.match_info['home']; data = await body(request)
        fields(data, ('targets',), ('targets',))
        require(isinstance(data['targets'], list) and len(data['targets']) <= 256, 'invalid_inventory', 400)
        targets = {}
        for target in data['targets']:
            fields(target, ('target_id', 'compatibility_id', 'boot_id', 'sha256', 'version'), ('target_id', 'compatibility_id', 'boot_id', 'sha256'))
            target_id = identifier(target['target_id']); digest(target['compatibility_id']); digest(target['sha256'])
            require(isinstance(target['boot_id'], str) and 0 < len(target['boot_id']) <= 128 and target_id not in targets, 'invalid_boot_identity', 400)
            require(isinstance(target.get('version', ''), str) and len(target.get('version', '')) <= 100, 'invalid_version', 400)
            targets[target_id] = target
        def update(root):
            home = home_for(root, who, home_id, device=True)
            home['inventory'] = targets
            return {'accepted': len(targets)}
        return web.json_response(await store.transaction(update))

    async def desired(request):
        who = await principal(request); home_id = request.match_info['home']
        def update(root):
            home = home_for(root, who, home_id, device=True)
            jobs = home.setdefault('jobs', {})
            for campaign_id, campaign in root.get('campaigns', {}).items():
                cohort = int.from_bytes(hashlib.sha256((campaign['seed'] + ':' + home_id + ':' + home['gateway_id']).encode()).digest()[:8], 'big') % 100
                if campaign['state'] != 'ACTIVE' or cohort >= campaign['percentage']:
                    continue
                job_id = hashlib.sha256((campaign_id + ':' + home['gateway_id'] + ':' + str(home['owner_epoch'])).encode()).hexdigest()[:32]
                if job_id in jobs: continue
                release = root['releases'][campaign['release_id']]['definition']
                targets = {}
                for target_id, observed in home.get('inventory', {}).items():
                    matches = [root['artifacts'][item] for item in release['artifacts'] if root['artifacts'][item]['compatibility_id'] == observed['compatibility_id']]
                    require(len(matches) <= 1, 'ambiguous_artifacts')
                    if matches and matches[0]['sha256'] != observed['sha256']:
                        selected = matches[0]
                        targets[target_id] = {'artifact_id': selected['artifact_id'], 'state': 'OFFERED', 'previous_boot_id': observed['boot_id'], 'previous_sha256': observed['sha256']}
                if not targets: continue
                required_artifacts = {dependency for target in targets.values() for dependency in release['dependencies'].get(target['artifact_id'], [])}
                satisfied = {target['artifact_id'] for target in targets.values()} | {item for item in release['artifacts'] if any(observed['sha256'] == root['artifacts'][item]['sha256'] and observed['compatibility_id'] == root['artifacts'][item]['compatibility_id'] for observed in home['inventory'].values())}
                require(required_artifacts <= satisfied, 'missing_bundle_dependency')
                generation = home.get('generation', 0) + 1; home['generation'] = generation
                jobs[job_id] = {'job_id': job_id, 'campaign_id': campaign_id, 'release_id': campaign['release_id'], 'gateway_id': home['gateway_id'], 'owner_epoch': home['owner_epoch'], 'generation': generation, 'targets': targets}
            visible = [job for job in jobs.values() if job['owner_epoch'] == home['owner_epoch'] and any(target['state'] not in TERMINAL for target in job['targets'].values())]
            artifact_ids = {target['artifact_id'] for job in visible for target in job['targets'].values()}
            return {'jobs': visible, 'artifacts': {item: root['artifacts'][item] for item in artifact_ids}, 'policy': home['policy'], 'campaigns': {job['campaign_id']: root['campaigns'][job['campaign_id']]['state'] for job in visible}}
        return web.json_response(await store.transaction(update))

    async def updates(request):
        who = await principal(request); home_id = request.match_info['home']
        def read(root):
            home = home_for(root, who, home_id)
            jobs = [job for job in home.get('jobs', {}).values() if job['owner_epoch'] == home['owner_epoch']]
            return {'policy': home['policy'], 'jobs': jobs, 'releases': {job['release_id']: root['releases'][job['release_id']]['definition'] for job in jobs}, 'campaigns': {job['campaign_id']: root['campaigns'][job['campaign_id']]['state'] for job in jobs}}
        return web.json_response(await store.transaction(read))

    async def lease(request):
        who = await principal(request); home_id = request.match_info['home']; data = await body(request)
        fields(data, ('worker_id',), ('worker_id',)); identifier(data['worker_id'])
        now = int(clock())
        def update(root):
            home = home_for(root, who, home_id, device=True); current = home.get('lease', {})
            require(current.get('expires_at', 0) <= now or current.get('worker_id') == data['worker_id'], 'lease_busy')
            fence = current.get('fence', 0) + (0 if current.get('expires_at', 0) > now else 1)
            home['lease'] = {'worker_id': data['worker_id'], 'fence': fence, 'expires_at': now + 120}
            return home['lease']
        return web.json_response(await store.transaction(update))

    async def grant(request):
        who = await principal(request); home_id = request.match_info['home']; data = await body(request)
        fields(data, ('worker_id', 'lease_fence', 'generation', 'target_id', 'policy_revision'), ('worker_id', 'lease_fence', 'generation', 'target_id', 'policy_revision'))
        now = int(clock()); nonce = secrets.token_hex(24)
        def update(root):
            home = home_for(root, who, home_id, device=True); lease_for(home, data, now); job = job_for(home, data, request.match_info['job'])
            target, artifact = target_for(home, job, data['target_id'], root)
            require(type(data['policy_revision']) is int and data['policy_revision'] == home['policy']['revision'], 'stale_policy')
            require(root['campaigns'][job['campaign_id']]['state'] == 'ACTIVE', 'campaign_not_active')
            require(may_install(home['policy'], data['target_id'], now), 'outside_customer_policy')
            require(target['state'] not in TERMINAL | INFLIGHT, 'target_already_started')
            require(not any(item['state'] in INFLIGHT for value in home['jobs'].values() for item in value['targets'].values()), 'target_in_progress')
            release = root['releases'][job['release_id']]['definition']
            for dependency in release['dependencies'].get(target['artifact_id'], []):
                matching = [item for item in job['targets'].values() if item['artifact_id'] == dependency]
                require(all(item['state'] == 'SUCCEEDED' for item in matching), 'dependency_not_succeeded')
                if not matching:
                    expected = root['artifacts'][dependency]
                    require(any(item['sha256'] == expected['sha256'] and item['compatibility_id'] == expected['compatibility_id'] for item in home['inventory'].values()), 'dependency_not_succeeded')
            grants = home.setdefault('grants', {})
            require(not any(not item['consumed'] and item['payload']['expires_at'] > now for item in grants.values()), 'grant_outstanding')
            payload = {'type': 'ota-install-grant-v1', 'tenant_id': home['tenant_id'], 'home_id': home_id, 'gateway_id': home['gateway_id'], 'target_id': data['target_id'], 'artifact_sha256': artifact['sha256'], 'job_id': job['job_id'], 'generation': job['generation'], 'owner_epoch': home['owner_epoch'], 'lease_fence': data['lease_fence'], 'policy_revision': data['policy_revision'], 'nonce': nonce, 'issued_at': now, 'expires_at': now + 120}
            grants[nonce] = {'payload': payload, 'consumed': False}
            audit(root, who, 'install_grant', home_id)
            return payload
        return web.json_response(signer.sign(await store.transaction(update)))

    async def consume(request):
        who = await principal(request); home_id = request.match_info['home']; data = await body(request)
        fields(data, ('worker_id', 'lease_fence', 'generation'), ('worker_id', 'lease_fence', 'generation'))
        now = int(clock())
        def update(root):
            home = home_for(root, who, home_id, device=True); lease_for(home, data, now)
            value = home.get('grants', {}).get(identifier(request.match_info['nonce']))
            require(value and not value['consumed'] and value['payload']['issued_at'] <= now < value['payload']['expires_at'], 'grant_expired_or_consumed')
            payload = value['payload']; job = job_for(home, data, payload['job_id'])
            require(payload['lease_fence'] == data['lease_fence'] and payload['owner_epoch'] == home['owner_epoch'], 'stale_grant')
            target, artifact = target_for(home, job, payload['target_id'], root)
            require(artifact['sha256'] == payload['artifact_sha256'] and target['state'] not in TERMINAL | INFLIGHT, 'grant_target_changed')
            require(not any(item['state'] in INFLIGHT for value in home['jobs'].values() for item in value['targets'].values()), 'target_in_progress')
            value['consumed'] = True; value['consumed_at'] = now
            target.update(state='INSTALLING', install_nonce=payload['nonce'], started_at=now, policy_revision=payload['policy_revision'])
            return {'state': 'INSTALLING', 'nonce': payload['nonce']}
        return web.json_response(await store.transaction(update))

    async def report(request):
        who = await principal(request); home_id = request.match_info['home']; data = await body(request)
        fields(data, ('worker_id', 'lease_fence', 'generation', 'target_id', 'state', 'boot_id', 'sha256', 'version', 'health', 'reason'), ('worker_id', 'lease_fence', 'generation', 'target_id', 'state'))
        require(isinstance(data['state'], str), 'invalid_state', 400)
        require(isinstance(data.get('reason', ''), str) and len(data.get('reason', '')) <= 500, 'invalid_reason', 400)
        for key in ('boot_id', 'sha256', 'version'):
            require(key not in data or isinstance(data[key], str) and len(data[key]) <= 128, 'invalid_evidence', 400)
        now = int(clock())
        def update(root):
            home = home_for(root, who, home_id, device=True); lease_for(home, data, now); job = job_for(home, data, request.match_info['job'])
            target = job['targets'].get(identifier(data['target_id'])); require(target is not None, 'unknown_target')
            artifact = root['artifacts'][target['artifact_id']]
            state, previous = data['state'], target['state']
            evidence = {key: data[key] for key in ('boot_id', 'sha256', 'version', 'health', 'reason') if key in data}
            if state == previous:
                require(evidence == target.get('evidence', {}), 'conflicting_duplicate_report')
                return target
            require(previous not in TERMINAL and state != 'INSTALLING' and (state in TRANSITIONS.get(previous, set()) or state in {'FAILED', 'CANCELLED', 'NEEDS_SERVICE'}), 'invalid_transition')
            if state == 'SUCCEEDED':
                require(bool(target.get('install_nonce')) and data.get('boot_id') and data['boot_id'] != target['previous_boot_id'] and data.get('sha256') == artifact['sha256'] and data.get('version') == artifact['version'] and data.get('health') is True, 'success_evidence_required')
            if state == 'ROLLED_BACK':
                require(bool(target.get('install_nonce')) and data.get('boot_id') and data['boot_id'] != target['previous_boot_id'] and data.get('sha256') == target['previous_sha256'] and data.get('health') is True, 'rollback_evidence_required')
            if previous in INFLIGHT and state == 'CANCELLED':
                raise OtaError('cannot_cancel_inflight')
            target.update(state=state, evidence=evidence, reported_at=now)
            outcomes = [item['state'] for value in root['homes'].values() for other in value.get('jobs', {}).values() if other['campaign_id'] == job['campaign_id'] for item in other['targets'].values() if item['state'] in {'SUCCEEDED', 'FAILED', 'ROLLED_BACK', 'NEEDS_SERVICE'}]
            failure_threshold = len(outcomes) >= 20 and sum(result != 'SUCCEEDED' for result in outcomes) / len(outcomes) > 0.01
            if failure_threshold or state in {'ROLLED_BACK', 'NEEDS_SERVICE'} or data.get('reason') in {'brick', 'unexpected_relay', 'signature_violation', 'compatibility_violation'}:
                root['campaigns'][job['campaign_id']]['state'] = 'PAUSED'
                audit(root, who, 'campaign_auto_pause', home_id, data.get('reason', state))
            return target
        return web.json_response(await store.transaction(update))

    async def challenge(request):
        data = await body(request); fields(data, ('gateway_id',), ('gateway_id',)); gateway_id = identifier(data['gateway_id'])
        now = int(clock()); nonce = secrets.token_hex(24)
        def update(root):
            device = root.get('devices', {}).get(gateway_id)
            require(device and not device['revoked'], 'unknown_device', 401)
            require(device.get('challenge', {}).get('issued_at', 0) < now, 'challenge_rate_limited', 429)
            payload = {'type': 'ota-device-proof-v1', 'gateway_id': gateway_id, 'home_id': device['home_id'], 'tenant_id': device['tenant_id'], 'owner_epoch': device['owner_epoch'], 'nonce': nonce, 'issued_at': now, 'expires_at': now + 120}
            device['challenge'] = payload
            return {'nonce': nonce, 'message': b64(canonical_json(payload)), 'expires_at': now + 120}
        return web.json_response(await store.transaction(update))

    async def device_token(request):
        data = await body(request); fields(data, ('gateway_id', 'nonce', 'signature'), ('gateway_id', 'nonce', 'signature')); gateway_id = identifier(data['gateway_id'])
        now = int(clock())
        def update(root):
            device = root.get('devices', {}).get(gateway_id)
            require(device and not device['revoked'], 'unknown_device', 401)
            value = device.get('challenge')
            require(value and value['nonce'] == data['nonce'] and now < value['expires_at'], 'challenge_expired_or_consumed')
            try:
                verify_bytes(canonical_json(value), data['signature'], serialization.load_pem_public_key(device['public_key_pem'].encode()))
            except ValueError:
                raise OtaError('invalid_device_proof', 401)
            del device['challenge']
            return {key: device[key] for key in ('gateway_id', 'home_id', 'tenant_id', 'owner_epoch')}
        identity = await store.transaction(update)
        return web.json_response({'access_token': signer.device_token(identity, now), 'token_type': 'Bearer', 'expires_in': 900})

    async def download(request):
        who = await principal(request); home_id = request.match_info['home']
        artifact_id = identifier(request.match_info['artifact'])
        def authorize(root):
            home = home_for(root, who, home_id, device=True)
            require(any(job['owner_epoch'] == home['owner_epoch'] and root['campaigns'][job['campaign_id']]['state'] != 'CANCELLED' and any(target['artifact_id'] == artifact_id for target in job['targets'].values()) for job in home.get('jobs', {}).values()), 'artifact_not_assigned', 403)
            return root['artifacts'][artifact_id]
        artifact = await store.transaction(authorize)
        require(download_signer is not None, 'download_unavailable', 503)
        try:
            url = await download_signer(artifact)
        except Exception:
            raise OtaError('download_unavailable', 503)
        return web.json_response({'url': url, 'expires_in': 900, 'sha256': artifact['sha256'], 'size': artifact['size'], 'storage_generation': artifact['storage_generation']})

    async def grant_key(request):
        return web.json_response({'key_id': signer.key_id, 'algorithm': 'ES256', 'public_key_pem': signer.public_pem()})

    async def health(request):
        return web.json_response({'status': 'ok'})

    app.add_routes([
        web.get('/healthz', health), web.get('/v1/grant-key', grant_key),
        web.post('/v1/device-challenges', challenge), web.post('/v1/device-token', device_token),
        web.post('/v1/homes/{home}/enrollment', enrollment), web.post('/v1/artifacts', artifact),
        web.post('/v1/releases', release), web.post('/v1/releases/{release}/approve', approve),
        web.post('/v1/campaigns', campaign), web.post('/v1/campaigns/{campaign}/state', campaign_state),
        web.get('/v1/homes/{home}/policy', policy), web.get('/v1/homes/{home}/updates', updates), web.put('/v1/homes/{home}/policy', policy),
        web.put('/v1/homes/{home}/inventory', inventory), web.get('/v1/homes/{home}/desired', desired),
        web.post('/v1/homes/{home}/lease', lease), web.get('/v1/homes/{home}/artifacts/{artifact}/download', download), web.post('/v1/homes/{home}/jobs/{job}/grants', grant),
        web.post('/v1/homes/{home}/grants/{nonce}/consume', consume),
        web.post('/v1/homes/{home}/jobs/{job}/reports', report),
    ])
    return app


class GcsDownloadSigner:
    """Use Cloud Run ADC and IAM signBlob; no service-account private key."""

    def __init__(self, client, credentials, bucket, service_account_email):
        self.client, self.credentials = client, credentials
        self.bucket, self.service_account_email = bucket, service_account_email

    async def __call__(self, artifact):
        def generate():
            from google.auth.transport.requests import Request
            if not self.credentials.valid:
                self.credentials.refresh(Request())
            blob = self.client.bucket(self.bucket).blob(artifact['storage_key'], generation=int(artifact['storage_generation']))
            blob.reload(timeout=15)
            require(blob.size == artifact['size'] and blob.metadata and blob.metadata.get('sha256') == artifact['sha256'], 'storage_artifact_mismatch')
            return blob.generate_signed_url(version='v4', expiration=timedelta(seconds=900), method='GET', service_account_email=self.service_account_email, access_token=self.credentials.token, generation=artifact['storage_generation'])
        return await asyncio.to_thread(generate)


def production_app():
    import firebase_admin
    import google.auth
    from google.cloud import storage
    from firebase_admin import db
    project = os.environ['GOOGLE_CLOUD_PROJECT']
    database_url = os.environ['FIREBASE_DATABASE_URL']
    require(database_url.startswith('https://') and (database_url.endswith('.firebasedatabase.app') or database_url.endswith('.firebaseio.com')), 'invalid_database_url', 500)
    pem = Path(os.environ['OTA_GRANT_KEY_FILE']).read_bytes()
    signer = GrantSigner(serialization.load_pem_private_key(pem, password=None), os.environ['OTA_GRANT_KEY_ID'])
    firebase_app = firebase_admin.initialize_app(options={'projectId': project, 'databaseURL': database_url})
    store = FirebaseStore(db.reference('/commercial_ota', app=firebase_app))
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    downloader = GcsDownloadSigner(storage.Client(project=project, credentials=credentials), credentials, os.environ['OTA_ARTIFACT_BUCKET'], os.environ['OTA_SIGNING_SERVICE_ACCOUNT'])
    return create_app(store, FirebaseAuth(firebase_app, signer), signer, download_signer=downloader)


if __name__ == '__main__':
    web.run_app(production_app(), host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
