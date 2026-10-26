"""Five simulated sockets, real response scheduling/playback and SQLite history.

TTS returns fixed PCM; this measures host orchestration, not Pi synthesis/radio capacity.
"""
import asyncio
import json
import math
from pathlib import Path
import resource
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer
from kws_service import KwsService
from registry_manager import RegistryManager


class KwsLoadTest(unittest.IsolatedAsyncioTestCase):
    async def test_five_speakers_keep_telemetry_live_and_bound_response_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryManager(registry_path=str(Path(tmp)/'registry'), db_path=str(Path(tmp)/'db'))
            nodes = registry.data['nodes'] = {}
            sources = []
            for i in range(5):
                sb, ab = f'SB{i+1:012X}', f'AB{i+11:012X}'
                nodes[sb] = {'status':'online'}
                nodes[ab] = {'status':'online', 'hardware_uid':ab[2:], 'subbox_id':sb,
                             'owner_epoch':1, 'desired_config_version':1, 'channels':{'ch1':{}}}
                sources.append({'node_id':ab, 'room':'BEDROOM'})

            async def publish(*args, **kwargs): return True
            async def synthesize(*args, **kwargs):
                await asyncio.sleep(0)
                return b'\0' * 320
            gateway = SimpleNamespace(registry=registry, mqtt=SimpleNamespace(publish=publish),
                                      tts=SimpleNamespace(synthesize_pcm=synthesize), broadcast_event=lambda *args:None)
            audio = gateway.audio_server = AudioServer(gateway)
            service = KwsService(gateway)
            self.addAsyncCleanup(service.stop)
            await service.set_config({'revision':0, 'sources':sources, 'bindings':[]})
            slow_gate = asyncio.Event()
            independent = asyncio.Event()
            completed_nodes = set()
            started = {}
            latencies = []

            class Socket:
                has_speaker = True
                def __init__(self, node): self.node_id=node
                async def send(self, message):
                    if not isinstance(message, str): return
                    message = json.loads(message)
                    if message['type'] == 'audio_start' and self.node_id == 'SB000000000001':
                        await slow_gate.wait()
                    if message['type'] == 'kws_playback_done':
                        key = (self.node_id, message['request_id'])
                        latencies.append((time.perf_counter()-started[key])*1000)
                        completed_nodes.add(self.node_id)
                        if len(completed_nodes - {'SB000000000001'}) == 4: independent.set()

            audio._ws_nodes = {sb:Socket(sb) for sb in nodes if sb.startswith('SB')}
            audio._active_speakers = set(audio._ws_nodes.values())
            accepted = dropped = peak_pending = 0
            cpu_start = time.process_time()
            wall_start = time.perf_counter()
            for request in range(1, 6):
                for source in sources:
                    ab = source['node_id']; sb = nodes[ab]['subbox_id']
                    result = dict(schema_version=1, issued_at=int(time.time()), session_id=1, request_id=request,
                                  origin_node=ab, status='error', reason='missing_binding', follow_up=False)
                    started[sb, request] = time.perf_counter()
                    if await service.on_result(f'home/subbox/{sb}/event/kws_result', result): accepted += 1
                    else: dropped += 1
                    peak_pending = max(peak_pending, len(service._tasks))
                    self.assertEqual(registry.record_channel_telemetry(ab, {'ch1':{
                        'current_ma':request*100, 'voltage_v':None, 'power_w':None,
                        'valid':True, 'sample_uptime_ms':request*1000}}), 1)
            try:
                await asyncio.wait_for(independent.wait(), 2)
                self.assertNotIn('SB000000000001', completed_nodes)
                for source in sources:
                    history = registry.get_channel_telemetry_history(source['node_id'], 'ch1')
                    self.assertEqual(len(history), 5)
                    self.assertTrue(all(row['power_w'] is None for row in history))
            finally:
                slow_gate.set()
                await service.drain()
            self.assertEqual((accepted, dropped, peak_pending), (16, 9, 16))
            self.assertEqual(len(latencies), accepted)
            ordered = sorted(latencies)
            metrics = dict(clients=5, accepted=accepted, dropped=dropped, queue_peak=peak_pending,
                           telemetry_rows=25, p50_ms=round(ordered[math.ceil(len(ordered)*.5)-1],2),
                           p95_ms=round(ordered[math.ceil(len(ordered)*.95)-1],2),
                           elapsed_ms=round((time.perf_counter()-wall_start)*1000,2),
                           cpu_ms=round((time.process_time()-cpu_start)*1000,2),
                           max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            print('KWS_HOST_EXERCISE ' + json.dumps(metrics, sort_keys=True))


if __name__ == '__main__': unittest.main()
