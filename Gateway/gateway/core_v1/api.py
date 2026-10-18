"""Authenticated HTTP/WebSocket management API. No device proof bypass routes."""
import asyncio
from collections import OrderedDict
import json
import sqlite3
import time
from aiohttp import web
from .registry import CoreError, require
from .provisioning import Provisioning

USER = web.RequestKey('user', str)
REGISTRY = web.AppKey('registry', object)
OTA = web.AppKey('ota', object)
VOICE = web.AppKey('voice', object)
SOCKETS = web.AppKey('sockets', set)

def create_app(registry, ota=None, allowed_origin=None, voice=None):
    buckets = OrderedDict()

    @web.middleware
    async def boundary(request, handler):
        try:
            origin=request.headers.get('Origin')
            require(not origin or origin==allowed_origin, 'origin_denied',403)
            identity=request.remote or 'unknown'
            now=time.monotonic()
            tokens,then=buckets.pop(identity,(60.,now))
            tokens=min(60.,tokens+(now-then)*10)
            buckets[identity]=(tokens-1,now)
            while len(buckets)>1024: buckets.popitem(last=False)
            require(tokens>=1,'rate_limited',429)
            if request.path!='/api/v1/health':
                auth=request.headers.get('Authorization','')
                require(auth.startswith('Bearer '),'unauthorized',401)
                request[USER]=registry.authenticate(auth[7:])
            return await handler(request)
        except CoreError as e:
            return web.json_response({'error':{'code':e.code,'message':str(e)}},status=e.status)
        except (KeyError,ValueError,TypeError,json.JSONDecodeError):
            return web.json_response({'error':{'code':'invalid_input','message':'Invalid request fields'}},status=400)
        except sqlite3.IntegrityError:
            return web.json_response({'error':{'code':'conflict','message':'Database constraint rejected the change'}},status=409)
        except web.HTTPException as e:
            return web.json_response({'error':{'code':'http_error','message':e.reason}},status=e.status)

    app=web.Application(middlewares=[boundary],client_max_size=5*1024*1024)
    app[REGISTRY],app[OTA],app[VOICE],app[SOCKETS]=registry,ota,voice,set()
    commissioning=Provisioning(registry)

    async def body(req):
        data=await req.json()
        require(isinstance(data,dict))
        return data

    def home(req):
        value=req.query.get('home_id')
        require(isinstance(value,str) and len(value)<=80)
        return value

    async def health(req):
        return web.json_response({'product':'Home Competition','api_version':1,'database':registry.integrity()})

    async def homes(req):
        if req.method=='GET': return web.json_response({'items':registry.homes(req[USER])})
        d=await body(req)
        return web.json_response({'home_id':registry.create_home(req[USER],d['name'])},status=201)

    async def rooms(req):
        if req.method=='GET': return web.json_response({'items':registry.rooms(req[USER],home(req))})
        d=await body(req)
        return web.json_response({'room_id':registry.create_room(req[USER],d['home_id'],d['name'])},status=201)

    async def nodes(req):
        if 'id' in req.match_info:
            return web.json_response(registry.get_node(req[USER],int(req.match_info['id'])))
        return web.json_response({'items':registry.nodes(req[USER],home(req))})

    async def room_nodes(req):
        r=registry.one('SELECT * FROM rooms WHERE room_id=?',(req.match_info['id'],))
        return web.json_response({'items':[n for n in registry.nodes(req[USER],r['home_id']) if n['room_id']==r['room_id']]})

    async def claim(req):
        d=await body(req)
        return web.json_response(registry.claim(req[USER],d['factory_id'],d['setup_code'],d['room_id'],d.get('parent_id')),status=202)

    async def assign(req):
        d=await body(req)
        return web.json_response(registry.assign(req[USER],int(req.match_info['id']),d['room_id'],d.get('parent_id')),status=202)

    async def provision_prepare(req):
        d=await body(req)
        claim_id=d.pop('claim_id')
        return web.json_response(commissioning.prepare(req[USER],claim_id,**d),status=202)

    async def provision_confirm(req):
        d=await body(req)
        receipt=bytes.fromhex(d['receipt'])
        require(len(receipt) in (78,82),'invalid_packet')
        c=registry.one('SELECT * FROM pairing_claims WHERE nonce=?',(receipt[4:36].hex(),))
        require(c['user_id']==req[USER],'forbidden',403)
        room=registry.one('SELECT home_id FROM rooms WHERE room_id=?',(c['room_id'],))
        registry.authorize(req[USER],room['home_id'],('Owner','Installer'))
        node=commissioning.accept_receipt(receipt)
        return web.json_response({'status':'REGISTERED' if node else 'PAIRING','node':node})

    async def provision_status(req):
        c=registry.one('SELECT * FROM pairing_claims WHERE claim_id=?',(req.match_info['id'],))
        require(c['user_id']==req[USER],'forbidden',403)
        room=registry.one('SELECT home_id FROM rooms WHERE room_id=?',(c['room_id'],))
        registry.authorize(req[USER],room['home_id'],('Owner','Installer'))
        return web.json_response({k:c[k] for k in ('claim_id','node_id','status','expires')})

    async def unpair(req):
        registry.unpair(req[USER],int(req.match_info['id']))
        return web.json_response({'status':'REVOKED'})

    async def channels(req):
        return web.json_response({'items':registry.channels(req[USER],int(req.match_info['id']))})

    async def devices(req):
        if req.method=='GET': return web.json_response({'items':registry.devices(req[USER],home(req))})
        d=await body(req)
        return web.json_response(registry.create_device(req[USER],d['home_id'],d['name'],d['kind'],d['channel_id']),status=201)

    async def patch_device(req):
        d=await body(req)
        registry.rename_device(req[USER],req.match_info['id'],d['name'],d['kind'])
        return web.json_response({'device_id':req.match_info['id']})

    async def command(req):
        d=await body(req)
        return web.json_response(registry.command(req[USER],req.match_info['id'],d['state'],d['idempotency_key'],d.get('ttl',5)),status=202)

    async def get_command(req):
        return web.json_response(registry.get_command(req[USER],req.match_info['id']))

    async def bind(req):
        d=await body(req)
        registry.bind(req[USER],d['device_id'],req.match_info['id'])
        return web.json_response({'status':'CONFIG_PENDING'})

    async def unbind(req):
        registry.unbind(req[USER],req.match_info['id'])
        return web.json_response({'status':'CONFIG_PENDING'})

    async def snapshot(req):
        return web.json_response(registry.snapshot(req[USER],home(req)))

    async def events(req):
        selected=home(req)
        registry.authorize(req[USER],selected)
        if req.headers.get('Upgrade','').lower()!='websocket':
            after=int(req.query.get('after','0'))
            require(after>=0)
            return web.json_response({'items':registry.events(req[USER],selected,after)})
        require(len(app[SOCKETS])<16,'websocket_capacity',429)
        ws=web.WebSocketResponse(heartbeat=20,max_msg_size=1024)
        await ws.prepare(req)
        app[SOCKETS].add(ws)
        try:

            while not ws.closed:
                registry.authorize(req[USER],selected)
                await asyncio.wait_for(ws.send_json({'type':'snapshot','data':registry.snapshot(req[USER],selected)}),5)
                try:
                    msg=await ws.receive(timeout=2)
                    if msg.type in (web.WSMsgType.CLOSE,web.WSMsgType.CLOSED,web.WSMsgType.ERROR): break
                except asyncio.TimeoutError:
                    pass
        except (ConnectionError,asyncio.TimeoutError,CoreError):
            pass
        finally:
            app[SOCKETS].discard(ws)
            await ws.close()
        return ws

    async def firmware(req):
        require(ota is not None,'ota_not_configured',503)
        if req.method=='GET':
            registry.authorize(req[USER],home(req))
            return web.json_response({'items':ota.artifacts()})
        d=await body(req)
        registry.authorize(req[USER],d['home_id'],('Owner',))
        import base64
        return web.json_response(ota.upload(d['manifest'],d['signature'],base64.b64decode(d['image'],validate=True)),status=201)

    async def ota_jobs(req):
        require(ota is not None,'ota_not_configured',503)
        if req.method=='GET':
            if 'id' in req.match_info: return web.json_response(ota.job(req[USER],req.match_info['id']))
            selected=home(req);registry.authorize(req[USER],selected)
            return web.json_response({'items':[ota.job(req[USER],j['job_id']) for j in registry.rows('SELECT job_id FROM ota_jobs WHERE home_id=? ORDER BY created DESC LIMIT 100',(selected,))]})
        d=await body(req)
        return web.json_response(ota.create_job(req[USER],d['home_id'],d['artifact_id'],d['node_ids']),status=202)

    async def voice_ws(req):
        require(voice is not None, 'voice_not_configured', 503)
        return await voice.websocket(req, req[USER])

    handlers=[('GET','/health',health),('GET','/homes',homes),('POST','/homes',homes),
              ('GET','/rooms',rooms),('POST','/rooms',rooms),('GET','/rooms/{id}/nodes',room_nodes),
              ('GET','/nodes',nodes),('POST','/nodes/claim',claim),('GET','/nodes/{id}',nodes),
              ('POST','/nodes/{id}/assign',assign),('POST','/nodes/{id}/unpair',unpair),('GET','/nodes/{id}/channels',channels),
              ('POST','/provisioning/prepare',provision_prepare),('POST','/provisioning/confirm',provision_confirm),('GET','/provisioning/{id}',provision_status),
              ('GET','/devices',devices),('POST','/devices',devices),('PATCH','/devices/{id}',patch_device),
              ('POST','/devices/{id}/command',command),('GET','/commands/{id}',get_command),
              ('POST','/channels/{id}/bind',bind),('DELETE','/channels/{id}/binding',unbind),
              ('GET','/states/snapshot',snapshot),('GET','/events',events),
              ('GET','/firmware',firmware),('POST','/firmware',firmware),
              ('GET','/ota/jobs',ota_jobs),('POST','/ota/jobs',ota_jobs),('GET','/ota/jobs/{id}',ota_jobs),
              ('GET','/voice/ws',voice_ws)]
    for method,path,handler in handlers: app.router.add_route(method,'/api/v1'+path,handler)

    async def openapi(req):
        paths={}
        for method,path,_ in handlers:
            item={'responses':{'200':{'description':'Success'},'400':{'description':'Invalid input'},'401':{'description':'Authentication required'},'403':{'description':'Forbidden'},'409':{'description':'Conflict'}},'security':[{'bearerAuth':[]}]}
            if '{id}' in path: item['parameters']=[{'name':'id','in':'path','required':True,'schema':{'type':'string'}}]
            paths.setdefault('/api/v1'+path,{})[method.lower()]=item
        return web.json_response({'openapi':'3.0.3','info':{'title':'Home Competition','version':'1.0.0'},'paths':paths,'components':{'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer'}}}})
    app.router.add_get('/api/v1/openapi.json',openapi)

    async def shutdown(_app):
        for ws in tuple(app[SOCKETS]): await ws.close(code=1001,message=b'Gateway stopping')
    app.on_shutdown.append(shutdown)
    return app
