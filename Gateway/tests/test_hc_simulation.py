import tempfile
import unittest
from gateway.core_v1.simulator import Simulation
from gateway.core_v1.protocol import Frame,MessageType


class SimulationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.sim=Simulation(self.tmp.name)
        r=self.sim.registry;room=r.create_room(self.sim.owner,self.sim.home,'Room')
        self.parent=self.sim.add(room);self.box=self.sim.add(room,self.parent.node)
        channel=r.channels(self.sim.owner,self.box.node)[0]['channel_id']
        self.device=r.create_device(self.sim.owner,self.sim.home,'Light','light',channel)
        self.sim.pump()
    def tearDown(self):self.sim.close();self.tmp.cleanup()
    def command(self,state,key):return self.sim.registry.command(self.sim.owner,self.device['device_id'],state,key)
    def wire_commands(self):return [data for _,data in self.sim.bridge.outgoing() if Frame.decode(data,self.box.key).type==MessageType.COMMAND]
    def test_ack_loss_retry_executes_once(self):
        c=self.command(True,'lost-ack');data=self.wire_commands()[0]
        self.sim.deliver_down(data,drop_ack=True)
        self.assertEqual(self.box.applied,1)
        self.sim.now+=1
        self.sim.pump()
        self.assertEqual(self.box.applied,1)
        self.assertEqual(self.sim.registry.get_command(self.sim.owner,c['command_id'])['status'],'APPLIED')
    def test_reordered_commands_cannot_restore_old_intent(self):
        self.command(True,'old');self.command(False,'new')
        older,newer=self.wire_commands()
        self.sim.deliver_down(newer);self.sim.deliver_down(older)
        self.assertEqual(self.box.applied,1)
        self.assertFalse(self.box.states[0])
    def test_expired_wire_command_never_actuates(self):
        c=self.command(True,'expiry');data=self.wire_commands()[0]
        self.sim.now+=10;self.sim.deliver_down(data)
        self.assertEqual(self.box.applied,0)
        self.sim.pump()
        self.assertEqual(self.sim.registry.get_command(self.sim.owner,c['command_id'])['status'],'TIMEOUT')
