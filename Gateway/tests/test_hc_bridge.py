import struct
import unittest
from test_hc_registry import RegistryTest
from gateway.core_v1.bridge import Bridge
from gateway.core_v1.protocol import Frame, MessageType,ReplayWindow
from gateway.core_v1.registry import CoreError


class BridgeTest(unittest.TestCase):
    _RegistryTest = RegistryTest

    def setUp(self):
        self.fixture = self._RegistryTest()
        self.fixture.setUp()
        self.r = self.fixture.r
        self.sub = self.fixture.sub
        self.action = self.fixture.action
        self.owner = self.fixture.owner
        self.keys = self.fixture.keys

    def tearDown(self):
        self.fixture.tearDown()

    def test_repeated_or_untracked_boot_result_gets_receipt_ack_without_false_success(self):
        from unittest.mock import Mock
        bridge=Bridge(self.r);window=ReplayWindow();window.admit(123);bridge.windows[self.action]=window
        bridge.ota=Mock();bridge.ota.receive.side_effect=CoreError('not_found')
        before=self.r.get_node(self.owner,self.action)['firmware']
        payload=b'2.0.0-b1'.ljust(16,b'\0')+b'h'*32+b'\x01'
        for sequence in (1,2):
            wire=Frame(MessageType.OTA_RESULT,sequence,self.action,0,123,sequence,1,payload).encode(self.keys[self.action])
            response=bridge.receive(self.sub,wire)
            ack=Frame.decode(response[0][1],self.keys[self.action])
            self.assertEqual((ack.type,ack.payload),(MessageType.OTA_RESULT,b''))
        self.assertEqual(self.r.get_node(self.owner,self.action)['firmware'],before)
        bad=Frame(MessageType.OTA_RESULT,3,self.action,0,123,3,1,payload[:-1]+b'\x03').encode(self.keys[self.action])
        with self.assertRaises(CoreError):bridge.receive(self.sub,bad)
        self.assertEqual(bridge.ota.receive.call_count,2)
    def test_signed_binary_handshake_state_and_command(self):
        bridge=Bridge(self.r)
        nonce=b'n'*16
        hello=Frame(MessageType.HELLO,1,self.action,0,123,1,1,nonce).encode(self.keys[self.action])
        responses=bridge.receive(self.sub,hello)
        challenge=Frame.decode(responses[0][1],self.keys[self.action])
        self.assertEqual(challenge.type,MessageType.IDENTITY_CHALLENGE)
        self.assertEqual(challenge.payload[:16],nonce)
        response=Frame(MessageType.IDENTITY_RESPONSE,2,self.action,0,123,2,1,challenge.payload[16:]).encode(self.keys[self.action])
        bridge.receive(self.sub,response)
        self.assertEqual(self.r.get_node(self.owner,self.action)['boot_id'],'123')
        channels=struct.pack('<Q',1000)+b''.join(struct.pack('<BBfH',i,2,.25,0) for i in (1,2,3))
        state=Frame(MessageType.STATE_REPORT,3,self.action,0,123,3,1,channels).encode(self.keys[self.action])
        bridge.receive(self.sub,state)
        self.assertEqual(self.r.channels(self.owner,self.action)[0]['current_rms_a'],.25)
        self.assertEqual(bridge.receive(self.sub,state),[])
        with self.assertRaises(ValueError):
            bridge.receive(self.sub,state[:-1]+bytes([state[-1]^1]))


del RegistryTest
