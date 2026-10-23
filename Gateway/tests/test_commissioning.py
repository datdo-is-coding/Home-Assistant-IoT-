"""Comprehensive test suite for Device Lifecycle & Commissioning (Milestone M1 - Task T03).

Covers:
1. Candidate TTL and 180s setup window expiration; setup_proof secrecy.
2. Reversed G1: Unseen candidate rejection, send_cfg failure error, no fake descriptor, not online.
3. Reversed G2: 4-node SubBox capacity limit rejects 5th node, preserves pending & input data.
4. Concurrent admin claims: only 1 claim accepted (202), second rejected (409 Conflict).
5. Idempotency: multiple requests with same idempotency_key return the same operation.
6. Timeout: operation times out after 120s without device ACK, candidate preserved, not online.
7. End-to-End Success: Valid candidate + correct proof -> 202 -> Device applied -> Succeeded -> READY -> HA Discovery.
8. HTTP REST API endpoints: authentication, authorization, response framing and status codes.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

from device_lifecycle import (
    ClaimError,
    CommissioningCandidate,
    DeviceLifecycleManager,
    LifecycleOperationLedger,
    Operation,
    OperationKind,
    OperationState,
)
from main import SmartHomeGateway
from registry_manager import RegistryManager
from web_server import WebServer


class TestCandidateLifecycleAndSecrecy(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.candidate = CommissioningCandidate(
            device_uid="AB_TEST_01",
            board_model="actionbox_v2",
            board_revision="rev_b",
            protocol_version=2,
            capabilities=["relay_3ch", "energy_monitor"],
            channel_count=3,
            subbox_id="subbox_living",
            rssi=-65,
            first_seen=self.now,
            last_seen=self.now,
            setup_window_expires_at=self.now + 180.0,
            ttl_expires_at=self.now + 30.0,
            setup_proof="SUPER_SECRET_PROOF_777",
            state="unclaimed",
        )

    def test_candidate_valid_within_window_and_ttl(self):
        self.assertFalse(self.candidate.is_expired(self.now + 10.0))
        self.assertFalse(self.candidate.is_expired(self.now + 29.9))

    def test_candidate_expires_after_ttl_30s(self):
        self.assertTrue(self.candidate.is_expired(self.now + 30.1))

    def test_candidate_expires_after_setup_window_180s(self):
        self.candidate.ttl_expires_at = self.now + 300.0  # even if TTL was somehow high
        self.assertTrue(self.candidate.is_expired(self.now + 180.1))

    def test_to_api_dict_never_exposes_setup_proof(self):
        api_dict = self.candidate.to_api_dict()
        self.assertNotIn("setup_proof", api_dict)
        self.assertNotIn("proof", api_dict)
        # Search all values in dict to make sure the secret string does not appear anywhere
        serialized = json.dumps(api_dict)
        self.assertNotIn("SUPER_SECRET_PROOF_777", serialized)
        # Verify required fields are present
        self.assertEqual(api_dict["device_uid"], "AB_TEST_01")
        self.assertEqual(api_dict["channel_count"], 3)
        self.assertEqual(api_dict["subbox_id"], "subbox_living")
        self.assertEqual(api_dict["state"], "unclaimed")


class TestLifecycleOperationLedger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.db")
        self.ledger = LifecycleOperationLedger(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_record_and_get_by_id(self):
        op = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_123",
            device_uid="AB_01",
            state=OperationState.ACCEPTED,
            idempotency_key="tx_key_1",
            requested_by="admin_user",
            target_subbox="subbox_1",
            desired_revision=1,
            reported_revision=0,
            created_at=100.0,
            updated_at=100.0,
            expires_at=220.0,
            metadata={"room_id": "livingroom"},
        )
        self.ledger.record_operation(op)

        fetched = self.ledger.get_by_id("op_123")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.operation_id, "op_123")
        self.assertEqual(fetched.kind, OperationKind.CLAIM)
        self.assertEqual(fetched.state, OperationState.ACCEPTED)
        self.assertEqual(fetched.idempotency_key, "tx_key_1")
        self.assertEqual(fetched.metadata.get("room_id"), "livingroom")

    def test_get_by_idempotency_key(self):
        op = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_idem",
            device_uid="AB_02",
            state=OperationState.RUNNING,
            idempotency_key="idem_unique_key",
            created_at=100.0,
            updated_at=100.0,
            expires_at=220.0,
        )
        self.ledger.record_operation(op)

        fetched = self.ledger.get_by_idempotency_key("idem_unique_key")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.operation_id, "op_idem")

        self.assertIsNone(self.ledger.get_by_idempotency_key("non_existent_key"))

    def test_update_operation_state(self):
        op = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_upd",
            device_uid="AB_03",
            state=OperationState.ACCEPTED,
            created_at=100.0,
            updated_at=100.0,
            expires_at=220.0,
        )
        self.ledger.record_operation(op)

        updated = self.ledger.update_operation_state(
            operation_id="op_upd",
            state=OperationState.SUCCEEDED,
            reported_revision=2,
            now_sec=150.0,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.state, OperationState.SUCCEEDED)
        self.assertEqual(updated.reported_revision, 2)
        self.assertEqual(updated.updated_at, 150.0)

    def test_ledger_pragmas_and_partial_unique_index(self):
        """Ledger initializes with WAL mode, busy timeout, and partial unique index on active claim."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

        # Insert active operation 1 (accepted)
        op1 = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_active_1",
            device_uid="DEV_CONCURRENT_1",
            state=OperationState.ACCEPTED,
            created_at=100.0,
            updated_at=100.0,
            expires_at=220.0,
        )
        self.ledger.record_operation(op1)

        # Attempt to insert second active operation for same device_uid (running)
        op2 = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_active_2",
            device_uid="DEV_CONCURRENT_1",
            state=OperationState.RUNNING,
            created_at=101.0,
            updated_at=101.0,
            expires_at=221.0,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.record_operation(op2)

        # Transition op1 to succeeded
        self.ledger.update_operation_state("op_active_1", OperationState.SUCCEEDED)

        # Now op2 can be recorded as accepted because op1 is no longer accepted or running
        op2.state = OperationState.ACCEPTED
        self.ledger.record_operation(op2)
        fetched = self.ledger.get_by_id("op_active_2")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.state, OperationState.ACCEPTED)


