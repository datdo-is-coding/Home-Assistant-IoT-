"""Unit tests for Device Lifecycle Contract Layer in Gateway."""
import json
from pathlib import Path
import sys
import unittest

GATEWAY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(GATEWAY_DIR / "gateway"))

from gateway.device_lifecycle import (
    ConnectivityState,
    FaultKind,
    LedPattern,
    LifecycleState,
    OperationKind,
    OperationState,
    SUPPORTED_BOARD_MODELS,
    WIRE_V2_MAX_CHUNK_LEN,
    WIRE_V2_MAX_CONFIG_LEN,
    ConcurrencyLimitError,
    CrcMismatchError,
    DeviceDescriptor,
    DeviceLifecycleError,
    DuplicateUidError,
    OldEpochError,
    Operation,
    OversizeConfigError,
    OversizeFragmentError,
    ReassemblyTimeoutError,
    StaleTimestampError,
    UnknownModelError,
    UnsupportedProtocolError,
    WireV2ConfigBegin,
    WireV2ConfigChunk,
    WireV2ConfigCommit,
    WireV2ConcurrencyManager,
    WireV2Reassembler,
    chunk_config,
    parse_device_descriptor,
    resolve_led_pattern,
    status_led_is_active,
    validate_operation_freshness,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests/fixtures/device_lifecycle"


class TestDeviceLifecycleContract(unittest.TestCase):
    def load_fixture(self, name: str) -> dict:
        fixture_path = FIXTURES_DIR / name
        self.assertTrue(fixture_path.is_file(), f"Fixture file not found: {fixture_path}")
        with fixture_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def test_fixtures_exist(self):
        expected_fixtures = [
            "actionbox_v1_2ch.json",
            "actionbox_v2_3ch.json",
            "subbox_0relay.json",
            "unknown_model.json",
            "unsupported_protocol.json",
            "old_epoch.json",
            "duplicate_uid.json",
            "stale_timestamp.json",
            "oversize_fragment.json",
        ]
        for name in expected_fixtures:
            data = self.load_fixture(name)
            self.assertIsInstance(data, dict)

    def test_actionbox_v1_exposes_two_channels(self):
        data = self.load_fixture("actionbox_v1_2ch.json")
        desc = parse_device_descriptor(data)
        self.assertEqual(desc.channel_count, 2)
        self.assertEqual(desc.board_model, "actionbox_v1")
        self.assertEqual(desc.protocol_version, 2)
        self.assertIn("relay", desc.capabilities)

    def test_v2_exposes_three_channels(self):
        data = self.load_fixture("actionbox_v2_3ch.json")
        desc = parse_device_descriptor(data)
        self.assertEqual(desc.channel_count, 3)
        self.assertEqual(desc.board_model, "actionbox_v2")
        self.assertEqual(desc.protocol_version, 2)
        self.assertIn("voice", desc.capabilities)

    def test_subbox_exposes_zero_channels(self):
        data = self.load_fixture("subbox_0relay.json")
        desc = parse_device_descriptor(data)
        self.assertEqual(desc.channel_count, 0)
        self.assertEqual(desc.board_model, "subbox_v1")
        self.assertEqual(desc.protocol_version, 2)

    def test_unknown_model_rejected(self):
        data = self.load_fixture("unknown_model.json")
        with self.assertRaises(UnknownModelError):
            parse_device_descriptor(data)

    def test_unsupported_protocol_rejected(self):
        data = self.load_fixture("unsupported_protocol.json")
        with self.assertRaises(UnsupportedProtocolError):
            parse_device_descriptor(data)

    def test_old_epoch_rejected(self):
        data = self.load_fixture("old_epoch.json")
        with self.assertRaises(OldEpochError):
            parse_device_descriptor(data)

    def test_duplicate_uid_rejected(self):
        data = self.load_fixture("duplicate_uid.json")
        with self.assertRaises(DuplicateUidError):
            parse_device_descriptor(data)

        # Also test with existing_uids set
        with self.assertRaises(DuplicateUidError):
            parse_device_descriptor(
                {"device_uid": "ab2_001", "board_model": "actionbox_v2", "protocol_version": 2, "owner_epoch": 1},
                existing_uids={"ab2_001"}
            )

    def test_stale_timestamp_rejected(self):
        data = self.load_fixture("stale_timestamp.json")
        now_sec = 1600000030.0  # past expires_at (1600000015.0)
        with self.assertRaises(StaleTimestampError):
            validate_operation_freshness(data, now_sec)

        op = Operation.from_dict(data)
        self.assertTrue(op.is_expired(now_sec))

    def test_oversize_fragment_rejected(self):
        data = self.load_fixture("oversize_fragment.json")
        oversize_payload = bytes.fromhex(data["chunk_payload_hex"])
        self.assertGreater(len(oversize_payload), WIRE_V2_MAX_CHUNK_LEN)

        # Test chunker rejection of oversize chunk_size
        with self.assertRaises(OversizeFragmentError):
            chunk_config("op1", 1, b"hello", chunk_size=200)

        # Test reassembler rejection of oversize fragment
        reassembler = WireV2Reassembler()
        begin = WireV2ConfigBegin("op1", 1, len(oversize_payload), 1, 0)
        reassembler.start(begin, now_sec=100.0)
        with self.assertRaises(OversizeFragmentError):
            reassembler.add_chunk(WireV2ConfigChunk("op1", 0, oversize_payload), now_sec=101.0)

    def test_oversize_config_rejected(self):
        huge_data = b"x" * (WIRE_V2_MAX_CONFIG_LEN + 1)
        with self.assertRaises(OversizeConfigError):
            chunk_config("op_huge", 1, huge_data)

        reassembler = WireV2Reassembler()
        begin = WireV2ConfigBegin("op_huge", 1, WIRE_V2_MAX_CONFIG_LEN + 10, 30, 0)
        with self.assertRaises(OversizeConfigError):
            reassembler.start(begin, now_sec=100.0)

    def test_chunking_and_reassembly_crc32(self):
        # 1000 bytes payload requires ceil(1000/160) = 7 chunks
        sample_config = b"ActionBox_Config_Payload_Bytes_1234567890_" * 25
        self.assertEqual(len(sample_config), 1050)

        begin, chunks, commit = chunk_config("op_cfg_01", config_revision=5, data=sample_config)
        self.assertEqual(begin.total_len, 1050)
        self.assertEqual(begin.chunk_count, 7)
        self.assertEqual(len(chunks), 7)
        self.assertEqual(commit.crc32, begin.crc32)

        # Verify all chunk sizes <= 160
        for chunk in chunks:
            self.assertLessEqual(len(chunk.payload), WIRE_V2_MAX_CHUNK_LEN)

        # Reassemble
        reassembler = WireV2Reassembler()
        reassembler.start(begin, now_sec=10.0)
        for chunk in chunks:
            reassembler.add_chunk(chunk, now_sec=11.0)

        result = reassembler.commit(commit, now_sec=12.0)
        self.assertEqual(result, sample_config)

    def test_reassembly_crc_mismatch(self):
        sample = b"valid_config_data"
        begin, chunks, commit = chunk_config("op_crc", 1, sample)
        # Corrupt one byte in chunk 0
        corrupted_payload = bytearray(chunks[0].payload)
        corrupted_payload[0] ^= 0xFF
        corrupted_chunk = WireV2ConfigChunk("op_crc", 0, bytes(corrupted_payload))

        reassembler = WireV2Reassembler()
        reassembler.start(begin, now_sec=10.0)
        reassembler.add_chunk(corrupted_chunk, now_sec=11.0)
        with self.assertRaises(CrcMismatchError):
            reassembler.commit(commit, now_sec=12.0)

    def test_reassembly_timeout(self):
        sample = b"timeout_test"
        begin, chunks, commit = chunk_config("op_to", 1, sample)

        reassembler = WireV2Reassembler(timeout_sec=10.0)
        reassembler.start(begin, now_sec=100.0)
        # Receive chunk past 10 seconds timeout
        with self.assertRaises(ReassemblyTimeoutError):
            reassembler.add_chunk(chunks[0], now_sec=111.0)

    def test_concurrency_limits(self):
        cm = WireV2ConcurrencyManager()
        # ActionBox limit is 1
        cm.acquire("ab_01", "actionbox_v2", "op_1")
        with self.assertRaises(ConcurrencyLimitError):
            cm.acquire("ab_01", "actionbox_v2", "op_2")

        # After releasing op_1, op_2 can be acquired
        cm.release("ab_01", "op_1")
        cm.acquire("ab_01", "actionbox_v2", "op_2")

        # SubBox limit is 2
        cm.acquire("sub_01", "subbox_v1", "op_s1")
        cm.acquire("sub_01", "subbox_v1", "op_s2")
        with self.assertRaises(ConcurrencyLimitError):
            cm.acquire("sub_01", "subbox_v1", "op_s3")

        cm.release("sub_01", "op_s1")
        cm.acquire("sub_01", "subbox_v1", "op_s3")

    def test_led_pattern_priorities(self):
        # 1. Fault overrides everything
        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.RELAY_WELDED,
            active_op_kind=OperationKind.IDENTIFY,
            active_op_state=OperationState.RUNNING,
        )
        self.assertEqual(p, LedPattern.FAULT)

        # 2. Awaiting reset confirmation overrides setup/claim, identify, connectivity
        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.NONE,
            active_op_kind=OperationKind.FACTORY_RESET,
            active_op_state=OperationState.AWAITING_CONFIRMATION,
        )
        self.assertEqual(p, LedPattern.AWAITING_FACTORY_RESET)

        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.NONE,
            active_op_kind=OperationKind.NETWORK_RESET,
            active_op_state=OperationState.AWAITING_CONFIRMATION,
        )
        self.assertEqual(p, LedPattern.AWAITING_NETWORK_RESET)

        # 3. Setup / Claim / Lifecycle overrides identify and connectivity
        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.NONE,
            active_op_kind=OperationKind.CONFIGURE,
            active_op_state=OperationState.RUNNING,
        )
        self.assertEqual(p, LedPattern.CONFIG_APPLYING)

        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMING,
            connectivity=ConnectivityState.UNKNOWN,
            fault=FaultKind.NONE,
        )
        self.assertEqual(p, LedPattern.CLAIMING)

        p = resolve_led_pattern(
            lifecycle=LifecycleState.UNCLAIMED,
            connectivity=ConnectivityState.UNKNOWN,
            fault=FaultKind.NONE,
        )
        self.assertEqual(p, LedPattern.UNCLAIMED)

        # 4. Identify overrides connectivity
        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.OFFLINE,
            fault=FaultKind.NONE,
            active_op_kind=OperationKind.IDENTIFY,
            active_op_state=OperationState.RUNNING,
            elapsed_in_state_ms=5000,
        )
        self.assertEqual(p, LedPattern.IDENTIFY)

        # 5. Connectivity
        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.CONNECTING,
            fault=FaultKind.NONE,
        )
        self.assertEqual(p, LedPattern.CONNECTING)

        p = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.OFFLINE,
            fault=FaultKind.NONE,
        )
        self.assertEqual(p, LedPattern.OFFLINE)

        # 6. Ready (Claimed & Online)
        p_ready = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.NONE,
            elapsed_in_state_ms=500,
        )
        self.assertEqual(p_ready, LedPattern.READY)

        p_ready_expired = resolve_led_pattern(
            lifecycle=LifecycleState.CLAIMED,
            connectivity=ConnectivityState.ONLINE,
            fault=FaultKind.NONE,
            elapsed_in_state_ms=2500,
        )
        self.assertEqual(p_ready_expired, LedPattern.OFF)

    def test_status_led_timing_waveforms(self):
        # UNCLAIMED: 500ms ON / 500ms OFF
        self.assertTrue(status_led_is_active(LedPattern.UNCLAIMED, 0))
        self.assertTrue(status_led_is_active(LedPattern.UNCLAIMED, 250))
        self.assertFalse(status_led_is_active(LedPattern.UNCLAIMED, 500))
        self.assertFalse(status_led_is_active(LedPattern.UNCLAIMED, 750))
        self.assertTrue(status_led_is_active(LedPattern.UNCLAIMED, 1000))

        # CLAIMING: 250ms ON / 250ms OFF
        self.assertTrue(status_led_is_active(LedPattern.CLAIMING, 0))
        self.assertTrue(status_led_is_active(LedPattern.CLAIMING, 100))
        self.assertFalse(status_led_is_active(LedPattern.CLAIMING, 250))
        self.assertFalse(status_led_is_active(LedPattern.CLAIMING, 400))
        self.assertTrue(status_led_is_active(LedPattern.CLAIMING, 500))

        # READY: Solid ON for 2000ms then OFF
        self.assertTrue(status_led_is_active(LedPattern.READY, 0))
        self.assertTrue(status_led_is_active(LedPattern.READY, 1999))
        self.assertFalse(status_led_is_active(LedPattern.READY, 2000))
        self.assertFalse(status_led_is_active(LedPattern.READY, 5000))

        # FAULT: 4 pulses of 200ms ON / 200ms OFF (0..1600), rest 2000ms (1600..3600)
        self.assertTrue(status_led_is_active(LedPattern.FAULT, 0))       # pulse 1 ON
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 200))    # pulse 1 OFF
        self.assertTrue(status_led_is_active(LedPattern.FAULT, 400))     # pulse 2 ON
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 600))    # pulse 2 OFF
        self.assertTrue(status_led_is_active(LedPattern.FAULT, 800))     # pulse 3 ON
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 1000))   # pulse 3 OFF
        self.assertTrue(status_led_is_active(LedPattern.FAULT, 1200))    # pulse 4 ON
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 1400))   # pulse 4 OFF
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 1600))   # rest
        self.assertFalse(status_led_is_active(LedPattern.FAULT, 3500))   # rest
        self.assertTrue(status_led_is_active(LedPattern.FAULT, 3600))    # next cycle pulse 1 ON

    def test_reassembly_commit_config_revision_mismatch(self):
        sample = b"valid_config_data"
        begin, chunks, commit = chunk_config("op_rev", 1, sample)
        # Modify commit config_revision
        mismatched_commit = WireV2ConfigCommit(commit.operation_id, config_revision=2, crc32=commit.crc32)

        reassembler = WireV2Reassembler()
        reassembler.start(begin, now_sec=10.0)
        for chunk in chunks:
            reassembler.add_chunk(chunk, now_sec=11.0)
        with self.assertRaises(DeviceLifecycleError) as ctx:
            reassembler.commit(mismatched_commit, now_sec=12.0)
        self.assertIn("Commit config revision mismatch", str(ctx.exception))

    def test_chunk_config_negative_or_zero_chunk_size(self):
        with self.assertRaises(ValueError):
            chunk_config("op_zero", 1, b"hello", chunk_size=0)
        with self.assertRaises(ValueError):
            chunk_config("op_neg", 1, b"hello", chunk_size=-16)

    def test_reassembler_negative_chunk_index(self):
        begin, _, _ = chunk_config("op_neg_chunk", 1, b"hello")
        bad_chunk = WireV2ConfigChunk("op_neg_chunk", -1, b"hello")
        reassembler = WireV2Reassembler()
        reassembler.start(begin, now_sec=10.0)
        with self.assertRaises(DeviceLifecycleError) as ctx:
            reassembler.add_chunk(bad_chunk, now_sec=11.0)
        self.assertIn("Negative chunk index", str(ctx.exception))

    def test_unknown_model_channel_count_returns_minus_one(self):
        desc = DeviceDescriptor(
            device_uid="unknown_01",
            board_model="unknown_box_xyz",
            board_revision="v1.0",
            protocol_version=2,
            capabilities=[],
            home_id="home_01",
            owner_epoch=1,
            boot_id="boot_01",
            config_revision=1,
        )
        self.assertEqual(desc.channel_count, -1)


if __name__ == "__main__":
    unittest.main()
