import struct
from unittest import TestCase
from test_hc_registry import RegistryTest
from gateway.core_v1.bridge import Bridge
from gateway.core_v1.firebase_commissioning import CoreCommissioning
from gateway.core_v1.maintenance import RECEIPT
from gateway.core_v1.protocol import Frame,MessageType,ReplayWindow
from gateway.core_v1.registry import CoreError


class CoreMaintenanceTests(TestCase):
    _Fixture=RegistryTest
    def setUp(self):
        self.f=self._Fixture();self.f.setUp();f=self.f
        f.online(f.sub,200);f.online(f.action,100);f.report()
        self.bridge=Bridge(f.r);self.m=self.bridge.maintenance
        self.bridge.windows[f.action]=ReplayWindow();self.bridge.windows[f.action].admit(100)
        self.bridge.uptimes[f.action]=(1000,f.r.clock())
        self.bridge.receive(f.sub,Frame(MessageType.CAPABILITY_REPORT,1,f.action,0,100,1,1,b'M\x01').encode(f.keys[f.action]))
    def tearDown(self):self.f.tearDown()
    def start(self,kind='factory_reset',key='once'):
        return self.m.start(self.f.owner,self.f.home,'AB001122334402',{'kind':kind,'confirmation':True,'idempotency_key':key})
    def receipt(self,op,state=2,source=None,boot=100):
        row=self.f.r.one('SELECT * FROM core_maintenance WHERE operation_id=?',(op['operation_id'],))
        frame=Frame(MessageType.MAINTENANCE_ACK,9,source or self.f.action,0,boot,5,1,RECEIPT.pack(row['wire_id'],state,0))
        self.m.receive(frame)

    def test_owner_confirmation_firmware_gate_and_single_active_operation(self):
        f=self.f;cloud=CoreCommissioning(f.r,{'home_id':f.home},['account']);actor=cloud.actor('account')
        self.assertFalse(cloud.context('account')['capabilities']['manage_devices'])
        with self.assertRaises(CoreError):self.m.start(actor,f.home,'AB001122334402',{'kind':'reboot','idempotency_key':'x'})
        f.r.add_member(f.owner,f.home,actor,'Owner');self.assertTrue(cloud.context('account')['capabilities']['manage_devices'])
        with self.assertRaises(CoreError):self.m.start(actor,f.home,'AB001122334402',{'kind':'factory_reset','idempotency_key':'x'})
        op=self.start();self.assertEqual(op,self.start())
        with self.assertRaises(CoreError):self.start(key='another')
        packets=self.m.outgoing(self.bridge);self.assertEqual(len(packets),1)
        frame=Frame.decode(packets[0][1],f.keys[f.action]);self.assertEqual(frame.type,MessageType.MAINTENANCE)
        self.assertEqual(struct.unpack('<BQ',frame.payload)[0],2)

    def test_reset_receipt_is_required_and_device_can_be_claimed_again(self):
        f=self.f;op=self.start()
        self.receipt(op,1);self.assertEqual(self.m.get(f.owner,f.home,op['operation_id'])['state'],'running')
        self.assertEqual(f.r.get_node(f.owner,f.action)['registration'],'REGISTERED')
        with self.assertRaises(CoreError):self.receipt(op,source=f.sub)
        with self.assertRaises(CoreError):self.receipt(op,boot=999)
        self.receipt(op,2);self.assertEqual(self.m.get(f.owner,f.home,op['operation_id'])['state'],'succeeded')
        self.assertEqual(f.r.get_node(f.owner,f.action)['registration'],'PAIRING')
        claim=f.r.claim(f.owner,'HC-001122334402','setup-HC-001122334402',f.room,f.sub)
        self.assertEqual(claim['node_id'],f.action)

    def test_missing_receipt_expires_and_subbox_with_children_is_protected(self):
        f=self.f
        self.m.receive(Frame(MessageType.CAPABILITY_REPORT,1,f.sub,0,200,1,1,b'M\x01'))
        with self.assertRaises(CoreError):self.m.start(f.owner,f.home,'SB001122334401',{'kind':'factory_reset','confirmation':True,'idempotency_key':'parent'})
        op=self.start('reboot');original=f.r.clock;now=original();f.r.clock=lambda:now+16
        self.assertEqual(self.m.get(f.owner,f.home,op['operation_id'])['state'],'timed_out')
        self.assertEqual(self.m.outgoing(self.bridge),[])
        self.assertEqual(f.r.get_node(f.owner,f.action)['registration'],'REGISTERED')

    def test_reboot_only_succeeds_after_an_authenticated_new_boot(self):
        f=self.f;op=self.start('reboot');self.receipt(op,2)
        self.assertEqual(self.m.get(f.owner,f.home,op['operation_id'])['state'],'running')
        f.online(f.action,101)
        self.m.receive(Frame(MessageType.CAPABILITY_REPORT,1,f.action,0,101,1,1,b'M\x01'))
        self.assertEqual(self.m.get(f.owner,f.home,op['operation_id'])['state'],'succeeded')

del RegistryTest
