"""
Multi-Room Concurrent Audio and Spatial Arbitration Tests.
Verifies:
1. 4 SubBoxes in 4 different rooms stream simultaneously with RMS 1500 -> all 4 are processed and succeed.
2. 2 devices in the same room -> louder is kept, weaker is suppressed.
3. Leakage across rooms (Room A has 2000 RMS, Room B has 200 RMS) -> Room B is suppressed.
4. Playback lock in Room A only locks Room A, Room B can start streaming.
"""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from audio_server import AudioServer, StreamArbiter
import config


class AsyncMessageSocket:
    remote_address = ('127.0.0.1', 54321)
    open = True

    def __init__(self, message_list, delay=0.01):
        self.message_list = message_list
        self.delay = delay
        self.sent = []
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def __aiter__(self):
        for msg in self.message_list:
            if callable(msg):
                msg = await msg() if asyncio.iscoroutinefunction(msg) else msg()
            yield msg
            if self.delay:
                await asyncio.sleep(self.delay)

    async def send(self, message):
        self.sent.append(message if isinstance(message, bytes) else json.loads(message))

    async def close(self, code=1000, reason=""):
        self.open = False
        self.closed = True
        self.close_code = code
        self.close_reason = reason


def make_pcm(rms: int, num_samples: int = 960) -> bytes:
    sample_bytes = int(rms).to_bytes(2, byteorder='little', signed=True)
    return sample_bytes * num_samples


class MultiRoomAudioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.nodes = {
            "SB_PK": {"room": "phong_khach", "speaker": True},
            "SB_PN": {"room": "phong_ngu", "speaker": True},
            "SB_PB": {"room": "phong_bep", "speaker": True},
            "SB_PT": {"room": "phong_tam", "speaker": True},
            "SB_PK_2": {"room": "phong_khach", "speaker": True},
        }
        self.gateway = SimpleNamespace(
            registry=SimpleNamespace(get_all_nodes=lambda: self.nodes),
            asr=SimpleNamespace(
                transcribe_with_confidence=lambda pcm, sr: ("bật đèn", 0.95)
            ),
            tts=SimpleNamespace(
                synthesize_pcm=AsyncMock(return_value=b"\x00\x00" * 3200),
                synthesize=AsyncMock(return_value=b"mp3_data"),
            ),
            process_voice_command=AsyncMock(
                return_value={"verify": "success", "voice_reply": "Đã bật đèn"}
            ),
            broadcast_event=lambda *args, **kwargs: None,
        )
        self.server = AudioServer(self.gateway)

    async def test_4_subboxes_in_4_rooms_stream_simultaneously(self):
        """4 SubBoxes in 4 different rooms streaming concurrently with RMS 1500 must all succeed."""
        rooms_and_nodes = [
            ("SB_PK", "phong_khach"),
            ("SB_PN", "phong_ngu"),
            ("SB_PB", "phong_bep"),
            ("SB_PT", "phong_tam"),
        ]

        sockets = []
        tasks = []
        for nid, room in rooms_and_nodes:
            messages = [
                json.dumps({"type": "start", "node_id": nid, "codec": "pcm", "sample_rate": 16000}),
                make_pcm(1500),
                json.dumps({"type": "stop"}),
            ]
            ws = AsyncMessageSocket(messages, delay=0.02)
            sockets.append((nid, room, ws))
            tasks.append(self.server._handle_client(ws))

        await asyncio.gather(*tasks)

        for nid, room, ws in sockets:
            # Must have recording and processing states
            statuses = [m.get("state") for m in ws.sent if isinstance(m, dict) and m.get("type") == "status"]
            self.assertIn("recording", statuses, f"{nid} missing recording status")
            self.assertIn("processing", statuses, f"{nid} missing processing status")

            # Must have accepted transcript
            transcripts = [m for m in ws.sent if isinstance(m, dict) and m.get("type") == "transcript"]
            self.assertTrue(len(transcripts) > 0, f"{nid} missing transcript")
            self.assertTrue(transcripts[0].get("accepted"), f"{nid} transcript was not accepted")

            # Must NOT have been suppressed
            suppressed = [m for m in ws.sent if isinstance(m, dict) and m.get("type") == "suppressed"]
            self.assertEqual(len(suppressed), 0, f"{nid} should not be suppressed: {suppressed}")

        # All 4 voice commands must have been processed
        self.assertEqual(self.gateway.process_voice_command.call_count, 4)

    async def test_two_devices_same_room_louder_kept_weaker_suppressed(self):
        """2 devices in the same room (phong_khach): louder kept, weaker suppressed."""
        ws_loud = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_PK", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(1800),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        ws_weak = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_PK_2", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(1200),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        await asyncio.gather(
            self.server._handle_client(ws_loud),
            self.server._handle_client(ws_weak),
        )

        # Louder socket SB_PK succeeded
        loud_transcripts = [m for m in ws_loud.sent if isinstance(m, dict) and m.get("type") == "transcript"]
        self.assertTrue(len(loud_transcripts) > 0)
        self.assertTrue(loud_transcripts[0].get("accepted"))
        self.assertFalse(any(isinstance(m, dict) and m.get("type") == "suppressed" for m in ws_loud.sent))

        # Weaker socket SB_PK_2 was suppressed
        weak_suppressed = [m for m in ws_weak.sent if isinstance(m, dict) and m.get("type") == "suppressed"]
        self.assertTrue(len(weak_suppressed) > 0)
        self.assertEqual(weak_suppressed[0].get("dominant_node"), "SB_PK")
        self.assertEqual(weak_suppressed[0].get("detected_room"), "phong_khach")

    async def test_cross_room_sound_leakage_suppressed(self):
        """Leakage across rooms: Room A has 2000 RMS, Room B has 200 RMS -> Room B is suppressed."""
        ws_pk = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_PK", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(2000),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        ws_pn = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_PN", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(200),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        await asyncio.gather(
            self.server._handle_client(ws_pk),
            self.server._handle_client(ws_pn),
        )

        # SB_PK (Room A) succeeded
        pk_transcripts = [m for m in ws_pk.sent if isinstance(m, dict) and m.get("type") == "transcript"]
        self.assertTrue(len(pk_transcripts) > 0)
        self.assertTrue(pk_transcripts[0].get("accepted"))

        # SB_PN (Room B) suppressed as acoustic leak
        pn_suppressed = [m for m in ws_pn.sent if isinstance(m, dict) and m.get("type") == "suppressed"]
        self.assertTrue(len(pn_suppressed) > 0)
        self.assertEqual(pn_suppressed[0].get("dominant_node"), "SB_PK")
        self.assertEqual(pn_suppressed[0].get("detected_room"), "phong_khach")

    async def test_playback_lock_per_room_isolation(self):
        """Playback lock in Room A only locks Room A, Room B can start streaming."""
        # Setup connected nodes in server
        ws_pk = AsyncMessageSocket([], delay=0)
        ws_pk.node_id = "SB_PK"
        ws_pk.has_speaker = True
        self.server._ws_nodes["SB_PK"] = ws_pk
        self.server._active_speakers.add(ws_pk)

        ws_pn = AsyncMessageSocket([], delay=0)
        ws_pn.node_id = "SB_PN"
        ws_pn.has_speaker = True
        self.server._ws_nodes["SB_PN"] = ws_pn
        self.server._active_speakers.add(ws_pn)

        # Lock Room A (phong_khach) playback lock
        async with self.server._playback_locks["phong_khach"]:
            self.assertTrue(self.server._playback_locks["phong_khach"].locked())
            self.assertFalse(self.server._playback_locks["phong_ngu"].locked())

            # Node in Room A attempts to start -> rejected with speaker_busy
            ws_pk_client = AsyncMessageSocket([
                json.dumps({"type": "start", "node_id": "SB_PK", "codec": "pcm", "sample_rate": 16000}),
            ], delay=0)
            await self.server._handle_client(ws_pk_client)
            suppressed = [m for m in ws_pk_client.sent if isinstance(m, dict) and m.get("type") == "suppressed"]
            self.assertTrue(len(suppressed) > 0)
            self.assertEqual(suppressed[0].get("reason"), "speaker_busy")

            # Node in Room B attempts to start -> accepted, recording starts!
            ws_pn_client = AsyncMessageSocket([
                json.dumps({"type": "start", "node_id": "SB_PN", "codec": "pcm", "sample_rate": 16000}),
            ], delay=0)
            await self.server._handle_client(ws_pn_client)
            pn_statuses = [m for m in ws_pn_client.sent if isinstance(m, dict) and m.get("state") == "recording"]
            self.assertTrue(len(pn_statuses) > 0)
            self.assertFalse(any(isinstance(m, dict) and m.get("type") == "suppressed" for m in ws_pn_client.sent))

        # After playback ends, Room A is no longer locked
        self.assertFalse(self.server._playback_locks["phong_khach"].locked())

    async def test_broadcast_pcm_stream_per_room_and_selective_busy(self):
        """Streaming audio to Room A locks Room A, notifies only Room A with speaker_busy."""
        ws_pk = AsyncMessageSocket([], delay=0)
        ws_pk.node_id = "SB_PK"
        ws_pk.has_speaker = True
        self.server._ws_nodes["SB_PK"] = ws_pk
        self.server._active_speakers.add(ws_pk)

        ws_pn = AsyncMessageSocket([], delay=0)
        ws_pn.node_id = "SB_PN"
        ws_pn.has_speaker = True
        self.server._ws_nodes["SB_PN"] = ws_pn
        self.server._active_speakers.add(ws_pn)

        # Send PCM stream to Room A (SB_PK only)
        pcm_data = b"\x00\x00" * 3200
        await self.server._broadcast_pcm_stream([ws_pk], pcm_data)

        # Check SB_PK received speaker_busy: True and False
        pk_busy = [m.get("busy") for m in ws_pk.sent if isinstance(m, dict) and m.get("type") == "speaker_busy"]
        self.assertEqual(pk_busy, [True, False])

        # Check SB_PN (Room B) never received speaker_busy
        pn_busy = [m for m in ws_pn.sent if isinstance(m, dict) and m.get("type") == "speaker_busy"]
        self.assertEqual(len(pn_busy), 0)

    async def test_stream_arbiter_direct_spatial_logic(self):
        """Direct unit test of StreamArbiter arbitration rules."""
        arbiter = StreamArbiter(self.gateway)

        # 1. 4 rooms with RMS 1500 (all >= 600 near-field threshold)
        arbiter.register_start("SB_PK")
        arbiter.add_rms("SB_PK", 1500)
        arbiter.register_start("SB_PN")
        arbiter.add_rms("SB_PN", 1500)
        arbiter.register_start("SB_PB")
        arbiter.add_rms("SB_PB", 1500)
        arbiter.register_start("SB_PT")
        arbiter.add_rms("SB_PT", 1500)

        for nid, room in [("SB_PK", "phong_khach"), ("SB_PN", "phong_ngu"),
                          ("SB_PB", "phong_bep"), ("SB_PT", "phong_tam")]:
            dom_nid, dom_room = arbiter.determine_dominant_room(nid)
            self.assertEqual(dom_nid, nid)
            self.assertEqual(dom_room, room)

        # 2. Near-field speaker in Room B (800 RMS) vs Room A (2000 RMS)
        # Even though Room A is 2.5x louder, Room B is >= 600 RMS so it's not a leak
        arbiter.active_streams.clear()
        arbiter.register_start("SB_PK")
        arbiter.add_rms("SB_PK", 2000)
        arbiter.register_start("SB_PN")
        arbiter.add_rms("SB_PN", 800)

        dom_nid, dom_room = arbiter.determine_dominant_room("SB_PN")
        self.assertEqual(dom_nid, "SB_PN")
        self.assertEqual(dom_room, "phong_ngu")

    async def test_two_unassigned_nodes_near_field_no_false_suppression(self):
        """Two nodes with room=None both speaking near-field (RMS 1200 and 1400) -> both succeed and do not falsely suppress."""
        # Unassigned nodes (not in self.nodes)
        ws_un1 = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_UN_1", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(1200),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        ws_un2 = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_UN_2", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(1400),
            json.dumps({"type": "stop"}),
        ], delay=0.02)

        await asyncio.gather(
            self.server._handle_client(ws_un1),
            self.server._handle_client(ws_un2),
        )

        for nid, ws in [("SB_UN_1", ws_un1), ("SB_UN_2", ws_un2)]:
            suppressed = [m for m in ws.sent if isinstance(m, dict) and m.get("type") == "suppressed"]
            self.assertEqual(len(suppressed), 0, f"{nid} should not be suppressed: {suppressed}")
            transcripts = [m for m in ws.sent if isinstance(m, dict) and m.get("type") == "transcript"]
            self.assertTrue(len(transcripts) > 0, f"{nid} missing transcript")
            self.assertTrue(transcripts[0].get("accepted"), f"{nid} transcript not accepted")

        # Also verify directly on StreamArbiter
        arbiter = StreamArbiter(self.gateway)
        arbiter.register_start("SB_UN_1")
        arbiter.add_rms("SB_UN_1", 1200)
        arbiter.register_start("SB_UN_2")
        arbiter.add_rms("SB_UN_2", 1400)
        dom1, room1 = arbiter.determine_dominant_room("SB_UN_1")
        dom2, room2 = arbiter.determine_dominant_room("SB_UN_2")
        self.assertEqual(dom1, "SB_UN_1")
        self.assertIsNone(room1)
        self.assertEqual(dom2, "SB_UN_2")
        self.assertIsNone(room2)

    async def test_unassigned_node_tts_does_not_lock_assigned_rooms(self):
        """Unassigned node TTS playback does not lock assigned rooms."""
        ws_un = AsyncMessageSocket([], delay=0)
        ws_un.node_id = "SB_UNASSIGNED"
        ws_un.has_speaker = True
        self.server._ws_nodes["SB_UNASSIGNED"] = ws_un
        self.server._active_speakers.add(ws_un)

        ws_pk = AsyncMessageSocket([], delay=0)
        ws_pk.node_id = "SB_PK"
        ws_pk.has_speaker = True
        self.server._ws_nodes["SB_PK"] = ws_pk
        self.server._active_speakers.add(ws_pk)

        # Stream PCM to unassigned node
        pcm_data = b"\x00\x00" * 3200
        await self.server._broadcast_pcm_stream([ws_un], pcm_data)

        # Assigned room (phong_khach) and global lock must not be locked
        self.assertFalse(self.server._playback_locks["phong_khach"].locked())
        self.assertFalse(self.server._default_playback_lock.locked())

        # Assigned room node (SB_PK) must not have received speaker_busy
        pk_busy = [m for m in ws_pk.sent if isinstance(m, dict) and m.get("type") == "speaker_busy"]
        self.assertEqual(len(pk_busy), 0)

        # Unassigned target received speaker_busy True then False
        un_busy = [m.get("busy") for m in ws_un.sent if isinstance(m, dict) and m.get("type") == "speaker_busy"]
        self.assertEqual(un_busy, [True, False])

    async def test_asr_timeout_rejection_after_5s(self):
        """ASR timeout rejection after 5s returns accepted=False with reason='asr_busy'."""
        calls = []
        real_timeout = asyncio.timeout

        def mock_timeout(delay):
            calls.append(delay)
            return real_timeout(0.01)

        def slow_asr(*args, **kwargs):
            import time
            time.sleep(0.05)
            return ("bật đèn", 0.95)

        self.gateway.asr.transcribe_with_confidence = slow_asr

        ws = AsyncMessageSocket([
            json.dumps({"type": "start", "node_id": "SB_PK", "codec": "pcm", "sample_rate": 16000}),
            make_pcm(1500),
            json.dumps({"type": "stop"}),
        ], delay=0.01)

        with unittest.mock.patch("asyncio.timeout", side_effect=mock_timeout):
            await self.server._handle_client(ws)

        # Confirm 5.0s timeout was configured
        self.assertIn(5.0, calls)

        # Confirm transcript rejection with reason asr_busy
        rejections = [
            m for m in ws.sent
            if isinstance(m, dict) and m.get("type") == "transcript" and not m.get("accepted")
        ]
        self.assertTrue(len(rejections) > 0)
        self.assertEqual(rejections[0].get("reason"), "asr_busy")


if __name__ == "__main__":
    unittest.main()
