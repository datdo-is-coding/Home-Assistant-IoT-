import tempfile
from pathlib import Path
import unittest
from aiohttp.test_utils import TestClient, TestServer
from gateway.core_v1.api import create_app
from gateway.core_v1.registry import Registry


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.registry=Registry(Path(self.tmp.name)/'api.db',b'k'*32)
        self.user,self.token=self.registry.create_user('Owner')
        self.home=self.registry.create_home(self.user,'House')
        self.client=TestClient(TestServer(create_app(self.registry)))
        await self.client.start_server()
        self.headers={'Authorization':'Bearer '+self.token}

    async def asyncTearDown(self):
        await self.client.close()
        self.registry.close()
        self.tmp.cleanup()

    async def test_auth_validation_and_routes(self):
        response=await self.client.get('/api/v1/homes')
        self.assertEqual(response.status,401)
        response=await self.client.get('/api/v1/homes',headers=self.headers)
        self.assertEqual((await response.json())['items'][0]['home_id'],self.home)
        response=await self.client.post('/api/v1/rooms',headers=self.headers,json={'home_id':self.home,'name':'Kitchen'})
        self.assertEqual(response.status,201)
        response=await self.client.post('/api/v1/rooms',headers=self.headers,json={})
        self.assertEqual(response.status,400)
        self.assertIn('code',(await response.json())['error'])
        response=await self.client.get('/api/v1/openapi.json',headers=self.headers)
        self.assertIn('/api/v1/devices/{id}/command',(await response.json())['paths'])

    async def test_websocket_snapshot_and_cross_home(self):
        async with self.client.ws_connect('/api/v1/events?home_id='+self.home,headers=self.headers) as ws:
            message=await ws.receive_json(timeout=3)
            self.assertEqual(message['type'],'snapshot')
            self.assertEqual(message['data']['home_id'],self.home)
            self.registry.create_room(self.user,self.home,'Bedroom')
            message=await ws.receive_json(timeout=3)
            self.assertEqual(message['type'],'snapshot')
            self.assertEqual(message['data']['rooms'][0]['name'],'Bedroom')
        user,token=self.registry.create_user('Other')
        other=self.registry.create_home(user,'Other')
        response=await self.client.get('/api/v1/states/snapshot?home_id='+other,headers=self.headers)
        self.assertEqual(response.status,403)

    async def test_bad_json_and_origin(self):
        response=await self.client.post('/api/v1/rooms',headers=self.headers,data='[1]')
        self.assertEqual(response.status,400)
        response=await self.client.post('/api/v1/rooms',headers={**self.headers,'Origin':'https://evil.example'},json={'name':'x','home_id':self.home})
        self.assertEqual(response.status,403)


if __name__=='__main__': unittest.main()