class TestReversedG1AndG2(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reg_json = os.path.join(self.test_dir, "reg.json")
        self.reg_db = os.path.join(self.test_dir, "reg.db")
        self.registry = RegistryManager(registry_path=self.reg_json, db_path=self.reg_db)

        self.gw = SmartHomeGateway.__new__(SmartHomeGateway)
        self.gw.registry = self.registry
        self.gw.mqtt = SimpleNamespace(send_cfg=AsyncMock(return_value=False), publish=AsyncMock(return_value=True))
        self.gw.discovery = SimpleNamespace(publish_ha_discovery_for_node=AsyncMock())
        self.gw.broadcast_event = Mock()
        self.gw.lifecycle = DeviceLifecycleManager(
            db_path=self.reg_db,
            registry=self.registry,
            mqtt=self.gw.mqtt,
            discovery=self.gw.discovery,
            broadcaster=self.gw.broadcast_event,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_reversed_g1_unseen_candidate_rejected(self):
        """Unseen candidate is rejected: no fake descriptor with serial 'S3-2026-000001' is created."""
        result = await self.gw.provision_pending("NEVER_SEEN_NODE", "livingroom")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

        # Registry must NOT contain NEVER_SEEN_NODE
        self.assertNotIn("NEVER_SEEN_NODE", self.registry.data.get("nodes", {}))
        self.assertNotIn("node_never_seen_node", self.registry.data.get("nodes", {}))

        # Lifecycle start_claim must also reject unseen candidate
        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        with self.assertRaises(ClaimError) as ctx:
            self.gw.lifecycle.start_claim(
                admin_user,
                {"candidate_id": "NEVER_SEEN_NODE", "room_id": "livingroom"},
                now=1000.0,
            )
        self.assertEqual(ctx.exception.error_code, "UNSEEN_CANDIDATE")

    async def test_reversed_g1_send_cfg_failure_returns_error_and_not_online(self):
        """When candidate is present in pending but send_cfg returns False, provisioning fails, not marked online."""
        # Device was discovered
        self.registry.on_hello({
            "id": "PENDING_NODE_01",
            "mac": "AA:11:22:33:44:55",
            "hardware": "esp32s3",
            "serial": "S3-REAL-001",
            "state": "FACTORY_NEW",
            "rl": [0, 0, 0],
        })
        self.assertIn("PENDING_NODE_01", self.registry.data["pending"])

        # send_cfg is set to return False
        self.gw.mqtt.send_cfg = AsyncMock(return_value=False)

        res = await self.gw.provision_pending("PENDING_NODE_01", "livingroom")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "Failed to transmit configuration to device")

        # Must not be online in registry
        node = self.registry.data.get("nodes", {}).get("PENDING_NODE_01")
        if node:
            self.assertNotEqual(node.get("status"), "online")
        self.gw.discovery.publish_ha_discovery_for_node.assert_not_called()

    def test_reversed_g2_subbox_limit_rejects_fifth_node_and_preserves_pending(self):
        """SubBox full (4 ActionBoxes) rejects 5th node, candidate in pending and inputs remain intact."""
        target_subbox = "subbox_living"

        # Pre-seed 4 ActionBoxes assigned to subbox_living
        for i in range(4):
            nid = f"AB_EXISTING_{i}"
            self.registry.data["pending"][nid] = {
                "device_id": nid,
                "mac": f"AA:BB:CC:DD:00:0{i}",
                "hardware": "esp32s3",
                "serial": f"S3-SER-{i}",
                "subbox_id": target_subbox,
                "rl": [0, 0, 0],
            }
            res = self.registry.provision_node(
                mac_or_id=nid,
                room="phong_khach",
                subbox_id=target_subbox,
            )
            self.assertIsNotNone(res)

        # Verify SubBox has exactly 4 nodes
        subbox_nodes = [
            n for n in self.registry.data["nodes"].values()
            if n.get("subbox_id") == target_subbox
        ]
        self.assertEqual(len(subbox_nodes), 4)

        # 5th candidate arrives
        fifth_id = "AB_FIFTH_CANDIDATE"
        self.registry.on_hello({
            "id": fifth_id,
            "mac": "AA:BB:CC:DD:00:05",
            "hardware": "esp32s3",
            "serial": "S3-SER-05",
            "subbox_id": target_subbox,
            "state": "FACTORY_NEW",
            "rl": [0, 0, 0],
        })
        self.assertIn(fifth_id, self.registry.data["pending"])

        # Also add to lifecycle candidates
        now = 1000.0
        self.gw.lifecycle.add_candidate({
            "device_uid": fifth_id,
            "hardware": "actionbox_v2",
            "subbox_id": target_subbox,
        }, now_sec=now)

        # Attempt to provision 5th node on this SubBox
        rejected = self.registry.provision_node(
            mac_or_id=fifth_id,
            room="phong_khach",
            subbox_id=target_subbox,
        )
        self.assertIsNone(rejected)

        # Critical assertion: fifth_id MUST STILL BE IN PENDING with original data intact!
        self.assertIn(fifth_id, self.registry.data["pending"])
        self.assertEqual(self.registry.data["pending"][fifth_id]["serial"], "S3-SER-05")

        # Lifecycle start_claim must also reject with SUBBOX_FULL (409) and KEEP candidate
        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        with self.assertRaises(ClaimError) as ctx:
            self.gw.lifecycle.start_claim(
                admin_user,
                {"candidate_id": fifth_id, "subbox_id": target_subbox},
                now=now,
            )
        self.assertEqual(ctx.exception.error_code, "SUBBOX_FULL")
        self.assertEqual(ctx.exception.status_code, 409)

        # Candidate MUST STILL be in lifecycle candidates!
        self.assertIn(fifth_id, self.gw.lifecycle.candidates)

    async def test_room_limit_rejects_and_preserves_candidate_in_pending(self):
        """Room full (4 nodes) rejects claim with HTTP 409 ROOM_FULL, candidate in pending and lifecycle remains intact."""
        target_room = "phong_bep"

        # Pre-seed 4 nodes in target_room
        for i in range(4):
            nid = f"AB_ROOM_NODE_{i}"
            self.registry.data["pending"][nid] = {
                "device_id": nid,
                "mac": f"CC:11:22:33:44:0{i}",
                "hardware": "esp32s3",
                "serial": f"S3-ROOM-{i}",
                "rl": [0, 0, 0],
            }
            res = self.registry.provision_node(
                mac_or_id=nid,
                room=target_room,
            )
            self.assertIsNotNone(res)

        # Verify target room has exactly 4 nodes
        room_nodes = [n for n in self.registry.data["nodes"].values() if n.get("room") == target_room]
        self.assertEqual(len(room_nodes), 4)

        # 5th candidate arrives
        fifth_id = "AB_FIFTH_ROOM_CANDIDATE"
        now = 1000.0
        self.registry.on_hello({
            "id": fifth_id,
            "mac": "CC:11:22:33:44:05",
            "hardware": "esp32s3",
            "serial": "S3-ROOM-05",
            "state": "FACTORY_NEW",
            "rl": [0, 0, 0],
        })
        self.assertIn(fifth_id, self.registry.data["pending"])

        self.gw.lifecycle.add_candidate({
            "device_uid": fifth_id,
            "hardware": "actionbox_v2",
        }, now_sec=now)
        self.assertIn(fifth_id, self.gw.lifecycle.candidates)

        # 1. Attempt start_claim into full room: must raise ClaimError ROOM_FULL (409)
        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        with self.assertRaises(ClaimError) as ctx:
            self.gw.lifecycle.start_claim(
                admin_user,
                {"candidate_id": fifth_id, "room_id": target_room},
                now=now,
            )
        self.assertEqual(ctx.exception.error_code, "ROOM_FULL")
        self.assertEqual(ctx.exception.status_code, 409)

        # Candidate MUST STILL be in pending and lifecycle candidates!
        self.assertIn(fifth_id, self.registry.data["pending"])
        self.assertEqual(self.registry.data["pending"][fifth_id]["serial"], "S3-ROOM-05")
        self.assertIn(fifth_id, self.gw.lifecycle.candidates)

        # 2. Also verify if on_device_applied runs and provision fails (node is None):
        fake_op = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_room_fail_01",
            device_uid=fifth_id,
            state=OperationState.ACCEPTED,
            metadata={"room_id": target_room},
            created_at=now,
            updated_at=now,
            expires_at=now + 120.0,
        )
        self.gw.lifecycle.ledger.record_operation(fake_op)

        applied_res = await self.gw.lifecycle.on_device_applied(
            device_uid=fifth_id,
            owner_epoch=1,
            operation_id=fake_op.operation_id,
            config_revision=1,
            now_sec=now + 1.0,
        )
        self.assertIsNotNone(applied_res)
        self.assertEqual(applied_res.state, OperationState.FAILED)
        self.assertEqual(applied_res.error_code, "PROVISION_FAILED")

        # Candidate MUST STILL be preserved in pending and lifecycle candidates
        self.assertIn(fifth_id, self.registry.data["pending"])
        self.assertIn(fifth_id, self.gw.lifecycle.candidates)
        # HA discovery must NOT be called
        self.gw.discovery.publish_ha_discovery_for_node.assert_not_called()

    async def test_unsolicited_applied_without_active_claim_rejected(self):
        """Unsolicited ACK applied from unverified device without active claim is rejected."""
        rogue_id = "DEV_ROGUE_ATTACKER"
        now = 1000.0

        # Ensure rogue device is not in nodes
        self.assertNotIn(rogue_id, self.registry.data.get("nodes", {}))

        # Attempt to apply ACK with no active claim
        applied = await self.gw.lifecycle.on_device_applied(
            device_uid=rogue_id,
            owner_epoch=1,
            operation_id="fake_op_rogue",
            config_revision=1,
            now_sec=now,
        )
        self.assertIsNone(applied)

        # Rogue device must NOT be added to registry nodes
        self.assertNotIn(rogue_id, self.registry.data.get("nodes", {}))
        self.gw.discovery.publish_ha_discovery_for_node.assert_not_called()

        # Also test with an expired claim operation: must still be rejected
        expired_op = Operation(
            kind=OperationKind.CLAIM,
            operation_id="op_expired_rogue",
            device_uid=rogue_id,
            state=OperationState.ACCEPTED,
            created_at=now - 200.0,
            updated_at=now - 200.0,
            expires_at=now - 50.0,
        )
        self.gw.lifecycle.ledger.record_operation(expired_op)
        applied_expired = await self.gw.lifecycle.on_device_applied(
            device_uid=rogue_id,
            owner_epoch=1,
            operation_id=expired_op.operation_id,
            config_revision=1,
            now_sec=now,
        )
        self.assertIsNone(applied_expired)
        self.assertNotIn(rogue_id, self.registry.data.get("nodes", {}))

    def test_capability_mismatch_rejected(self):
        """Claim requesting 3 channels on a 2-channel device is rejected with 400 CAPABILITY_MISMATCH."""
        dev_id = "AB_2CH_ONLY"
        now = 1000.0
        self.gw.lifecycle.add_candidate({
            "device_uid": dev_id,
            "board_model": "actionbox_v1",
            "capabilities": ["relay_2ch"],
            "channel_count": 2,
        }, now_sec=now)

        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        claim_req = {
            "candidate_id": dev_id,
            "room_id": "livingroom",
            "channels": {
                "ch1": "light",
                "ch2": "fan",
                "ch3": "heater",
            },
        }

        with self.assertRaises(ClaimError) as ctx:
            self.gw.lifecycle.start_claim(admin_user, claim_req, now=now)

        self.assertEqual(ctx.exception.error_code, "CAPABILITY_MISMATCH")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Device supports 2 channels, requested 3", ctx.exception.message)


class TestConcurrentClaimsAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reg_db = os.path.join(self.test_dir, "test.db")
        self.registry = RegistryManager(db_path=self.reg_db)
        self.lifecycle = DeviceLifecycleManager(db_path=self.reg_db, registry=self.registry)
        self.now = 1000.0

        # Register a valid candidate
        self.lifecycle.add_candidate({
            "device_uid": "AB_CONCURRENT_DEV",
            "board_model": "actionbox_v2",
            "setup_proof": "SECRET_PROOF_999",
            "subbox_id": "sb_1",
        }, now_sec=self.now)

        self.admin1 = {"id": 1, "username": "admin1", "role": "admin"}
        self.admin2 = {"id": 2, "username": "admin2", "role": "admin"}

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_concurrent_admin_claims_first_accepted_second_conflict(self):
        """2 admin claim simultaneously: first accepted (202), second rejected (409 Conflict)."""
        req1 = {
            "candidate_id": "AB_CONCURRENT_DEV",
            "setup_proof": "SECRET_PROOF_999",
            "room_id": "livingroom",
            "subbox_id": "sb_1",
        }
        op1 = self.lifecycle.start_claim(self.admin1, req1, now=self.now)
        self.assertEqual(op1.state, OperationState.ACCEPTED)
        self.assertEqual(op1.device_uid, "AB_CONCURRENT_DEV")

        # Second admin claims the same device
        req2 = {
            "candidate_id": "AB_CONCURRENT_DEV",
            "setup_proof": "SECRET_PROOF_999",
            "room_id": "bedroom",
            "subbox_id": "sb_1",
        }
        with self.assertRaises(ClaimError) as ctx:
            self.lifecycle.start_claim(self.admin2, req2, now=self.now)
        self.assertEqual(ctx.exception.error_code, "CLAIM_IN_PROGRESS")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_idempotency_returns_same_operation(self):
        """Sending 2 requests with the same idempotency_key returns the same operation without duplicates."""
        req = {
            "candidate_id": "AB_CONCURRENT_DEV",
            "setup_proof": "SECRET_PROOF_999",
            "room_id": "livingroom",
            "idempotency_key": "IDEMPOTENT_TX_KEY_001",
        }
        op1 = self.lifecycle.start_claim(self.admin1, req, now=self.now)
        op2 = self.lifecycle.start_claim(self.admin1, req, now=self.now + 2.0)

        self.assertEqual(op1.operation_id, op2.operation_id)
        self.assertEqual(op1.idempotency_key, op2.idempotency_key)

        # Check in SQLite ledger: only 1 operation exists for this key
        fetched = self.lifecycle.ledger.get_by_idempotency_key("IDEMPOTENT_TX_KEY_001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.operation_id, op1.operation_id)

    def test_multithreaded_concurrent_start_claim(self):
        """Concurrent threads calling start_claim for same device: exactly 1 succeeds, others 409."""
        def do_claim(admin_id: int):
            user = {"id": admin_id, "username": f"admin{admin_id}", "role": "admin"}
            req = {
                "candidate_id": "AB_CONCURRENT_DEV",
                "setup_proof": "SECRET_PROOF_999",
                "room_id": f"room_{admin_id}",
                "subbox_id": "sb_1",
            }
            return self.lifecycle.start_claim(user, req, now=self.now)

        successes = []
        conflicts = []
        errors = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(do_claim, i) for i in range(1, 6)]
            for f in concurrent.futures.as_completed(futures):
                try:
                    res = f.result()
                    successes.append(res)
                except ClaimError as e:
                    if e.status_code == 409 and e.error_code == "CLAIM_IN_PROGRESS":
                        conflicts.append(e)
                    else:
                        errors.append(e)
                except Exception as e:
                    errors.append(e)

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 4)

    def test_start_claim_integrity_error_handling(self):
        """IntegrityError from ledger in start_claim is converted to ClaimError CLAIM_IN_PROGRESS (409)."""
        req = {
            "candidate_id": "AB_CONCURRENT_DEV",
            "setup_proof": "SECRET_PROOF_999",
            "room_id": "livingroom",
            "subbox_id": "sb_1",
        }
        with patch.object(self.lifecycle.ledger, "record_operation", side_effect=sqlite3.IntegrityError("UNIQUE constraint failed")):
            with self.assertRaises(ClaimError) as ctx:
                self.lifecycle.start_claim(self.admin1, req, now=self.now)
            self.assertEqual(ctx.exception.error_code, "CLAIM_IN_PROGRESS")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("AB_CONCURRENT_DEV", ctx.exception.message)


