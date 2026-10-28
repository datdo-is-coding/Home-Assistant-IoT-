"""Core-enrolled speakers authenticate independently of legacy commissioning."""
import asyncio
import hashlib
import hmac
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
import ssl
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer
from registry_manager import RegistryManager
import config
from gateway.core_v1.registry import Registry, canonical
import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import ipaddress


class SpeakerSocket:
    remote_address = ('127.0.0.1', 1234)
    open = True
    closed = False

    def __init__(self, node, token, messages, observe=None, tls=True):
        self.request_headers = {'Authorization': 'Bearer '+token, 'X-Device-ID': node}
        self.transport = SimpleNamespace(get_extra_info=lambda key: object() if tls and key == 'ssl_object' else None)
        self.messages, self.observe, self.sent = messages, observe, []

    async def __aiter__(self):
        for message in self.messages:
            yield json.dumps(message)
        if self.observe:
            await self.observe(self)

    async def send(self, data):
        self.sent.append(data if isinstance(data, bytes) else json.loads(data))

    async def close(self, *args):
        self.closed, self.open = True, False


class CoreSpeakerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Registry(Path(self.tmp.name)/'core.db', b'k'*32)
        self.owner, _ = self.r.create_user('owner')
        self.home = self.r.create_home(self.owner, 'Home')
        room = self.r.create_room(self.owner, self.home, 'Living')
        factory = 'HC-001122334401'; secret = b's'*32
        self.r.add_factory_device(factory, 'SUB_BOX', 'subbox', secret, 'test-setup-code')
        claim = self.r.claim(self.owner, factory, 'test-setup-code', room, None)
        proof = hmac.digest(secret, canonical(dict(claim=claim, stored=True, peer_confirmed=True, channels=0)), 'sha256').hex()
        node = self.r.confirm_claim(claim['claim_id'], proof, stored=True, peer_confirmed=True, channels=0)
        self.node, self.id = node['node_id'], 'SB001122334401'
        self.token = hmac.digest(self.r.node_key(self.node), b'HC-SPEAKER-V1\0', 'sha256').hex()
        self.gateway = SimpleNamespace(firebase_commissioning=SimpleNamespace(core=SimpleNamespace(r=self.r, home=self.home)),
                                       tts=SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'\0\0'*800)),
                                       registry=SimpleNamespace(get_all_nodes=lambda:{}), broadcast_event=lambda *args:None)
        self.audio = AudioServer(self.gateway)
        self.addAsyncCleanup(self.cleanup)

    async def cleanup(self):
        self.r.close(); self.tmp.cleanup()

    async def test_only_registered_subbox_in_configured_home_can_authenticate(self):
        self.assertTrue(self.audio._is_token_valid(self.token, self.id))
        self.assertFalse(self.audio._is_token_valid('0'*64, self.id))
        self.assertFalse(self.audio._is_token_valid(self.token, 'SB001122334402'))
        self.gateway.firebase_commissioning.core.home = 'another-home'
        self.assertFalse(self.audio._is_token_valid(self.token, self.id))
        self.gateway.firebase_commissioning.core.home = self.home
        self.r.db.execute("UPDATE registered_nodes SET registration='REVOKED' WHERE node_id=?",(self.node,))
        self.assertFalse(self.audio._is_token_valid(self.token, self.id))

    async def test_core_hello_registers_playback_only_without_legacy_reprovision(self):
        observed = {}
        async def observe(ws):
            observed.update(bound=self.audio.has_ws(self.id), playback_only=ws.playback_only,
                            ack=ws.requires_playback_ack, speaker=ws in self.audio._active_speakers,
                            relay=await self.audio.send_relay_ws(self.id,'ch1','turn_on',7))
        ws = SpeakerSocket(self.id,self.token,[{'t':'hello','id':self.id,'speaker':True,'playback_only':True}],observe)
        with patch.object(config,'WS_AUDIO_AUTH_REQUIRED',True):
            await self.audio._handle_client(ws)
        self.assertIn({'t':'hello_ok','id':self.id},ws.sent)
        self.assertEqual(observed, dict(bound=True, playback_only=True, ack=True, speaker=True, relay=False))

    async def test_core_speaker_rejects_plaintext_and_wrong_identity(self):
        for tls, ident in [(False,self.id),(True,'SB001122334402')]:
            ws=SpeakerSocket(self.id,self.token,[{'t':'hello','id':ident,'speaker':True,'playback_only':True}],tls=tls)
            with patch.object(config,'WS_AUDIO_AUTH_REQUIRED',True):
                await self.audio._handle_client(ws)
            self.assertTrue(ws.closed)
            self.assertFalse(self.audio.has_ws(self.id))

    async def test_incomplete_tls_configuration_never_starts_plaintext_server(self):
        missing = str(Path(self.tmp.name) / 'missing.pem')
        for cert, key in ((missing, ''), ('', missing), (missing, missing)):
            with self.subTest(cert=cert, key=key), patch.object(config, 'WS_AUDIO_TLS_CERT', cert), \
                    patch.object(config, 'WS_AUDIO_TLS_KEY', key):
                with self.assertRaisesRegex(ValueError, 'TLS certificate/key missing'):
                    await self.audio.start()
                self.assertIsNone(self.audio.server)

    async def test_core_identity_cannot_use_legacy_hello_without_device_header(self):
        root = Path(self.tmp.name)
        self.gateway.registry = RegistryManager(str(root/'legacy.json'), str(root/'legacy.db'))
        for field, auth_required, header_node in product(('id', 'node_id', 'device_id'), (False, True), (None, 'legacy-device')):
            with self.subTest(field=field, auth_required=auth_required, header_node=header_node):
                hello = {'t':'hello', field:self.id, 'speaker':True, 'cfg':1}
                if auth_required:
                    hello['token'] = self.token
                ws = SpeakerSocket(self.id, self.token, [hello], tls=False)
                ws.request_headers = {} if header_node is None else {'X-Device-ID':header_node}
                with patch.object(config, 'WS_AUDIO_AUTH_REQUIRED', auth_required), \
                        patch.object(config, 'WS_AUDIO_TOKEN', ''), patch.object(config, 'WS_AUDIO_TOKENS', {}):
                    await self.audio._handle_client(ws)
                self.assertTrue(ws.closed, 'Core identities must require the pinned WSS speaker handshake')
                self.assertNotIn({'t':'hello_ok', 'id':self.id}, ws.sent)

    async def test_core_identity_cannot_bind_through_legacy_start(self):
        ws = SpeakerSocket(self.id, self.token, [{'type':'start', 'node_id':self.id}], tls=False)
        ws.request_headers = {}
        with patch.object(config, 'WS_AUDIO_AUTH_REQUIRED', False), \
                patch.object(config, 'WS_AUDIO_TOKEN', ''), patch.object(config, 'WS_AUDIO_TOKENS', {}):
            await self.audio._handle_client(ws)
        self.assertTrue(ws.closed)
        self.assertFalse(any(message.get('state') == 'recording' for message in ws.sent))

    async def test_core_speaker_does_not_accept_unconfirmed_mp3_fallback(self):
        ws = SpeakerSocket(self.id, self.token, [])
        ws.node_id, ws.has_speaker = self.id, True
        ws.playback_only = ws.requires_playback_ack = True
        self.audio._active_speakers.add(ws)
        self.gateway.tts.synthesize_pcm.return_value = None
        self.gateway.tts.synthesize = AsyncMock(return_value=b'unplayable-mp3')
        self.assertFalse(await self.audio.speak_proactive('test'))
        self.assertEqual(ws.sent, [])

    async def test_queued_playback_rechecks_revocation_before_sending(self):
        ws = SpeakerSocket(self.id, self.token, [])
        ws.node_id, ws.has_speaker = self.id, True
        ws.playback_only = ws.requires_playback_ack = True
        lock = self.audio._playback_locks['speaker_'+self.id]
        async with lock:
            playback = asyncio.create_task(self.audio._broadcast_pcm_stream([ws], b'\0\0'*800))
            await asyncio.sleep(0)
            self.assertFalse(playback.done())
            self.r.db.execute("UPDATE registered_nodes SET registration='REVOKED' WHERE node_id=?", (self.node,))
        try:
            await asyncio.wait({playback}, timeout=.1)
            self.assertEqual(ws.sent, [], 'A speaker revoked while queued must receive no audio')
            self.assertTrue(playback.done())
            self.assertFalse(playback.result())
        finally:
            playback.cancel()
            await asyncio.gather(playback, return_exceptions=True)

    async def test_explicit_missing_speaker_does_not_play_in_another_room(self):
        other=SpeakerSocket(self.id,self.token,[])
        other.has_speaker=True
        self.audio._ws_nodes[self.id]=other
        self.assertFalse(await self.audio.speak_proactive('test','missing-speaker'))
        self.assertEqual(other.sent,[])

    async def test_proactive_returns_false_if_target_disconnects_during_synthesis(self):
        ws=SpeakerSocket(self.id,self.token,[]);ws.has_speaker=True
        self.audio._active_speakers.add(ws)
        async def synthesize(*args,**kwargs):
            ws.closed=True;ws.open=False;return b'\0\0'*800
        self.gateway.tts.synthesize_pcm.side_effect=synthesize
        self.assertFalse(await self.audio.speak_proactive('test'))

    async def test_wss_stream_waits_for_matching_device_completion(self):
        root=Path(self.tmp.name);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'speaker-test')]);now=datetime.now(timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
              .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),True)
              .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
              .sign(key,hashes.SHA256()))
        certfile=root/'server.pem';keyfile=root/'server.key'
        certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.audio.host='127.0.0.1';self.audio.port=0
        with patch.object(config,'WS_AUDIO_TLS_CERT',str(certfile)), patch.object(config,'WS_AUDIO_TLS_KEY',str(keyfile)):
            await self.audio.start()
        try:
            port=self.audio.server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f'wss://127.0.0.1:{port}/ws/audio',ssl=ssl.create_default_context(cafile=str(certfile)),
                    headers={'Authorization':'Bearer '+self.token,'X-Device-ID':self.id}) as ws:
                    await ws.send_json({'t':'hello','id':self.id,'speaker':True,'playback_only':True})
                    self.assertEqual((await ws.receive_json())['t'],'hello_ok')
                    for valid in (True,False):
                        task=asyncio.create_task(self.audio.speak_proactive('test',self.id));received=0
                        while True:
                            msg=await asyncio.wait_for(ws.receive(),2)
                            if msg.type==aiohttp.WSMsgType.BINARY:received+=len(msg.data)
                            elif msg.type==aiohttp.WSMsgType.TEXT:
                                data=json.loads(msg.data)
                                if data.get('type')=='audio_end':break
                        await asyncio.sleep(.02)
                        self.assertFalse(task.done(),'Sending END is not playback completion')
                        await ws.send_json({'type':'playback_complete','playback_id':'0'*32,'success':True,'received_bytes':received})
                        await asyncio.sleep(.02);self.assertFalse(task.done())
                        await ws.send_json({'type':'playback_complete','playback_id':data['playback_id'],
                                            'success':True,'received_bytes':received if valid else received+1})
                        self.assertEqual(await asyncio.wait_for(task,2),valid)
        finally:
            await self.audio.stop()
