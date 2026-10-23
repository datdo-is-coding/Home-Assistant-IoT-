"""Device Lifecycle & Wire v2 Contract Layer for Gateway.

Follows the canonical specification in docs/contracts/device-lifecycle-v1.md.
Implements DTOs, parsing & validation, Wire v2 chunking & reassembly,
concurrency tracking, and LED pattern resolution.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import sqlite3
import threading
import time
import uuid
import zlib
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

WIRE_V2_MAX_FRAME_LEN: int = 250
WIRE_V2_MAX_CHUNK_LEN: int = 160
WIRE_V2_MAX_CONFIG_LEN: int = 4096
WIRE_V2_REASSEMBLY_TIMEOUT_SEC: float = 10.0
WIRE_V2_MAX_CONCURRENT_OPS_ACTIONBOX: int = 1
WIRE_V2_MAX_CONCURRENT_OPS_SUBBOX: int = 2

SUPPORTED_BOARD_MODELS: dict[str, int] = {
    "actionbox_v1": 2,
    "actionbox_v2": 3,
    "subbox_v1": 0,
}


class LifecycleState(str, Enum):
    UNCLAIMED = "unclaimed"
    CLAIMING = "claiming"
    CLAIMED = "claimed"
    RESETTING = "resetting"
    DECOMMISSIONED = "decommissioned"


class ConnectivityState(str, Enum):
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    ONLINE = "online"
    OFFLINE = "offline"


class FaultKind(str, Enum):
    NONE = "none"
    OVER_CURRENT = "over_current"
    OVER_TEMPERATURE = "over_temperature"
    RELAY_WELDED = "relay_welded"
    METER_FAULT = "meter_fault"
    SYSTEM_FAULT = "system_fault"


class OperationKind(str, Enum):
    IDENTIFY = "identify"
    REBOOT = "reboot"
    NETWORK_RESET = "network_reset"
    FACTORY_RESET = "factory_reset"
    REMOVE_FROM_HOME = "remove_from_home"
    CONFIGURE = "configure"
    CLAIM = "claim"


class OperationState(str, Enum):
    ACCEPTED = "accepted"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    AWAITING_RECONNECT = "awaiting_reconnect"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class LedPattern(str, Enum):
    FAULT = "fault"
    AWAITING_FACTORY_RESET = "awaiting_factory_reset"
    AWAITING_NETWORK_RESET = "awaiting_network_reset"
    CLAIMING = "claiming"
    CONFIG_APPLYING = "config_applying"
    UNCLAIMED = "unclaimed"
    IDENTIFY = "identify"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    READY = "ready"
    OFF = "off"


class DeviceLifecycleError(Exception):
    """Base exception for device lifecycle violations."""


class UnknownModelError(DeviceLifecycleError):
    """Raised when board model is unrecognized or unsupported."""


class UnsupportedProtocolError(DeviceLifecycleError):
    """Raised when protocol_version != 2."""


class OldEpochError(DeviceLifecycleError):
    """Raised when owner_epoch is older than current accepted epoch."""


class DuplicateUidError(DeviceLifecycleError):
    """Raised when device_uid already exists in the system."""


class StaleTimestampError(DeviceLifecycleError):
    """Raised when timestamp or expiry is in the past."""


class OversizeFragmentError(DeviceLifecycleError):
    """Raised when chunk fragment > 160 bytes."""


class OversizeConfigError(DeviceLifecycleError):
    """Raised when config size > 4096 bytes."""


class ReassemblyTimeoutError(DeviceLifecycleError):
    """Raised when config chunk reassembly exceeds 10 seconds."""


class CrcMismatchError(DeviceLifecycleError):
    """Raised when assembled CRC32 does not match expected CRC32."""


class ConcurrencyLimitError(DeviceLifecycleError):
    """Raised when concurrent config operations exceed limit."""


class ClaimError(DeviceLifecycleError):
    """Raised when a commissioning or claim operation is rejected."""

    def __init__(self, error_code: str, status_code: int = 400, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.message = message or error_code


class OperationError(DeviceLifecycleError):
    """Raised when a lifecycle operation is rejected or fails."""

    def __init__(self, error_code: str, status_code: int = 400, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.message = message or error_code


@dataclass
class CommissioningCandidate:
    device_uid: str
    board_model: str
    board_revision: str
    protocol_version: int
    capabilities: list[str]
    channel_count: int
    subbox_id: str | None = None
    rssi: int | None = None
    first_seen: float = 0.0
    last_seen: float = 0.0
    setup_window_expires_at: float = 0.0
    ttl_expires_at: float = 0.0
    setup_proof: str | None = None
    setup_session: int = 0
    state: str = "unclaimed"

    def is_expired(self, now_sec: float) -> bool:
        if self.ttl_expires_at > 0.0 and now_sec > self.ttl_expires_at:
            return True
        if self.setup_window_expires_at > 0.0 and now_sec > self.setup_window_expires_at:
            return True
        return False

    def to_api_dict(self) -> dict[str, Any]:
        """TUYỆT ĐỐI KHÔNG xuất trường setup_proof ra ngoài API."""
        return {
            "device_uid": self.device_uid,
            "board_model": self.board_model,
            "board_revision": self.board_revision,
            "protocol_version": self.protocol_version,
            "capabilities": list(self.capabilities),
            "channel_count": self.channel_count,
            "subbox_id": self.subbox_id,
            "rssi": self.rssi,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "setup_window_expires_at": self.setup_window_expires_at,
            "ttl_expires_at": self.ttl_expires_at,
            "state": self.state,
        }


@dataclass
class DeviceDescriptor:
    device_uid: str
    board_model: str
    board_revision: str
    protocol_version: int
    capabilities: list[str]
    home_id: str
    owner_epoch: int
    boot_id: str
    config_revision: int

    @property
    def channel_count(self) -> int:
        norm = self.board_model.strip().lower()
        return SUPPORTED_BOARD_MODELS.get(norm, -1)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        current_epoch: int = 1,
        existing_uids: set[str] | None = None,
    ) -> DeviceDescriptor:
        return parse_device_descriptor(data, current_epoch=current_epoch, existing_uids=existing_uids)


@dataclass
class Operation:
    kind: OperationKind
    operation_id: str
    device_uid: str
    state: OperationState
    idempotency_key: str | None = None
    requested_by: str | None = None
    target_subbox: str | None = None
    desired_revision: int = 1
    reported_revision: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    expires_at: float = 0.0
    metadata: dict[str, Any] | None = None

    def is_expired(self, now_sec: float) -> bool:
        return self.expires_at > 0.0 and now_sec > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value if isinstance(self.kind, Enum) else str(self.kind),
            "operation_id": self.operation_id,
            "device_uid": self.device_uid,
            "state": self.state.value if isinstance(self.state, Enum) else str(self.state),
            "idempotency_key": self.idempotency_key,
            "requested_by": self.requested_by,
            "target_subbox": self.target_subbox,
            "desired_revision": self.desired_revision,
            "reported_revision": self.reported_revision,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Operation:
        return Operation(
            kind=OperationKind(data["kind"]),
            operation_id=str(data["operation_id"]),
            device_uid=str(data["device_uid"]),
            state=OperationState(data["state"]),
            idempotency_key=data.get("idempotency_key"),
            requested_by=data.get("requested_by"),
            target_subbox=data.get("target_subbox"),
            desired_revision=int(data.get("desired_revision", 1)),
            reported_revision=int(data.get("reported_revision", 0)),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
            metadata=data.get("metadata"),
        )


@dataclass
class WireV2ConfigBegin:
    operation_id: str
    config_revision: int
    total_len: int
    chunk_count: int
    crc32: int


@dataclass
class WireV2ConfigChunk:
    operation_id: str
    chunk_index: int
    payload: bytes


@dataclass
class WireV2ConfigCommit:
    operation_id: str
    config_revision: int
    crc32: int


def parse_device_descriptor(
    data: dict[str, Any],
    current_epoch: int = 1,
    existing_uids: set[str] | None = None,
) -> DeviceDescriptor:
    raw_model = str(data.get("board_model", "")).strip().lower()
    if raw_model not in SUPPORTED_BOARD_MODELS:
        raise UnknownModelError(f"Unknown board model: {data.get('board_model')}")

    protocol_version = int(data.get("protocol_version", 0))
    if protocol_version != 2:
        raise UnsupportedProtocolError(f"Unsupported protocol version {protocol_version}, expected 2")

    owner_epoch = int(data.get("owner_epoch", 0))
    current_req = int(data.get("current_epoch", current_epoch))
    if owner_epoch < current_req:
        raise OldEpochError(f"Stale owner epoch {owner_epoch} < {current_req}")

    device_uid = str(data.get("device_uid", "")).strip()
    if not device_uid:
        raise DeviceLifecycleError("device_uid is required")
    if existing_uids and device_uid in existing_uids:
        raise DuplicateUidError(f"Duplicate device_uid: {device_uid}")
    if "existing_uids" in data and device_uid in data["existing_uids"]:
        raise DuplicateUidError(f"Duplicate device_uid in existing_uids: {device_uid}")

    return DeviceDescriptor(
        device_uid=device_uid,
        board_model=raw_model,
        board_revision=str(data.get("board_revision", "")),
        protocol_version=protocol_version,
        capabilities=list(data.get("capabilities", [])),
        home_id=str(data.get("home_id", "")),
        owner_epoch=owner_epoch,
        boot_id=str(data.get("boot_id", "")),
        config_revision=int(data.get("config_revision", 0)),
    )


def validate_operation_freshness(data: dict[str, Any], now_sec: float) -> None:
    expires_at = float(data.get("expires_at", 0.0))
    timestamp = float(data.get("timestamp", 0.0))
    if expires_at > 0.0 and now_sec > expires_at:
        raise StaleTimestampError(f"Operation expired: {expires_at} < now {now_sec}")
    if timestamp > 0.0 and (now_sec - timestamp) > 30.0:
        raise StaleTimestampError(f"Stale operation timestamp: {timestamp} (elapsed {now_sec - timestamp:.1f}s)")


def chunk_config(
    operation_id: str,
    config_revision: int,
    data: bytes,
    chunk_size: int = WIRE_V2_MAX_CHUNK_LEN,
) -> tuple[WireV2ConfigBegin, list[WireV2ConfigChunk], WireV2ConfigCommit]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    total_len = len(data)
    if total_len > WIRE_V2_MAX_CONFIG_LEN:
        raise OversizeConfigError(f"Config length {total_len} exceeds limit {WIRE_V2_MAX_CONFIG_LEN}")
    if chunk_size > WIRE_V2_MAX_CHUNK_LEN:
        raise OversizeFragmentError(f"Chunk size {chunk_size} exceeds limit {WIRE_V2_MAX_CHUNK_LEN}")

    crc = zlib.crc32(data) & 0xFFFFFFFF
    if total_len == 0:
        chunk_count = 1
        chunks = [WireV2ConfigChunk(operation_id=operation_id, chunk_index=0, payload=b"")]
    else:
        chunk_count = math.ceil(total_len / chunk_size)
        chunks = [
            WireV2ConfigChunk(
                operation_id=operation_id,
                chunk_index=i,
                payload=data[i * chunk_size : (i + 1) * chunk_size],
            )
            for i in range(chunk_count)
        ]

    begin = WireV2ConfigBegin(
        operation_id=operation_id,
        config_revision=config_revision,
        total_len=total_len,
        chunk_count=chunk_count,
        crc32=crc,
    )
    commit = WireV2ConfigCommit(
        operation_id=operation_id,
        config_revision=config_revision,
        crc32=crc,
    )
    return begin, chunks, commit


class WireV2Reassembler:
    def __init__(self, timeout_sec: float = WIRE_V2_REASSEMBLY_TIMEOUT_SEC):
        self.timeout_sec = timeout_sec
        self.begin: WireV2ConfigBegin | None = None
        self.chunks: dict[int, bytes] = {}
        self.start_time: float = 0.0

    def start(self, begin: WireV2ConfigBegin, now_sec: float) -> None:
        if begin.total_len > WIRE_V2_MAX_CONFIG_LEN:
            raise OversizeConfigError(f"Total config length {begin.total_len} exceeds {WIRE_V2_MAX_CONFIG_LEN}")
        self.begin = begin
        self.chunks.clear()
        self.start_time = now_sec

    def add_chunk(self, chunk: WireV2ConfigChunk, now_sec: float) -> None:
        if not self.begin:
            raise DeviceLifecycleError("Reassembler not started with Begin packet")
        if chunk.operation_id != self.begin.operation_id:
            raise DeviceLifecycleError(f"Operation ID mismatch: {chunk.operation_id} != {self.begin.operation_id}")
        if (now_sec - self.start_time) > self.timeout_sec:
            raise ReassemblyTimeoutError(
                f"Reassembly timed out ({(now_sec - self.start_time):.1f}s > {self.timeout_sec}s)"
            )
        if chunk.chunk_index < 0:
            raise DeviceLifecycleError("Negative chunk index")
        if len(chunk.payload) > WIRE_V2_MAX_CHUNK_LEN:
            raise OversizeFragmentError(f"Chunk size {len(chunk.payload)} exceeds max {WIRE_V2_MAX_CHUNK_LEN}")
        if chunk.chunk_index >= self.begin.chunk_count:
            raise DeviceLifecycleError(f"Chunk index {chunk.chunk_index} out of bounds ({self.begin.chunk_count})")

        self.chunks[chunk.chunk_index] = chunk.payload

    def commit(self, commit: WireV2ConfigCommit, now_sec: float) -> bytes:
        if not self.begin:
            raise DeviceLifecycleError("Reassembler not started with Begin packet")
        if commit.operation_id != self.begin.operation_id:
            raise DeviceLifecycleError(f"Commit op_id mismatch: {commit.operation_id} != {self.begin.operation_id}")
        if commit.config_revision != self.begin.config_revision:
            raise DeviceLifecycleError(
                f"Commit config revision mismatch: {commit.config_revision} != {self.begin.config_revision}"
            )
        if (now_sec - self.start_time) > self.timeout_sec:
            raise ReassemblyTimeoutError("Reassembly timed out before commit")
        if len(self.chunks) < self.begin.chunk_count:
            missing = set(range(self.begin.chunk_count)) - set(self.chunks.keys())
            raise DeviceLifecycleError(f"Missing chunks: {sorted(missing)}")

        assembled = b"".join(self.chunks[i] for i in range(self.begin.chunk_count))
        if len(assembled) != self.begin.total_len:
            raise DeviceLifecycleError(f"Assembled size {len(assembled)} != expected {self.begin.total_len}")

        calc_crc = zlib.crc32(assembled) & 0xFFFFFFFF
        if calc_crc != self.begin.crc32:
            raise CrcMismatchError(f"Calculated CRC 0x{calc_crc:08X} != begin CRC 0x{self.begin.crc32:08X}")
        if calc_crc != commit.crc32:
            raise CrcMismatchError(f"Calculated CRC 0x{calc_crc:08X} != commit CRC 0x{commit.crc32:08X}")

        return assembled


class WireV2ConcurrencyManager:
    def __init__(self) -> None:
        self._active: dict[str, set[str]] = {}

    def get_limit(self, board_model: str) -> int:
        norm = board_model.strip().lower()
        if "subbox" in norm:
            return WIRE_V2_MAX_CONCURRENT_OPS_SUBBOX
        return WIRE_V2_MAX_CONCURRENT_OPS_ACTIONBOX

    def acquire(self, device_uid: str, board_model: str, operation_id: str) -> None:
        limit = self.get_limit(board_model)
        current = self._active.setdefault(device_uid, set())
        if operation_id in current:
            return
        if len(current) >= limit:
            raise ConcurrencyLimitError(
                f"Concurrency limit ({limit}) reached for {device_uid} ({board_model})"
            )
        current.add(operation_id)

    def release(self, device_uid: str, operation_id: str) -> None:
        if device_uid in self._active:
            self._active[device_uid].discard(operation_id)
            if not self._active[device_uid]:
                del self._active[device_uid]


def resolve_led_pattern(
    lifecycle: LifecycleState,
    connectivity: ConnectivityState,
    fault: FaultKind = FaultKind.NONE,
    active_op_kind: OperationKind | None = None,
    active_op_state: OperationState | None = None,
    elapsed_in_state_ms: int = 0,
) -> LedPattern:
    # 1. Fault has highest priority
    if fault != FaultKind.NONE:
        return LedPattern.FAULT

    # 2. Awaiting reset confirmation (max 5s)
    if active_op_state == OperationState.AWAITING_CONFIRMATION:
        if active_op_kind == OperationKind.FACTORY_RESET:
            return LedPattern.AWAITING_FACTORY_RESET
        if active_op_kind == OperationKind.NETWORK_RESET:
            return LedPattern.AWAITING_NETWORK_RESET

    # 3. Setup / Claim / Lifecycle
    if active_op_kind == OperationKind.CONFIGURE and active_op_state == OperationState.RUNNING:
        return LedPattern.CONFIG_APPLYING
    if lifecycle == LifecycleState.CLAIMING:
        return LedPattern.CLAIMING
    if lifecycle in (LifecycleState.UNCLAIMED, LifecycleState.DECOMMISSIONED):
        return LedPattern.UNCLAIMED

    # 4. Identify (max 15s)
    if active_op_kind == OperationKind.IDENTIFY and active_op_state == OperationState.RUNNING:
        if elapsed_in_state_ms < 15000:
            return LedPattern.IDENTIFY

    # 5. Connectivity (when claimed)
    if connectivity == ConnectivityState.CONNECTING:
        return LedPattern.CONNECTING
    if connectivity in (ConnectivityState.OFFLINE, ConnectivityState.UNKNOWN):
        return LedPattern.OFFLINE

    # 6. Ready (Claimed & Online)
    if lifecycle == LifecycleState.CLAIMED and connectivity == ConnectivityState.ONLINE:
        if elapsed_in_state_ms < 2000:
            return LedPattern.READY
        return LedPattern.OFF

    return LedPattern.OFF


def status_led_is_active(pattern: LedPattern, elapsed_ms: int) -> bool:
    if elapsed_ms < 0:
        elapsed_ms = 0

    if pattern == LedPattern.FAULT:
        phase = elapsed_ms % 3600
        return (phase < 1600) and ((phase % 400) < 200)

    if pattern == LedPattern.AWAITING_FACTORY_RESET:
        phase = elapsed_ms % 3000
        return (phase < 2000) and ((phase % 400) < 200)

    if pattern == LedPattern.AWAITING_NETWORK_RESET:
        phase = elapsed_ms % 2200
        return (phase < 1200) and ((phase % 400) < 200)

    if pattern == LedPattern.CLAIMING:
        return (elapsed_ms % 500) < 250

    if pattern == LedPattern.CONFIG_APPLYING:
        phase = elapsed_ms % 1600
        return (phase < 800) and ((phase % 400) < 200)

    if pattern == LedPattern.UNCLAIMED:
        return (elapsed_ms % 1000) < 500

    if pattern == LedPattern.IDENTIFY:
        phase = elapsed_ms % 3000
        return (phase < 1200) and ((phase % 400) < 200)

    if pattern == LedPattern.OFFLINE:
        phase = elapsed_ms % 2800
        return (phase < 800) and ((phase % 400) < 200)

    if pattern == LedPattern.CONNECTING:
        phase = elapsed_ms % 1400
        return (phase < 400) and ((phase % 400) < 200)

    if pattern == LedPattern.READY:
        return elapsed_ms < 2000

    return False


class LifecycleOperationLedger:
    """Lưu trữ bền vững các thao tác vòng đời trên SQLite."""

    def __init__(self, db_path: str = "registry.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lifecycle_operations (
                    operation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    device_uid TEXT NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    requested_by TEXT,
                    target_subbox TEXT,
                    desired_revision INTEGER DEFAULT 1,
                    reported_revision INTEGER DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lifecycle_ops_dev_state ON lifecycle_operations(device_uid, state)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_ops_idempotency ON lifecycle_operations(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_ops_active_claim ON lifecycle_operations(device_uid) WHERE state IN ('accepted', 'running')"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_tombstones (
                    device_uid TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    offline_removed INTEGER DEFAULT 0,
                    owner_epoch INTEGER DEFAULT 1,
                    notice TEXT,
                    created_at REAL NOT NULL,
                    metadata TEXT
                )
                """
            )
            conn.commit()

    def _row_to_operation(self, row: sqlite3.Row) -> Operation:
        meta = None
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                meta = {}
        return Operation(
            kind=OperationKind(row["kind"]),
            operation_id=row["operation_id"],
            device_uid=row["device_uid"],
            state=OperationState(row["state"]),
            idempotency_key=row["idempotency_key"],
            requested_by=row["requested_by"],
            target_subbox=row["target_subbox"],
            desired_revision=row["desired_revision"],
            reported_revision=row["reported_revision"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            metadata=meta,
        )

    def record_operation(self, op: Operation) -> None:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO lifecycle_operations (
                        operation_id, kind, device_uid, state, idempotency_key,
                        requested_by, target_subbox, desired_revision, reported_revision,
                        error_code, error_message, created_at, updated_at, expires_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        kind=excluded.kind,
                        device_uid=excluded.device_uid,
                        state=excluded.state,
                        idempotency_key=excluded.idempotency_key,
                        requested_by=excluded.requested_by,
                        target_subbox=excluded.target_subbox,
                        desired_revision=excluded.desired_revision,
                        reported_revision=excluded.reported_revision,
                        error_code=excluded.error_code,
                        error_message=excluded.error_message,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at,
                        expires_at=excluded.expires_at,
                        metadata=excluded.metadata
                    """,
                    (
                        op.operation_id,
                        op.kind.value if isinstance(op.kind, Enum) else str(op.kind),
                        op.device_uid,
                        op.state.value if isinstance(op.state, Enum) else str(op.state),
                        op.idempotency_key,
                        op.requested_by,
                        op.target_subbox,
                        op.desired_revision,
                        op.reported_revision,
                        op.error_code,
                        op.error_message,
                        op.created_at,
                        op.updated_at,
                        op.expires_at,
                        json.dumps(op.metadata) if op.metadata else None,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                logging.warning(
                    "Integrity constraint violation recording operation %s for %s (state=%s): %s",
                    op.operation_id, op.device_uid, op.state, exc
                )
                raise

    def get_by_id(self, operation_id: str) -> Operation | None:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM lifecycle_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row:
                return self._row_to_operation(row)
        return None

    def get_by_idempotency_key(self, idempotency_key: str) -> Operation | None:
        if not idempotency_key:
            return None
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM lifecycle_operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row:
                return self._row_to_operation(row)
        return None

    def get_active_claim(self, device_uid: str, now_sec: float | None = None) -> Operation | None:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_operations
                WHERE device_uid = ? AND kind = 'claim' AND state IN ('accepted', 'running')
                ORDER BY created_at DESC
                """,
                (device_uid,),
            ).fetchall()
            for r in rows:
                op = self._row_to_operation(r)
                if now_sec is not None and op.is_expired(now_sec):
                    self.update_operation_state(
                        op.operation_id,
                        OperationState.TIMED_OUT,
                        error_code="TIMEOUT",
                        error_message="Claim operation timed out waiting for device ACK",
                        now_sec=now_sec,
                    )
                    continue
                return op
        return None

    def update_operation_state(
        self,
        operation_id: str,
        state: OperationState | str,
        error_code: str | None = None,
        error_message: str | None = None,
        reported_revision: int | None = None,
        metadata: dict | None = None,
        now_sec: float | None = None,
    ) -> Operation | None:
        st_val = state.value if isinstance(state, Enum) else str(state)
        now = now_sec if now_sec is not None else time.time()
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM lifecycle_operations WHERE operation_id = ?",
                (operation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            up_error_code = error_code if error_code is not None else row["error_code"]
            up_error_msg = error_message if error_message is not None else row["error_message"]
            up_rep_rev = reported_revision if reported_revision is not None else row["reported_revision"]
            up_meta = json.dumps(metadata) if metadata is not None else row["metadata"]

            conn.execute(
                """
                UPDATE lifecycle_operations
                SET state = ?, error_code = ?, error_message = ?, reported_revision = ?, metadata = ?, updated_at = ?
                WHERE operation_id = ?
                """,
                (st_val, up_error_code, up_error_msg, up_rep_rev, up_meta, now, operation_id),
            )
            conn.commit()
        return self.get_by_id(operation_id)

    def get_active_operation(self, device_uid: str, now_sec: float | None = None) -> Operation | None:
        now = now_sec if now_sec is not None else time.time()
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_operations
                WHERE device_uid = ? AND state IN ('accepted', 'awaiting_confirmation', 'running', 'awaiting_reconnect')
                ORDER BY created_at DESC
                """,
                (device_uid,),
            ).fetchall()
            for r in rows:
                op = self._row_to_operation(r)
                if op.is_expired(now):
                    self.update_operation_state(
                        op.operation_id,
                        OperationState.TIMED_OUT,
                        error_code="TIMEOUT",
                        error_message="Operation timed out",
                        now_sec=now,
                    )
                    continue
                return op
        return None

    def record_tombstone(
        self,
        device_uid: str,
        status: str = "removed_from_home",
        offline_removed: bool = False,
        owner_epoch: int = 1,
        notice: str | None = None,
        metadata: dict | None = None,
        created_at: float | None = None,
    ) -> None:
        now = created_at if created_at is not None else time.time()
        meta_str = json.dumps(metadata) if metadata else None
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute(
                """
                INSERT INTO device_tombstones (device_uid, status, offline_removed, owner_epoch, notice, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_uid) DO UPDATE SET
                    status=excluded.status,
                    offline_removed=excluded.offline_removed,
                    owner_epoch=excluded.owner_epoch,
                    notice=excluded.notice,
                    created_at=excluded.created_at,
                    metadata=excluded.metadata
                """,
                (device_uid, status, 1 if offline_removed else 0, owner_epoch, notice, now, meta_str),
            )
            conn.commit()

    def clear_tombstone(self, device_uid: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("DELETE FROM device_tombstones WHERE device_uid = ?", (str(device_uid),))
            conn.commit()
        return True

    def get_tombstone(self, device_uid: str) -> dict | None:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM device_tombstones WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
            if row:
                res = dict(row)
                if res.get("metadata"):
                    try:
                        res["metadata"] = json.loads(res["metadata"])
                    except Exception:
                        pass
                return res
        return None

    def check_timeouts(self, now_sec: float) -> list[Operation]:
        timed_out = []
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_operations
                WHERE state IN ('accepted', 'awaiting_confirmation', 'running', 'awaiting_reconnect') AND expires_at > 0 AND expires_at < ?
                """,
                (now_sec,),
            ).fetchall()
            for r in rows:
                timed_out.append(self._row_to_operation(r))
        for op in timed_out:
            self.update_operation_state(
                op.operation_id,
                OperationState.TIMED_OUT,
                error_code="TIMEOUT",
                error_message="Operation timed out waiting for device ACK",
                now_sec=now_sec,
            )
        return timed_out

    def list_operations(self, now_sec: float | None = None) -> list[Operation]:
        if now_sec is not None:
            self.check_timeouts(now_sec)
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM lifecycle_operations ORDER BY created_at DESC").fetchall()
            return [self._row_to_operation(r) for r in rows]


class DeviceLifecycleManager:
    """Điều phối vòng đời thiết bị: Discovery candidates, Claim transactions, ACK reconciliation."""

    def __init__(
        self,
        db_path: str = "registry.db",
        registry: Any = None,
        mqtt: Any = None,
        discovery: Any = None,
        broadcaster: Callable[[str, dict[str, Any]], None] | None = None,
        auth: Any = None,
    ) -> None:
        self._lock = threading.Lock()
        self.db_path = db_path
        self.ledger = LifecycleOperationLedger(db_path=db_path)
        self.registry = registry
        self.mqtt = mqtt
        self.discovery = discovery
        self.broadcaster = broadcaster
        self.auth = auth
        if self.auth is None and self.registry and hasattr(self.registry, "auth"):
            self.auth = self.registry.auth
        self.candidates: dict[str, CommissioningCandidate] = {}
        self._claim_tasks: dict[str, asyncio.Task] = {}

    def clear_tombstone(self, device_uid: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("DELETE FROM device_tombstones WHERE device_uid = ?", (str(device_uid),))
            conn.commit()
        return True

    def add_candidate(
        self,
        candidate_data: CommissioningCandidate | dict[str, Any],
        now_sec: float | None = None,
    ) -> CommissioningCandidate:
        now = now_sec if now_sec is not None else time.time()
        if isinstance(candidate_data, CommissioningCandidate):
            cand = candidate_data
            if cand.first_seen <= 0.0:
                cand.first_seen = now
            cand.last_seen = now
            if cand.ttl_expires_at <= 0.0:
                cand.ttl_expires_at = now + 30.0
            if cand.setup_window_expires_at <= 0.0:
                cand.setup_window_expires_at = now + 180.0
            self.candidates[cand.device_uid] = cand
            return cand

        d = candidate_data
        uid = str(d.get("device_uid") or d.get("device_id") or d.get("id") or d.get("mac") or d.get("serial", "")).strip()
        board_model = str(d.get("board_model") or d.get("hardware") or "actionbox_v2").strip().lower()
        board_rev = str(d.get("board_revision", "rev_b")).strip()
        proto_ver = int(d.get("protocol_version", 2))
        caps = list(d.get("capabilities", []))
        if not caps:
            caps = ["relay_3ch" if ("s3" in board_model or "v2" in board_model) else "relay_2ch"]
        ch_count = int(d.get("channel_count", 0)) or (3 if "relay_3ch" in caps else 2)
        subbox_id = d.get("subbox_id") or d.get("parent_id")
        rssi = d.get("rssi")
        proof = d.get("setup_proof") or d.get("setup_code") or d.get("proof")

        existing = self.candidates.get(uid)
        if existing and d.get("setup_session", 0) != existing.setup_session:
            existing = None
        first_seen = existing.first_seen if existing else now
        setup_win = existing.setup_window_expires_at if existing else (now + 180.0)

        if "setup_remaining_ms" in d:
            setup_win = min(setup_win, now + d["setup_remaining_ms"] / 1000.0)

        cand = CommissioningCandidate(
            device_uid=uid,
            board_model=board_model,
            board_revision=board_rev,
            protocol_version=proto_ver,
            capabilities=caps,
            channel_count=ch_count,
            subbox_id=subbox_id,
            rssi=rssi,
            first_seen=first_seen,
            last_seen=now,
            setup_window_expires_at=setup_win,
            ttl_expires_at=now + 30.0,
            setup_session=d.get("setup_session", 0),
            setup_proof=proof if proof is not None else (existing.setup_proof if existing else None),
            state="unclaimed",
        )
        self.candidates[uid] = cand
        return cand

    def get_candidates(self, now_sec: float | None = None) -> list[CommissioningCandidate]:
        now = now_sec if now_sec is not None else time.time()
        return [c for c in self.candidates.values() if not c.is_expired(now)]

    def get_candidate(self, device_uid: str, now_sec: float | None = None) -> CommissioningCandidate | None:
        cand = self.candidates.get(device_uid)
        if not cand:
            return None
        now = now_sec if now_sec is not None else time.time()
        if cand.is_expired(now):
            return None
        return cand

    def remove_candidate(self, device_uid: str) -> None:
        self.candidates.pop(device_uid, None)

    def start_claim(
        self,
        user: dict[str, Any],
        request: dict[str, Any],
        now: float,
    ) -> Operation:
        # 1. Check user permission: admin only
        if not user or user.get("role") != "admin":
            raise ClaimError("ADMIN_REQUIRED", 403, "Admin privileges required to claim device")

        # 2. Idempotency: return existing operation if idempotency_key matches
        idempotency_key = request.get("idempotency_key")
        if idempotency_key:
            existing = self.ledger.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        with self._lock:
            # 3. Candidate check: must be seen and unexpired
            device_uid = request.get("candidate_id") or request.get("device_uid")
            if not device_uid:
                raise ClaimError("INVALID_REQUEST", 400, "candidate_id or device_uid is required")

            if idempotency_key:
                existing = self.ledger.get_by_idempotency_key(idempotency_key)
                if existing:
                    return existing

            candidate = self.candidates.get(device_uid)
            if not candidate or candidate.is_expired(now):
                raise ClaimError("UNSEEN_CANDIDATE", 400, f"Candidate {device_uid} not seen or expired")

            if candidate.setup_session and request.get("subbox_id") not in (None, "", candidate.subbox_id):
                raise ClaimError("WRONG_SUBBOX", 409, "Chọn đúng SubBox đang phát hiện thiết bị")

            # 4. Proof check: if candidate has setup_proof, request must match
            if candidate.setup_proof:
                proof = request.get("setup_proof")
                if not proof or str(proof).strip() != str(candidate.setup_proof).strip():
                    raise ClaimError("INVALID_PROOF", 400, "Invalid setup proof provided")

            # 4b. Capability check: channel count mismatch
            req_channels = request.get("channels")
            if isinstance(req_channels, (dict, list)) and candidate.channel_count > 0:
                if len(req_channels) > candidate.channel_count:
                    raise ClaimError("CAPABILITY_MISMATCH", 400, f"Device supports {candidate.channel_count} channels, requested {len(req_channels)}")

            if candidate.setup_session:
                if req_channels is not None and (not isinstance(req_channels, dict) or
                        any(key not in ("ch1", "ch2", "ch3") for key in req_channels)):
                    raise ClaimError("INVALID_CHANNELS", 400, "Kênh thiết bị không hợp lệ")
                for value in (req_channels or {}).values():
                    kind = value.get("type", "switch") if isinstance(value, dict) else value
                    if kind not in ("light", "fan", "switch", "air_conditioner", "socket"):
                        raise ClaimError("INVALID_CHANNELS", 400, "Loại thiết bị không được hỗ trợ")

            # 5. Check active claim in progress
            active_op = self.ledger.get_active_claim(device_uid, now_sec=now)
            if active_op and not active_op.is_expired(now):
                raise ClaimError("CLAIM_IN_PROGRESS", 409, f"Claim operation {active_op.operation_id} already in progress for {device_uid}")

            reserved = [item for item in self.ledger.list_operations(now_sec=now)
                        if item.kind == OperationKind.CLAIM and item.state in (OperationState.ACCEPTED, OperationState.RUNNING)
                        and item.device_uid not in self.registry.data.get("nodes", {})] if self.registry else []

            # 6. Check SubBox slots: max 4 ActionBoxes per SubBox
            target_subbox = request.get("subbox_id") or candidate.subbox_id
            if target_subbox and self.registry:
                subbox_nodes = [
                    n for n in self.registry.data.get("nodes", {}).values()
                    if (n.get("subbox_id") == target_subbox or n.get("parent_subbox") == target_subbox)
                ]
                if len(subbox_nodes) + sum(item.target_subbox == target_subbox for item in reserved) >= 4 and device_uid not in self.registry.data.get("nodes", {}):
                    raise ClaimError("SUBBOX_FULL", 409, f"SubBox '{target_subbox}' already has 4 ActionBoxes")

            # 6b. Check Room slots: max 4 ActionBoxes per Room
            room_id = request.get("room_id") or request.get("room")
            if room_id and self.registry:
                from registry_manager import slug
                room_s = slug(room_id)
                room_nodes = [n for n in self.registry.data.get("nodes", {}).values() if n.get("room") == room_s]
                if len(room_nodes) + sum(slug((item.metadata or {}).get("room_id") or (item.metadata or {}).get("room", "")) == room_s for item in reserved) >= 4 and device_uid not in self.registry.data.get("nodes", {}):
                    raise ClaimError("ROOM_FULL", 409, f"Room '{room_s}' already has 4 nodes")

            # 7. Valid: create operation with state 'accepted' and deadline now + 120s
            op_id = f"op_claim_{uuid.uuid4().hex[:12]}"
            expires_at = now + 120.0
            safe_meta = {k: v for k, v in request.items() if k not in ("setup_proof", "proof", "setup_code", "setup_session")}
            safe_meta["setup_session"] = candidate.setup_session
            op = Operation(
                kind=OperationKind.CLAIM,
                operation_id=op_id,
                device_uid=device_uid,
                state=OperationState.ACCEPTED,
                idempotency_key=idempotency_key,
                requested_by=user.get("username") or user.get("id", "admin"),
                target_subbox=target_subbox,
                desired_revision=int(request.get("config_revision", 1)),
                reported_revision=0,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
                metadata=safe_meta,
            )
            try:
                self.ledger.record_operation(op)
            except sqlite3.IntegrityError:
                raise ClaimError("CLAIM_IN_PROGRESS", 409, f"Claim operation already in progress for {device_uid}")

            candidate.state = "claiming"

        # Dispatch config via MQTT if available
        if self.mqtt:
            try:
                self._schedule_claim(op, candidate, request)
            except RuntimeError:
                pass

        return op

    def _schedule_claim(self, op: Operation, candidate: CommissioningCandidate, request: dict) -> None:
        if op.operation_id in self._claim_tasks:
            return
        task = asyncio.get_running_loop().create_task(self._dispatch_claim_config(op, candidate, request))
        self._claim_tasks[op.operation_id] = task
        task.add_done_callback(lambda _: self._claim_tasks.pop(op.operation_id, None))

    def resume_claims(self, subbox_id: str) -> None:
        # Called by the SubBox heartbeat, including after Gateway restart.
        now = time.time()
        for op in self.ledger.list_operations(now_sec=now):
            meta = op.metadata or {}
            if (op.kind != OperationKind.CLAIM or op.target_subbox != subbox_id
                    or op.state not in (OperationState.ACCEPTED, OperationState.RUNNING)
                    or not meta.get("setup_session")):
                continue
            candidate = CommissioningCandidate(device_uid=op.device_uid, board_model="actionbox_v2",
                board_revision="", protocol_version=3, capabilities=["relay_3ch"], channel_count=3,
                subbox_id=subbox_id, setup_session=meta["setup_session"])
            self._schedule_claim(op, candidate, meta)

    async def _dispatch_claim_config(self, op: Operation, candidate: CommissioningCandidate, request: dict[str, Any]) -> None:
        op.state = OperationState.RUNNING
        self.ledger.update_operation_state(op.operation_id, OperationState.RUNNING)
        if not self.mqtt:
            return
        target_subbox = op.target_subbox
        from registry_manager import slug
        import hashlib
        room_key = slug(request.get("room_id") or request.get("room", "livingroom"))
        if len(room_key.encode("utf-8")) > 15:
            room_key = "r_" + hashlib.sha256(room_key.encode("utf-8")).hexdigest()[:12]
        payload = {
            "room_key": room_key,
            "op_id": op.operation_id,
            "device_uid": op.device_uid,
            "revision": op.desired_revision,
            "owner_epoch": 1,
            "setup_session": candidate.setup_session,
            "room_id": request.get("room_id") or request.get("room", "livingroom"),
            "channels": request.get("channels", {}),
            "name": request.get("name", ""),
        }
        if candidate.setup_session:
            # Names/aliases stay in the durable operation; the radio only needs channel types.
            payload["channels"] = {key: {"type": value.get("type", "switch") if isinstance(value, dict) else value}
                                   for key, value in (request.get("channels") or {}).items()}
            payload.pop("name", None)
            payload.pop("room_id", None)
        try:
            if target_subbox:
                sent = await self.mqtt.publish(f"home/subbox/{target_subbox}/command", {
                    "cmd": "claim", **payload
                }, qos=1)
            else:
                sent = await self.mqtt.publish(f"home/devices/{op.device_uid}/config/desired", payload, qos=1)
            if not sent:
                raise RuntimeError("MQTT enqueue failed")
            if candidate.setup_session and target_subbox:
                # Radio or MQTT ACK loss must reuse the same durable operation.
                while True:
                    await asyncio.sleep(5)
                    current = self.ledger.get_by_id(op.operation_id)
                    if not current or current.state not in (OperationState.ACCEPTED, OperationState.RUNNING):
                        break
                    if current.is_expired(time.time()):
                        self.ledger.check_timeouts(time.time())
                        break
                    await self.mqtt.publish(f"home/subbox/{target_subbox}/command", {"cmd": "claim", **payload}, qos=1)

        except Exception:
            self.ledger.update_operation_state(op.operation_id, OperationState.FAILED,
                error_code="DISPATCH_FAILED", error_message="Không gửi được đăng ký tới SubBox. Kiểm tra kết nối Gateway.")
            candidate.state = "unclaimed"

    async def on_device_applied(
        self,
        device_uid: str,
        owner_epoch: int = 1,
        operation_id: str | None = None,
        config_revision: int = 1,
        now_sec: float | None = None,
        confirmed_subbox: str | None = None,
    ) -> Operation | None:
        now = now_sec if now_sec is not None else time.time()
        op = None
        if operation_id:
            op = self.ledger.get_by_id(operation_id)
            if op and op.device_uid != device_uid:
                logger.warning(
                    f"Rejected applied ACK: operation {operation_id} device mismatch ({op.device_uid} != {device_uid})"
                )
                return None
            if not op:
                return None
        if not op:
            op = self.ledger.get_active_claim(device_uid, now_sec=now)

        if self.registry and device_uid not in self.registry.data.get("nodes", {}):
            if not op or op.state not in (OperationState.ACCEPTED, OperationState.RUNNING) or op.is_expired(now):
                logger.warning(f"Rejected unsolicited applied ACK from unverified device {device_uid}")
                return None

        if op and (op.kind != OperationKind.CLAIM or op.state not in (OperationState.ACCEPTED, OperationState.RUNNING)
                   or op.is_expired(now) or config_revision != op.desired_revision):
            return None

        if op and (op.metadata or {}).get("setup_session") and confirmed_subbox != op.target_subbox:
            return None

        # Update registry node state to claimed, READY, online = True
        node = None
        if self.registry:
            meta = (op.metadata if op else None) or {}
            node = self.registry.data.get("nodes", {}).get(device_uid)
            if not node or (op and device_uid in self.registry.data.get("pending", {})):
                channels = meta.get("channels")
                if isinstance(channels, list):
                    rl1 = channels[0] if len(channels) > 0 else "light"
                    rl2 = channels[1] if len(channels) > 1 else "fan"
                    rl3 = channels[2] if len(channels) > 2 else None
                elif isinstance(channels, dict):
                    rl1 = channels.get("ch1", "light")
                    rl2 = channels.get("ch2", "fan")
                    rl3 = channels.get("ch3")
                else:
                    rl1, rl2, rl3 = "light", "fan", None

                def device_type(value, default):
                    return value.get("type", value.get("device_type", default)) if isinstance(value, dict) else value
                rl1, rl2, rl3 = device_type(rl1, "light"), device_type(rl2, "fan"), device_type(rl3, "switch")
                self.registry.provision_node(
                    mac_or_id=device_uid,
                    room=meta.get("room_id") or meta.get("room", "livingroom"),
                    rl1=rl1,
                    rl2=rl2,
                    rl3=rl3,
                    name=meta.get("name"),
                    subbox_id=op.target_subbox if op else meta.get("subbox_id"),
                )
                node = self.registry.data.get("nodes", {}).get(device_uid)

            if not node:
                if op:
                    op.state = OperationState.FAILED
                    op.error_code = "PROVISION_FAILED"
                    op.error_message = "Failed to provision node into registry"
                    op.updated_at = now
                    self.ledger.update_operation_state(
                        op.operation_id,
                        OperationState.FAILED,
                        error_code="PROVISION_FAILED",
                        error_message="Failed to provision node into registry",
                        now_sec=now,
                    )
                return op

            for key, value in (meta.get("channels") or {}).items() if isinstance(meta.get("channels"), dict) else []:
                if isinstance(value, dict) and key in node.get("channels", {}):
                    node["channels"][key].update({k: v for k, v in value.items() if k in ("name", "aliases")})
            node["status"] = "online"
            node["state"] = "READY"
            if "security" not in node:
                node["security"] = {}
            node["security"]["state"] = "READY"
            node["security"]["lifecycle_state"] = "claimed"
            node["config_revision"] = config_revision
            node["owner_epoch"] = owner_epoch
            if op and op.target_subbox:
                node["subbox_id"] = op.target_subbox
            self.registry.save(changed_node=device_uid)

        # Clear tombstone upon successful recommission
        self.clear_tombstone(device_uid)
        if node:
            node_mac = node.get("address", {}).get("mac") or node.get("mac")
            if node_mac and str(node_mac).upper() != str(device_uid).upper():
                self.clear_tombstone(str(node_mac).upper())
                self.clear_tombstone(str(node_mac).lower())

        if op:
            op.state = OperationState.SUCCEEDED
            op.reported_revision = config_revision
            op.updated_at = now
            self.ledger.update_operation_state(
                op.operation_id,
                OperationState.SUCCEEDED,
                reported_revision=config_revision,
                now_sec=now,
            )

        # Remove candidate from candidates and registry pending
        self.remove_candidate(device_uid)
        if self.registry and "pending" in self.registry.data:
            self.registry.data["pending"].pop(device_uid, None)
            for k, p in list(self.registry.data["pending"].items()):
                if p.get("device_id") == device_uid or p.get("mac") == device_uid:
                    self.registry.data["pending"].pop(k, None)
            self.registry.save()

        # Call HA discovery
        if self.discovery and hasattr(self.discovery, "publish_ha_discovery_for_node"):
            res = self.discovery.publish_ha_discovery_for_node(device_uid)
            if asyncio.iscoroutine(res):
                await res

        # Broadcast SSE event device_claimed
        if self.broadcaster:
            self.broadcaster("device_claimed", {
                "device_uid": device_uid,
                "operation_id": op.operation_id if op else None,
                "owner_epoch": owner_epoch,
                "config_revision": config_revision,
                "state": "succeeded",
            })

        return op

    def start_operation(
        self,
        user: dict[str, Any],
        device_uid: str,
        kind: OperationKind | str,
        idempotency_key: str | None = None,
        confirmation: bool = False,
        now_sec: float | None = None,
    ) -> Operation:
        now = now_sec if now_sec is not None else time.time()

        # 1. Admin permission check
        if not user or user.get("role") != "admin":
            raise OperationError("ADMIN_REQUIRED", 403, "Admin privileges required for device lifecycle operations")

        # 2. Device existence check in registry
        if not self.registry or "nodes" not in getattr(self.registry, "data", {}) or device_uid not in self.registry.data["nodes"]:
            raise OperationError("DEVICE_NOT_FOUND", 404, f"Device '{device_uid}' not found in registry")
        node = self.registry.data["nodes"][device_uid]

        # 3. Kind validation & normalization
        if isinstance(kind, str):
            try:
                op_kind = OperationKind(kind.strip().lower())
            except ValueError:
                raise OperationError("INVALID_KIND", 400, f"Unsupported operation kind: '{kind}'")
        elif isinstance(kind, OperationKind):
            op_kind = kind
        else:
            raise OperationError("INVALID_KIND", 400, f"Invalid operation kind: {kind}")

        allowed_kinds = {
            OperationKind.IDENTIFY,
            OperationKind.REBOOT,
            OperationKind.NETWORK_RESET,
            OperationKind.FACTORY_RESET,
            OperationKind.REMOVE_FROM_HOME,
        }
        if op_kind not in allowed_kinds:
            raise OperationError("INVALID_KIND", 400, f"Operation kind '{op_kind.value}' is not supported via start_operation")

        # 4. Idempotency check
        if idempotency_key:
            existing = self.ledger.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        with self._lock:
            # Recheck idempotency with lock
            if idempotency_key:
                existing = self.ledger.get_by_idempotency_key(idempotency_key)
                if existing:
                    return existing

            # 5. Concurrency check
            active_op = self.ledger.get_active_operation(device_uid, now_sec=now)
            pending_confirm = False
            if active_op and not active_op.is_expired(now):
                if active_op.state == OperationState.AWAITING_CONFIRMATION and active_op.kind == op_kind and confirmation:
                    pending_confirm = True
                    op = active_op
                else:
                    raise OperationError(
                        "OPERATION_IN_PROGRESS",
                        409,
                        f"Active operation '{active_op.operation_id}' ({active_op.kind.value}) is already in progress for device '{device_uid}'",
                    )
            else:
                op = None

            target_subbox = node.get("subbox_id") or node.get("parent_subbox")
            requested_by = user.get("username") or str(user.get("id", "admin"))

            # 6. Branch by kind
            if op_kind == OperationKind.IDENTIFY:
                expires_at = now + 15.0
                op = Operation(
                    kind=OperationKind.IDENTIFY,
                    operation_id=f"op_ident_{uuid.uuid4().hex[:12]}",
                    device_uid=device_uid,
                    state=OperationState.RUNNING,
                    idempotency_key=idempotency_key,
                    requested_by=requested_by,
                    target_subbox=target_subbox,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                    metadata={"duration_sec": 15.0, "warning": "Blink indicator only, no relay toggle"},
                )
                self.ledger.record_operation(op)
                self._dispatch_op(op, OperationKind.IDENTIFY, extra={"duration": 15})

            elif op_kind == OperationKind.REBOOT:
                expires_at = now + 30.0
                op = Operation(
                    kind=OperationKind.REBOOT,
                    operation_id=f"op_reboot_{uuid.uuid4().hex[:12]}",
                    device_uid=device_uid,
                    state=OperationState.RUNNING,
                    idempotency_key=idempotency_key,
                    requested_by=requested_by,
                    target_subbox=target_subbox,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                    metadata={
                        "warning": "Power to connected loads may be temporarily interrupted during reboot",
                        "reconnect_timeout_sec": 120.0,
                    },
                )
                self.ledger.record_operation(op)
                self._dispatch_op(op, OperationKind.REBOOT)
                self.ledger.update_operation_state(
                    op.operation_id,
                    OperationState.AWAITING_RECONNECT,
                    now_sec=now,
                )
                op.state = OperationState.AWAITING_RECONNECT

            elif op_kind == OperationKind.NETWORK_RESET:
                if not confirmation:
                    op = Operation(
                        kind=OperationKind.NETWORK_RESET,
                        operation_id=f"op_netreset_{uuid.uuid4().hex[:12]}",
                        device_uid=device_uid,
                        state=OperationState.AWAITING_CONFIRMATION,
                        idempotency_key=idempotency_key,
                        requested_by=requested_by,
                        target_subbox=target_subbox,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + 30.0,
                        metadata={"warning": "Clears network settings. Confirmation required within 30s."},
                    )
                    self.ledger.record_operation(op)
                else:
                    if pending_confirm and op:
                        op.state = OperationState.RUNNING
                        op.updated_at = now
                        op.expires_at = now + 30.0
                        self.ledger.update_operation_state(op.operation_id, OperationState.RUNNING, now_sec=now)
                    else:
                        op = Operation(
                            kind=OperationKind.NETWORK_RESET,
                            operation_id=f"op_netreset_{uuid.uuid4().hex[:12]}",
                            device_uid=device_uid,
                            state=OperationState.RUNNING,
                            idempotency_key=idempotency_key,
                            requested_by=requested_by,
                            target_subbox=target_subbox,
                            created_at=now,
                            updated_at=now,
                            expires_at=now + 30.0,
                            metadata={"confirmed": True},
                        )
                        self.ledger.record_operation(op)
                    self._dispatch_op(op, OperationKind.NETWORK_RESET)

            elif op_kind == OperationKind.FACTORY_RESET:
                if not confirmation:
                    op = Operation(
                        kind=OperationKind.FACTORY_RESET,
                        operation_id=f"op_factreset_{uuid.uuid4().hex[:12]}",
                        device_uid=device_uid,
                        state=OperationState.AWAITING_CONFIRMATION,
                        idempotency_key=idempotency_key,
                        requested_by=requested_by,
                        target_subbox=target_subbox,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + 30.0,
                        metadata={"warning": "Factory reset will wipe device configuration. Requires confirmation within 30s."},
                    )
                    self.ledger.record_operation(op)
                else:
                    if pending_confirm and op:
                        op.state = OperationState.RUNNING
                        op.updated_at = now
                        op.expires_at = now + 60.0
                        self.ledger.update_operation_state(op.operation_id, OperationState.RUNNING, now_sec=now)
                    else:
                        op = Operation(
                            kind=OperationKind.FACTORY_RESET,
                            operation_id=f"op_factreset_{uuid.uuid4().hex[:12]}",
                            device_uid=device_uid,
                            state=OperationState.RUNNING,
                            idempotency_key=idempotency_key,
                            requested_by=requested_by,
                            target_subbox=target_subbox,
                            created_at=now,
                            updated_at=now,
                            expires_at=now + 60.0,
                            metadata={"confirmed": True},
                        )
                        self.ledger.record_operation(op)

                    curr_epoch = int(node.get("owner_epoch", node.get("epoch", 1)))
                    new_epoch = curr_epoch + 1
                    self._dispatch_op(op, OperationKind.FACTORY_RESET, extra={"owner_epoch": new_epoch})

                    node["owner_epoch"] = new_epoch

                    if self.auth and hasattr(self.auth, "revoke_device_grants"):
                        self.auth.revoke_device_grants(device_uid)

                    node["status"] = "unclaimed"
                    node["state"] = "unclaimed"
                    if "security" not in node:
                        node["security"] = {}
                    node["security"]["lifecycle_state"] = "resetting"
                    node["security"]["state"] = "unclaimed"
                    self.registry.save(changed_node=device_uid)

                    self._handle_subbox_children(device_uid)

            elif op_kind == OperationKind.REMOVE_FROM_HOME:
                self._handle_subbox_children(device_uid)

                if self.auth and hasattr(self.auth, "revoke_device_grants"):
                    self.auth.revoke_device_grants(device_uid)

                is_online = (node.get("status") == "online" or node.get("state") == "READY")

                if is_online:
                    self._dispatch_op(
                        Operation(
                            kind=OperationKind.FACTORY_RESET,
                            operation_id=f"op_unpair_{uuid.uuid4().hex[:8]}",
                            device_uid=device_uid,
                            state=OperationState.RUNNING,
                        ),
                        OperationKind.FACTORY_RESET,
                        extra={"action": "unpair"},
                    )
                    self.registry.delete_node(device_uid)
                    self._trigger_remove_ha(device_uid)

                    self.ledger.record_tombstone(
                        device_uid=device_uid,
                        status="removed_from_home",
                        offline_removed=False,
                        owner_epoch=node.get("owner_epoch", 1),
                        notice="Device removed while online",
                        metadata={"offline_removed": False},
                        created_at=now,
                    )

                    op = Operation(
                        kind=OperationKind.REMOVE_FROM_HOME,
                        operation_id=f"op_rem_{uuid.uuid4().hex[:12]}",
                        device_uid=device_uid,
                        state=OperationState.SUCCEEDED,
                        idempotency_key=idempotency_key,
                        requested_by=requested_by,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + 120.0,
                        metadata={"status": "removed_from_home", "offline_removed": False, "auth_revoked": True},
                    )
                    self.ledger.record_operation(op)

                else:
                    notice = "Device was offline when removed from home. Physical button reset is required on the physical device before it can be commissioned again."
                    self.ledger.record_tombstone(
                        device_uid=device_uid,
                        status="removed_from_home",
                        offline_removed=True,
                        owner_epoch=node.get("owner_epoch", 1),
                        notice=notice,
                        metadata={"offline_removed": True, "notice": notice},
                        created_at=now,
                    )
                    self.registry.delete_node(device_uid)
                    self._trigger_remove_ha(device_uid)

                    op = Operation(
                        kind=OperationKind.REMOVE_FROM_HOME,
                        operation_id=f"op_rem_{uuid.uuid4().hex[:12]}",
                        device_uid=device_uid,
                        state=OperationState.SUCCEEDED,
                        idempotency_key=idempotency_key,
                        requested_by=requested_by,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + 120.0,
                        metadata={
                            "status": "removed_from_home",
                            "offline_removed": True,
                            "notice": notice,
                            "auth_revoked": True,
                        },
                    )
                    self.ledger.record_operation(op)

                if self.broadcaster:
                    self.broadcaster("device_deleted", {
                        "device_id": device_uid,
                        "node_id": device_uid,
                        "offline_removed": not is_online,
                    })

            return op

    def reconcile_operation(self, operation_id: str, now_sec: float | None = None) -> Operation:
        now = now_sec if now_sec is not None else time.time()
        op = self.ledger.get_by_id(operation_id)
        if not op:
            raise OperationError("OPERATION_NOT_FOUND", 404, f"Operation '{operation_id}' not found")
        if op.state in (OperationState.ACCEPTED, OperationState.AWAITING_CONFIRMATION, OperationState.RUNNING, OperationState.AWAITING_RECONNECT):
            if op.is_expired(now):
                op = self.ledger.update_operation_state(
                    op.operation_id,
                    OperationState.TIMED_OUT,
                    error_code="TIMEOUT",
                    error_message=f"Operation {op.kind.value} timed out",
                    now_sec=now,
                )
                if self.registry and "nodes" in getattr(self.registry, "data", {}):
                    node = self.registry.data["nodes"].get(op.device_uid)
                    if node and op.kind == OperationKind.FACTORY_RESET and node.get("status") != "unclaimed":
                        node["status"] = "unclaimed"
                        self.registry.save(changed_node=op.device_uid)
        return op

    def get_operation(self, operation_id: str, now_sec: float | None = None) -> Operation | None:
        try:
            return self.reconcile_operation(operation_id, now_sec=now_sec)
        except OperationError:
            return None

    def on_device_reconnected(self, device_uid: str, now_sec: float | None = None) -> Operation | None:
        now = now_sec if now_sec is not None else time.time()
        active_op = self.ledger.get_active_operation(device_uid, now_sec=now)
        if active_op and active_op.kind == OperationKind.REBOOT:
            if active_op.state in (OperationState.AWAITING_RECONNECT, OperationState.RUNNING):
                op = self.ledger.update_operation_state(
                    active_op.operation_id,
                    OperationState.SUCCEEDED,
                    now_sec=now,
                )
                if self.broadcaster:
                    self.broadcaster("device_rebooted", {
                        "device_uid": device_uid,
                        "operation_id": active_op.operation_id,
                        "state": "succeeded",
                    })
                return op
        return None

    def on_operation_ack(
        self,
        device_uid: str,
        operation_id: str | None = None,
        status: str = "succeeded",
        error_code: str | None = None,
        error_message: str | None = None,
        now_sec: float | None = None,
    ) -> Operation | None:
        now = now_sec if now_sec is not None else time.time()
        op = None
        if operation_id:
            op = self.ledger.get_by_id(operation_id)
        if not op:
            op = self.ledger.get_active_operation(device_uid, now_sec=now)
        if not op:
            return None

        st = OperationState.SUCCEEDED if status.lower() in ("succeeded", "ok", "success") else OperationState.FAILED
        res = self.ledger.update_operation_state(
            op.operation_id,
            st,
            error_code=error_code,
            error_message=error_message,
            now_sec=now,
        )
        if self.broadcaster:
            self.broadcaster("operation_updated", {
                "operation_id": op.operation_id,
                "device_uid": device_uid,
                "state": st.value,
                "error_code": error_code,
            })
        return res

    def _handle_subbox_children(self, subbox_uid: str) -> list[str]:
        if not self.registry or "nodes" not in getattr(self.registry, "data", {}):
            return []
        affected = []
        for nid, child in self.registry.data["nodes"].items():
            if nid != subbox_uid and (child.get("subbox_id") == subbox_uid or child.get("parent_subbox") == subbox_uid):
                child["status"] = "offline"
                child["state"] = "reconnecting"
                if "security" not in child:
                    child["security"] = {}
                child["security"]["state"] = "reconnecting"
                child["security"]["route_status"] = "needs_route_recovery"
                affected.append(nid)
        if affected:
            self.registry.save()
            logger.info(
                f"SubBox '{subbox_uid}' action affected {len(affected)} child ActionBoxes: {affected}. "
                "Marked offline/reconnecting (route recovery required)."
            )
            if self.broadcaster:
                self.broadcaster("subbox_route_lost", {
                    "subbox_id": subbox_uid,
                    "affected_children": affected,
                })
        return affected

    def _dispatch_op(self, op: Operation, kind: OperationKind, extra: dict | None = None) -> None:
        if not self.mqtt:
            return
        payload = {
            "cmd": kind.value if isinstance(kind, Enum) else str(kind),
            "operation_id": op.operation_id,
            "device_uid": op.device_uid,
            **(extra or {})
        }
        topic = f"smarthome/cmd/{op.device_uid}/operation"
        target_subbox = op.target_subbox
        subbox_topic = f"home/subbox/{target_subbox}/command" if target_subbox else None
        subbox_payload = {
            "cmd": kind.value if isinstance(kind, Enum) else str(kind),
            "operation_id": op.operation_id,
            "node_id": op.device_uid,
            **(extra or {})
        } if target_subbox else None

        async def _do_send():
            try:
                res = self.mqtt.publish(topic, payload)
                if asyncio.iscoroutine(res):
                    await res
                if subbox_topic and subbox_payload:
                    res2 = self.mqtt.publish(subbox_topic, subbox_payload)
                    if asyncio.iscoroutine(res2):
                        await res2
            except Exception as e:
                logger.warning(f"Error publishing MQTT operation {op.operation_id}: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_send())
        except RuntimeError:
            try:
                res = self.mqtt.publish(topic, payload)
                if asyncio.iscoroutine(res):
                    try:
                        asyncio.run(res)
                    except Exception:
                        pass
                if subbox_topic and subbox_payload:
                    res2 = self.mqtt.publish(subbox_topic, subbox_payload)
                    if asyncio.iscoroutine(res2):
                        try:
                            asyncio.run(res2)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Sync MQTT publish failed for {op.operation_id}: {e}")

    _dispatch_mqtt_operation = _dispatch_op

    def _trigger_remove_ha(self, device_uid: str) -> None:
        if not self.discovery or not hasattr(self.discovery, "remove_ha_discovery_for_node"):
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.discovery.remove_ha_discovery_for_node(device_uid))
        except RuntimeError:
            try:
                res = self.discovery.remove_ha_discovery_for_node(device_uid)
                if asyncio.iscoroutine(res):
                    try:
                        asyncio.run(res)
                    except Exception:
                        pass
            except Exception:
                pass

    def reconcile_operations(self, now_sec: float) -> list[Operation]:
        return self.ledger.check_timeouts(now_sec)

    def list_operations(self, now_sec: float | None = None) -> list[Operation]:
        return self.ledger.list_operations(now_sec=now_sec)