class TestClaimTimeoutAndRecovery(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reg_db = os.path.join(self.test_dir, "test.db")
        self.registry = RegistryManager(db_path=self.reg_db)
        self.lifecycle = DeviceLifecycleManager(db_path=self.reg_db, registry=self.registry)
        self.now = 1000.0

        self.lifecycle.add_candidate({
            "device_uid": "AB_TIMEOUT_DEV",
            "board_model": "actionbox_v2",
            "setup_proof": "PROOF_123",
        }, now_sec=self.now)

        self.admin = {"id": 1, "username": "admin", "role": "admin"}

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_operation_times_out_after_120s(self):
        """If device does not ACK within 120s, operation transitions to timed_out, device not online, candidate preserved."""
        req = {
            "candidate_id": "AB_TIMEOUT_DEV",
            "setup_proof": "PROOF_123",
            "room_id": "livingroom",
        }
        op = self.lifecycle.start_claim(self.admin, req, now=self.now)
        self.assertEqual(op.expires_at, self.now + 120.0)

        # At t = 110s, operation is still accepted
        op_check = self.lifecycle.get_operation(op.operation_id, now_sec=self.now + 110.0)
        self.assertEqual(op_check.state, OperationState.ACCEPTED)

        # At t = 121s (expired), get_operation transitions to timed_out
        op_timed_out = self.lifecycle.get_operation(op.operation_id, now_sec=self.now + 121.0)
        self.assertEqual(op_timed_out.state, OperationState.TIMED_OUT)
        self.assertEqual(op_timed_out.error_code, "TIMEOUT")

        # Device must NOT be online or claimed in registry
        node = self.registry.data.get("nodes", {}).get("AB_TIMEOUT_DEV")
        if node:
            self.assertNotEqual(node.get("status"), "online")
            self.assertNotEqual(node.get("security", {}).get("lifecycle_state"), "claimed")

        # Candidate MUST STILL be retained in lifecycle manager
        self.assertIn("AB_TIMEOUT_DEV", self.lifecycle.candidates)


class TestEndToEndSuccess(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reg_json = os.path.join(self.test_dir, "reg.json")
        self.reg_db = os.path.join(self.test_dir, "reg.db")
        self.registry = RegistryManager(registry_path=self.reg_json, db_path=self.reg_db)

        self.mqtt = SimpleNamespace(
            publish=AsyncMock(return_value=True),
            send_cfg=AsyncMock(return_value=True),
        )
        self.discovery = SimpleNamespace(
            publish_ha_discovery_for_node=AsyncMock(return_value=True),
        )
        self.events = []
        self.broadcaster = lambda event, data: self.events.append((event, data))

        self.lifecycle = DeviceLifecycleManager(
            db_path=self.reg_db,
            registry=self.registry,
            mqtt=self.mqtt,
            discovery=self.discovery,
            broadcaster=self.broadcaster,
        )
        self.now = 1000.0

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_end_to_end_claim_success(self):
        """Candidate + valid proof -> 202 Accepted -> Device ACK applied -> Succeeded -> READY -> HA Discovery."""
        device_uid = "AB_E2E_DEVICE"
        setup_proof = "PROPER_SETUP_CODE_2026"

        # 1. Device discovered as unclaimed candidate
        candidate = self.lifecycle.add_candidate({
            "device_uid": device_uid,
            "board_model": "actionbox_v2",
            "setup_proof": setup_proof,
            "subbox_id": "subbox_master",
            "capabilities": ["relay_3ch"],
            "channel_count": 3,
        }, now_sec=self.now)
        self.assertEqual(candidate.state, "unclaimed")
        self.assertIn(device_uid, self.lifecycle.candidates)

        # Also add to registry pending
        self.registry.data["pending"][device_uid] = {
            "device_id": device_uid,
            "hardware": "actionbox_v2",
            "serial": "S3-2026-E2E",
            "subbox_id": "subbox_master",
            "rl": [0, 0, 0],
        }

        # 2. Admin starts claim with correct proof
        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        claim_req = {
            "candidate_id": device_uid,
            "setup_proof": setup_proof,
            "room_id": "phong_khach",
            "subbox_id": "subbox_master",
            "name": "ActionBox Khách",
            "channels": {"ch1": "light", "ch2": "fan", "ch3": "switch"},
            "idempotency_key": "idem_e2e_001",
        }
        op = self.lifecycle.start_claim(admin_user, claim_req, now=self.now)
        self.assertEqual(op.state, OperationState.ACCEPTED)
        self.assertEqual(op.expires_at, self.now + 120.0)

        # 3. Device receives config and sends ACK applied
        applied_op = await self.lifecycle.on_device_applied(
            device_uid=device_uid,
            owner_epoch=1,
            operation_id=op.operation_id,
            config_revision=1,
            now_sec=self.now + 5.0,
        )
        self.assertIsNotNone(applied_op)
        self.assertEqual(applied_op.state, OperationState.SUCCEEDED)

        # 4. Device is marked claimed and READY in registry, online = True
        node = self.registry.data["nodes"].get(device_uid)
        self.assertIsNotNone(node)
        self.assertEqual(node["status"], "online")
        self.assertEqual(node["state"], "READY")
        self.assertEqual(node["security"]["state"], "READY")
        self.assertEqual(node["security"]["lifecycle_state"], "claimed")
        self.assertEqual(node["subbox_id"], "subbox_master")

        # 5. Candidate is removed from candidates and pending
        self.assertNotIn(device_uid, self.lifecycle.candidates)
        self.assertNotIn(device_uid, self.registry.data["pending"])

        # 6. HA Discovery published
        self.discovery.publish_ha_discovery_for_node.assert_called_once_with(device_uid)

        # 7. SSE event broadcast
        claimed_events = [data for evt, data in self.events if evt == "device_claimed"]
        self.assertEqual(len(claimed_events), 1)
        self.assertEqual(claimed_events[0]["device_uid"], device_uid)
        self.assertEqual(claimed_events[0]["operation_id"], op.operation_id)
        self.assertEqual(claimed_events[0]["state"], "succeeded")

    async def test_operation_state_transitions_to_running_then_succeeded(self):
        """Verify strict progression: ACCEPTED -> RUNNING (via MQTT dispatch) -> SUCCEEDED (via ACK applied)."""
        device_uid = "AB_TRANSITION_DEV"
        setup_proof = "PROOF_TRANS_123"

        cand = self.lifecycle.add_candidate({
            "device_uid": device_uid,
            "board_model": "actionbox_v2",
            "setup_proof": setup_proof,
            "capabilities": ["relay_3ch"],
            "channel_count": 3,
        }, now_sec=self.now)
        self.registry.data["pending"][device_uid] = {
            "device_id": device_uid,
            "hardware": "actionbox_v2",
            "serial": "S3-TRANS-01",
            "rl": [0, 0, 0],
        }

        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        claim_req = {
            "candidate_id": device_uid,
            "setup_proof": setup_proof,
            "room_id": "phong_khach",
            "channels": {"ch1": "light", "ch2": "fan"},
        }

        # 1. Start claim -> ACCEPTED
        op = self.lifecycle.start_claim(admin_user, claim_req, now=self.now)
        self.assertEqual(op.state, OperationState.ACCEPTED)
        ledger_op = self.lifecycle.ledger.get_by_id(op.operation_id)
        self.assertEqual(ledger_op.state, OperationState.ACCEPTED)

        # 2. Dispatch config -> RUNNING
        await self.lifecycle._dispatch_claim_config(op, cand, claim_req)
        self.assertEqual(op.state, OperationState.RUNNING)
        ledger_op = self.lifecycle.ledger.get_by_id(op.operation_id)
        self.assertEqual(ledger_op.state, OperationState.RUNNING)

        # 3. ACK applied -> SUCCEEDED
        applied_op = await self.lifecycle.on_device_applied(
            device_uid=device_uid,
            owner_epoch=1,
            operation_id=op.operation_id,
            config_revision=1,
            now_sec=self.now + 2.0,
        )
        self.assertIsNotNone(applied_op)
        self.assertEqual(applied_op.state, OperationState.SUCCEEDED)
        ledger_op = self.lifecycle.ledger.get_by_id(op.operation_id)
        self.assertEqual(ledger_op.state, OperationState.SUCCEEDED)

    async def test_cross_device_operation_id_mismatch_rejected(self):
        """Device B sending ACK with operation_id belonging to Device A must not attach to A's op, and if B has no claim it is rejected."""
        device_a = "AB_DEV_A"
        proof_a = "PROOF_A"
        self.lifecycle.add_candidate({
            "device_uid": device_a,
            "board_model": "actionbox_v2",
            "setup_proof": proof_a,
            "subbox_id": "subbox_master",
            "capabilities": ["relay_3ch"],
            "channel_count": 3,
        }, now_sec=self.now)
        self.registry.data["pending"][device_a] = {
            "device_id": device_a,
            "hardware": "actionbox_v2",
        }

        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        op_a = self.lifecycle.start_claim(admin_user, {
            "candidate_id": device_a,
            "setup_proof": proof_a,
            "room_id": "livingroom",
        }, now=self.now)
        self.assertEqual(op_a.state, OperationState.ACCEPTED)

        # Device B (not in registry, no claim of its own) sends applied ACK with op_a.operation_id
        device_b = "AB_DEV_B_SPOOF"
        res = await self.lifecycle.on_device_applied(
            device_uid=device_b,
            operation_id=op_a.operation_id,
            now_sec=self.now + 1.0,
        )

        # 1. Result must be None (rejected unsolicited ACK)
        self.assertIsNone(res)

        # 2. Device A's operation must remain unchanged (ACCEPTED/RUNNING), never SUCCEEDED
        op_a_fetched = self.lifecycle.ledger.get_by_id(op_a.operation_id)
        self.assertIsNotNone(op_a_fetched)
        self.assertNotEqual(op_a_fetched.state, OperationState.SUCCEEDED)
        self.assertEqual(op_a_fetched.device_uid, device_a)

        # 3. Device B must not be in nodes
        self.assertNotIn(device_b, self.registry.data.get("nodes", {}))

        # 4. Device A can legitimately complete its own operation
        res_a = await self.lifecycle.on_device_applied(
            device_uid=device_a,
            operation_id=op_a.operation_id,
            now_sec=self.now + 2.0,
        )
        self.assertIsNotNone(res_a)
        self.assertEqual(res_a.state, OperationState.SUCCEEDED)
        self.assertIn(device_a, self.registry.data.get("nodes", {}))

    async def test_claim_with_channels_list_and_room_key(self):
        """Verify start_claim works with 'room' key and channels as list."""
        device_uid = "AB_CH_LIST_DEV"
        proof = "PROOF_LIST_CH"
        self.lifecycle.add_candidate({
            "device_uid": device_uid,
            "board_model": "actionbox_v2",
            "setup_proof": proof,
            "capabilities": ["relay_2ch"],
            "channel_count": 2,
        }, now_sec=self.now)
        self.registry.data["pending"][device_uid] = {
            "device_id": device_uid,
            "hardware": "actionbox_v2",
        }

        admin_user = {"id": 1, "username": "admin", "role": "admin"}
        # Channels list exceeding channel_count raises CAPABILITY_MISMATCH
        with self.assertRaises(ClaimError) as ctx:
            self.lifecycle.start_claim(admin_user, {
                "candidate_id": device_uid,
                "setup_proof": proof,
                "room": "bedroom",
                "channels": ["light", "fan", "switch"],
            }, now=self.now)
        self.assertEqual(ctx.exception.error_code, "CAPABILITY_MISMATCH")

        # Valid channels list (length 2 <= 2) and 'room' key
        op = self.lifecycle.start_claim(admin_user, {
            "candidate_id": device_uid,
            "setup_proof": proof,
            "room": "bedroom",
            "channels": ["light", "fan"],
        }, now=self.now)
        self.assertEqual(op.state, OperationState.ACCEPTED)

        res = await self.lifecycle.on_device_applied(
            device_uid=device_uid,
            operation_id=op.operation_id,
            now_sec=self.now + 1.0,
        )
        self.assertIsNotNone(res)
        node = self.registry.data["nodes"].get(device_uid)
        self.assertIsNotNone(node)
        self.assertEqual(node.get("room"), "bedroom")


class TestCommissioningHttpApi(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reg_db = os.path.join(self.test_dir, "api.db")
        self.registry = RegistryManager(db_path=self.reg_db)

        self.auth = Mock()
        self.auth.has_any_admin.return_value = True

        self.gateway = SimpleNamespace(
            auth=self.auth,
            registry=self.registry,
            mqtt=SimpleNamespace(publish=AsyncMock(return_value=True)),
            discovery=SimpleNamespace(publish_ha_discovery_for_node=AsyncMock(return_value=True)),
            broadcast_event=Mock(),
        )
        self.lifecycle = DeviceLifecycleManager(
            db_path=self.reg_db,
            registry=self.registry,
            mqtt=self.gateway.mqtt,
            discovery=self.gateway.discovery,
            broadcaster=self.gateway.broadcast_event,
        )
        self.gateway.lifecycle = self.lifecycle
        self.server = WebServer(self.gateway)

        # Seed candidate
        self.lifecycle.add_candidate({
            "device_uid": "AB_HTTP_NODE",
            "board_model": "actionbox_v2",
            "setup_proof": "HTTP_SECRET_123",
            "subbox_id": "subbox_1",
        }, now_sec=time.time())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def _send_request(self, method: str, path: str, token: str | None = None, body: bytes = b""):
        req_headers = {
            "Host": "gateway.local",
            "Content-Length": str(len(body)),
        }
        if token:
            req_headers["Authorization"] = f"Bearer {token}"

        header_lines = "".join(f"{k}: {v}\r\n" for k, v in req_headers.items())
        raw_req = f"{method} {path} HTTP/1.1\r\n{header_lines}\r\n".encode() + body

        reader = asyncio.StreamReader()
        reader.feed_data(raw_req)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()

        await self.server._handle_client(reader, writer)
        raw_response = b"".join(call.args[0] for call in writer.write.call_args_list)
        if not raw_response:
            return 0, {}, {}

        parts = raw_response.split(b"\r\n\r\n", 1)
        resp_headers_raw = parts[0].decode()
        resp_body = parts[1] if len(parts) > 1 else b""
        status = int(resp_headers_raw.split("\r\n")[0].split()[1])

        parsed_json = {}
        if resp_body:
            try:
                parsed_json = json.loads(resp_body.decode())
            except Exception:
                pass
        return status, {}, parsed_json

    async def test_get_candidates_unauthenticated_returns_401(self):
        self.auth.authenticate_token.return_value = None
        status, _, _ = await self._send_request("GET", "/api/commissioning/candidates")
        self.assertEqual(status, 401)

    async def test_get_candidates_member_returns_403(self):
        self.auth.authenticate_token.return_value = {"id": 2, "username": "member", "role": "member"}
        status, _, _ = await self._send_request("GET", "/api/commissioning/candidates", token="member_tok")
        self.assertEqual(status, 403)

    async def test_get_candidates_admin_returns_200_no_proof_leaked(self):
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        status, _, data = await self._send_request("GET", "/api/commissioning/candidates", token="admin_tok")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        candidates = data.get("candidates", [])
        self.assertGreater(len(candidates), 0)
        c0 = candidates[0]
        self.assertEqual(c0["device_uid"], "AB_HTTP_NODE")
        self.assertNotIn("setup_proof", c0)
        self.assertNotIn("HTTP_SECRET_123", json.dumps(data))

    async def test_post_claims_admin_valid_proof_returns_202(self):
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        body = json.dumps({
            "candidate_id": "AB_HTTP_NODE",
            "setup_proof": "HTTP_SECRET_123",
            "room_id": "livingroom",
            "idempotency_key": "http_tx_001",
        }).encode()
        status, _, data = await self._send_request("POST", "/api/commissioning/claims", token="admin_tok", body=body)
        self.assertEqual(status, 202)
        self.assertTrue(data.get("success"))
        op = data.get("operation", {})
        self.assertEqual(op.get("state"), "accepted")
        self.assertEqual(op.get("device_uid"), "AB_HTTP_NODE")

        # Now GET /api/operations/{id}
        op_id = op.get("operation_id")
        status_get, _, data_get = await self._send_request("GET", f"/api/operations/{op_id}", token="admin_tok")
        self.assertEqual(status_get, 200)
        self.assertEqual(data_get.get("operation", {}).get("operation_id"), op_id)

    async def test_post_claims_invalid_proof_returns_400(self):
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        body = json.dumps({
            "candidate_id": "AB_HTTP_NODE",
            "setup_proof": "WRONG_SECRET",
            "room_id": "livingroom",
        }).encode()
        status, _, data = await self._send_request("POST", "/api/commissioning/claims", token="admin_tok", body=body)
        self.assertEqual(status, 400)
        self.assertEqual(data.get("error_code"), "INVALID_PROOF")

    async def test_setup_proof_not_leaked_in_operations_api(self):
        """Confirm setup_proof is stripped from metadata and not leaked via operations API or SQLite."""
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        secret_proof = "SECRET_SUPER_CONFIDENTIAL_PROOF"

        self.lifecycle.add_candidate({
            "device_uid": "AB_PROOF_TEST_NODE",
            "board_model": "actionbox_v2",
            "setup_proof": secret_proof,
            "capabilities": ["relay_3ch"],
            "channel_count": 3,
            "subbox_id": "subbox_1",
        }, now_sec=time.time())

        claim_body = json.dumps({
            "candidate_id": "AB_PROOF_TEST_NODE",
            "setup_proof": secret_proof,
            "proof": secret_proof,
            "setup_code": secret_proof,
            "room_id": "livingroom",
            "name": "Protected Box",
        }).encode()

        status, _, data = await self._send_request(
            "POST", "/api/commissioning/claims", token="admin_tok", body=claim_body
        )
        self.assertEqual(status, 202)
        op_dict = data.get("operation", {})
        op_id = op_dict.get("operation_id")

        # 1. Verify response of POST does not contain secret proof in metadata
        meta = op_dict.get("metadata", {})
        self.assertNotIn("setup_proof", meta)
        self.assertNotIn("proof", meta)
        self.assertNotIn("setup_code", meta)
        self.assertNotIn(secret_proof, json.dumps(data))

        # 2. Verify GET /api/operations/{op_id} does not contain secret proof
        status_get, _, data_get = await self._send_request(
            "GET", f"/api/operations/{op_id}", token="admin_tok"
        )
        self.assertEqual(status_get, 200)
        self.assertNotIn(secret_proof, json.dumps(data_get))
        get_meta = data_get.get("operation", {}).get("metadata", {})
        self.assertNotIn("setup_proof", get_meta)

        # 3. Verify SQLite DB row for this operation does not contain secret proof
        with sqlite3.connect(self.reg_db) as conn:
            cur = conn.execute("SELECT metadata FROM lifecycle_operations WHERE operation_id = ?", (op_id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertNotIn(secret_proof, row[0])


if __name__ == "__main__":
    unittest.main()
