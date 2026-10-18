import ctypes
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from gateway.core_v1.protocol import Frame, MessageType, ReplayWindow, RetryQueue, Reassembler, factory_id

ROOT = Path(__file__).resolve().parents[2]
KEY = bytes(range(32))


class ProtocolTest(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(factory_id(bytes.fromhex('7c9ebd42a153')), 'HC-7C9EBD42A153')
        with self.assertRaises(ValueError):
            factory_id(b'123')

    def test_vector_and_tampering(self):
        for v in json.loads((ROOT / 'protocol/test_vectors/hc_v1.json').read_text()):
            frame = Frame(MessageType(v['type']), v['message_id'], v['source'], v['destination'],
                          v['boot_id'], v['sequence'], v['config_rev'], bytes.fromhex(v['payload']), v['flags'])
            encoded = frame.encode(KEY)
            self.assertEqual(encoded.hex(), v['wire'])
            self.assertEqual(Frame.decode(encoded, KEY), frame)
            for index in range(len(encoded)):
                bad = bytearray(encoded)
                bad[index] ^= 1
                with self.assertRaises(ValueError):
                    Frame.decode(bytes(bad), KEY)
            with self.assertRaises(ValueError):
                Frame.decode(encoded + b'\0', KEY)
            with self.assertRaises(ValueError):
                Frame.decode(encoded, b'x' * 32)

    def test_limits(self):
        frame = Frame(MessageType.COMMAND, 1, 2, 3, 4, 5, 1, b'x' * 196)
        self.assertEqual(len(frame.encode(KEY)), 250)
        for bad in (b'x' * 197,):
            with self.assertRaises(ValueError):
                Frame(MessageType.COMMAND, 1, 2, 3, 4, 5, 1, bad).encode(KEY)

    def test_session_must_be_admitted_and_duplicates_do_not_advance(self):
        w = ReplayWindow()
        self.assertEqual(w.check(123, 1), 'SESSION_REQUIRED')
        w.admit(123)
        self.assertEqual(w.check(123, 1), 'NEW')
        self.assertEqual(w.check(123, 1), 'DUPLICATE')
        self.assertEqual(w.check(999, 2), 'SESSION_REQUIRED')
        self.assertEqual(w.check(123, 3), 'NEW')
        self.assertEqual(w.check(123, 2), 'NEW')
        self.assertEqual(w.check(123, 2), 'DUPLICATE')
        self.assertEqual(w.check(123, 100), 'NEW')
        self.assertEqual(w.check(123, 1), 'STALE')

    def test_retry_expiry_and_backpressure(self):
        q = RetryQueue(capacity=1, attempts=3, interval=0.2)
        q.add(1, b'command', now=0, ttl=1)
        with self.assertRaises(BufferError):
            q.add(2, b'other', now=0, ttl=1)
        self.assertEqual(q.due(0), [(1, b'command')])
        self.assertEqual(q.due(.1), [])
        self.assertEqual(q.due(.3), [(1, b'command')])
        self.assertEqual(q.due(.6), [(1, b'command')])
        self.assertEqual(q.due(1), [])
        self.assertEqual(q.timeouts, [1])
        q.add(2, b'other', now=2, ttl=1)
        q.ack(2)
        self.assertEqual(q.due(2), [])

    def test_reassembly_limits_overlap_and_timeout(self):
        r = Reassembler(max_size=512, timeout=2)
        self.assertIsNone(r.add(1, 0, 6, b'abc', now=0))
        self.assertIsNone(r.add(1, 0, 6, b'abc', now=.1))
        with self.assertRaises(ValueError):
            r.add(1, 0, 6, b'xbc', now=.2)
        self.assertEqual(r.add(1, 3, 6, b'def', now=.3), b'abcdef')
        with self.assertRaises(ValueError):
            r.add(2, 0, 513, b'a', now=1)
        self.assertIsNone(r.add(2, 0, 6, b'abc', now=1))
        self.assertIsNone(r.add(2, 3, 6, b'def', now=4))

    def test_c_codec_matches_python_and_rejects_malformed(self):
        source = ROOT / 'Firmware/firmware_esp/common/hc_core'
        with tempfile.TemporaryDirectory() as d:
            lib = Path(d) / 'libhc.so'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            str(source / 'hc_protocol.c'), '-I', str(source), '-o', str(lib)], check=True)
            c = ctypes.CDLL(str(lib))
            mac_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_size_t, ctypes.c_void_p)
            @mac_type
            def mac(_ctx, data, length, out):
                tag = hmac.digest(KEY, ctypes.string_at(data, length), 'sha256')[:16]
                ctypes.memmove(out, tag, 16)
                return 0
            generations=(ctypes.c_uint64*3)()
            c.hc_command_admit.argtypes=[ctypes.POINTER(ctypes.c_uint64),ctypes.c_uint8,ctypes.c_uint8,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64]
            self.assertEqual(c.hc_command_admit(generations,1,0,2,2000,1000),1)
            self.assertEqual(c.hc_command_admit(generations,1,1,1,2000,1001),0)
            self.assertEqual(c.hc_command_admit(generations,1,0,2,2000,1002),0)
            self.assertEqual(c.hc_command_admit(generations,2,1,3,999,1000),0)
            self.assertEqual(c.hc_command_admit(generations,4,1,3,2000,1000),0)
            self.assertEqual(c.hc_command_admit(generations,3,2,3,2000,1000),0)
            self.assertEqual(c.hc_command_admit(generations,3,1,3,32000,1000),0)
            c.hc_validate.argtypes = [ctypes.c_void_p, ctypes.c_size_t, mac_type, ctypes.c_void_p]
            for v in json.loads((ROOT / 'protocol/test_vectors/hc_v1.json').read_text()):
                raw = bytes.fromhex(v['wire'])
                self.assertEqual(c.hc_validate(raw, len(raw), mac, None), 0)
                for n in range(len(raw)):
                    self.assertNotEqual(c.hc_validate(raw, n, mac, None), 0)
                out = ctypes.create_string_buffer(250)
                c.hc_roundtrip.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, mac_type, ctypes.c_void_p]
                self.assertEqual(c.hc_roundtrip(raw, len(raw), out, mac, None), len(raw))
                self.assertEqual(out.raw[:len(raw)], raw)


if __name__ == '__main__':
    unittest.main()
