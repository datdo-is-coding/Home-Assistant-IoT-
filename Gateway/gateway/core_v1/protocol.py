"""HC v1: bounded authenticated frames. Admission is not inferred from a boot ID."""
from dataclasses import dataclass
from enum import IntEnum
import hmac
import struct


class MessageType(IntEnum):
    HELLO = 1
    IDENTITY_CHALLENGE = 2
    IDENTITY_RESPONSE = 3
    PAIR_REQUEST = 4
    PAIR_ACCEPT = 5
    PAIR_REJECT = 6
    HEARTBEAT = 7
    CAPABILITY_REPORT = 8
    CONFIG_PUSH = 9
    CONFIG_ACK = 10
    COMMAND = 11
    COMMAND_ACK = 12
    STATE_REPORT = 13
    TELEMETRY_REPORT = 14
    EVENT_REPORT = 15
    ROOM_SNAPSHOT = 16
    STATE_SYNC_REQUEST = 17
    ERROR_REPORT = 18
    OTA_OFFER = 19
    OTA_START = 20
    OTA_PROGRESS = 21
    OTA_RESULT = 22
    OTA_ABORT = 23
    UNPAIR = 24
    FACTORY_RESET_REQUEST = 25
    OTA_CHUNK = 26
    OTA_CHUNK_ACK = 27
    FRAGMENT = 28
    CHANNEL_PROBE = 29
    MAINTENANCE = 30
    MAINTENANCE_ACK = 31


HEADER = struct.Struct('<2sBBBBQIIQII')
MAX_PAYLOAD = 196


def factory_id(base_mac: bytes) -> str:
    if len(base_mac) != 6:
        raise ValueError('base MAC must be six bytes')
    return 'HC-' + base_mac.hex().upper()


@dataclass(frozen=True)
class Frame:
    type: MessageType
    message_id: int
    source: int
    destination: int
    boot_id: int
    sequence: int
    config_rev: int
    payload: bytes = b''
    flags: int = 0

    def encode(self, key: bytes) -> bytes:
        if len(key) != 32 or len(self.payload) > MAX_PAYLOAD or self.flags & ~3:
            raise ValueError('key, payload or flags invalid')
        if not self.message_id or not self.boot_id or not self.sequence:
            raise ValueError('message, boot and sequence must be nonzero')
        try:
            packet = HEADER.pack(b'HC', 1, MessageType(self.type), self.flags, len(self.payload),
                                 self.message_id, self.source, self.destination, self.boot_id,
                                 self.sequence, self.config_rev) + self.payload
        except (struct.error, OverflowError) as e:
            raise ValueError('invalid frame fields') from e
        return packet + hmac.digest(key, packet, 'sha256')[:16]

    @classmethod
    def decode(cls, data: bytes, key: bytes):
        if len(key) != 32 or not 54 <= len(data) <= 250:
            raise ValueError('invalid frame length or key')
        magic, version, typ, flags, length, mid, src, dst, boot, seq, rev = HEADER.unpack_from(data)
        if magic != b'HC' or version != 1 or flags & ~3 or len(data) != 54 + length:
            raise ValueError('invalid header')
        if not hmac.compare_digest(hmac.digest(key, data[:-16], 'sha256')[:16], data[-16:]):
            raise ValueError('authentication failed')
        if not mid or not boot or not seq:
            raise ValueError('zero message, boot or sequence')
        return cls(MessageType(typ), mid, src, dst, boot, seq, rev, data[38:-16], flags)


class ReplayWindow:
    def __init__(self):
        self.boot = None
        self.high = 0
        self.mask = 0

    def admit(self, boot: int):
        if not 0 < boot < 2**64:
            raise ValueError('invalid boot')
        if self.boot != boot:
            self.boot, self.high, self.mask = boot, 0, 0

    def check(self, boot: int, seq: int) -> str:
        if boot != self.boot:
            return 'SESSION_REQUIRED'
        if not 0 < seq < 2**32:
            return 'STALE'
        if seq > self.high:
            self.mask = ((self.mask << min(seq - self.high, 32)) | 1) & 0xffffffff
            self.high = seq
            return 'NEW'
        delta = self.high - seq
        if delta >= 32:
            return 'STALE'
        bit = 1 << delta
        if self.mask & bit:
            return 'DUPLICATE'
        self.mask |= bit
        return 'NEW'


class RetryQueue:
    def __init__(self, capacity=16, attempts=3, interval=.25):
        if capacity < 1 or attempts < 1 or interval <= 0:
            raise ValueError('invalid retry policy')
        self.capacity, self.attempts, self.interval = capacity, attempts, interval
        self.pending = {}
        self.timeouts = []

    def add(self, mid, payload, *, now, ttl):
        if mid in self.pending or ttl <= 0 or ttl > 30:
            raise ValueError('duplicate ID or invalid TTL')
        if len(self.pending) >= self.capacity:
            raise BufferError('command queue full')
        self.pending[mid] = [payload, now, now + ttl, 0]

    def ack(self, mid):
        self.pending.pop(mid, None)

    def due(self, now):
        self.timeouts = []
        result = []
        for mid, item in list(self.pending.items()):
            payload, next_try, expiry, attempts = item
            if now >= expiry or (now >= next_try and attempts >= self.attempts):
                self.timeouts.append(mid)
                del self.pending[mid]
            elif now >= next_try:
                result.append((mid, payload))
                item[1], item[3] = now + self.interval, attempts + 1
        return result


class Reassembler:
    """One bounded transfer per peer; conflicting overlapping bytes are rejected."""
    def __init__(self, max_size=4096, timeout=5):
        self.max_size, self.timeout = max_size, timeout
        self.mid = None
        self.started = 0

    def add(self, mid, offset, total, data, *, now):
        if not data or not 0 < total <= self.max_size or offset < 0 or offset + len(data) > total:
            raise ValueError('invalid fragment bounds')
        if self.mid is not None and now - self.started >= self.timeout:
            self.mid = None
        if self.mid is None:
            self.mid, self.started = mid, now
            self.data, self.seen = bytearray(total), bytearray(total)
        if self.mid != mid:
            raise BufferError('another transfer is active')
        if len(self.data) != total:
            raise ValueError('inconsistent total')
        for i, value in enumerate(data, offset):
            if self.seen[i] and self.data[i] != value:
                raise ValueError('conflicting fragment')
        self.data[offset:offset + len(data)] = data
        self.seen[offset:offset + len(data)] = b'\1' * len(data)
        if all(self.seen):
            self.mid = None
            return bytes(self.data)
        return None
