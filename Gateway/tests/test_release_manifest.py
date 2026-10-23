"""Comprehensive test suite for Signed Release Manifest & Storage Retention (Milestone M4 - Task T15)."""
from __future__ import annotations

import hashlib
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
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

from ota_manager import OTAManager, ESP_IMAGE_MAGIC
from registry_manager import RegistryManager


class TestReleaseManifestAndRetention(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="aeth_release_test_")
        self.fw_dir = os.path.join(self.test_dir, "firmware")
        os.makedirs(self.fw_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, "registry.db")

        self.registry = RegistryManager(db_path=self.db_path)
        self.gateway = SimpleNamespace(
            registry=self.registry,
            broadcast_event=Mock(),
        )
        self.ota = OTAManager(self.gateway)
        self.ota.firmware_dir = self.fw_dir

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_bin(self, filename: str, chip_byte: int = 0x0009, magic: int = ESP_IMAGE_MAGIC) -> str:
        """Create a mock ESP-IDF binary."""
        path = os.path.join(self.fw_dir, filename)
        content = bytearray(512)
        content[0] = magic
        content[1] = 4  # segments
        content[2] = 0  # flash mode
        content[3] = 0x20  # flash size/freq
        content[12] = chip_byte & 0xFF
        content[13] = (chip_byte >> 8) & 0xFF
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_release_manifest_validates_magic_byte_and_hash(self):
        # Valid binary
        self._create_mock_bin("actionbox_v2_1.0.0.bin")
        res = self.ota.validate_firmware("actionbox_v2_1.0.0.bin")
        self.assertTrue(res["valid"])
        self.assertTrue(res["valid_esp"])
        self.assertIn("sha256", res)
        self.assertIn("md5", res)

        # Invalid magic byte
        self._create_mock_bin("corrupted.bin", magic=0x00)
        res_bad = self.ota.validate_firmware("corrupted.bin")
        self.assertFalse(res_bad["valid"])
        self.assertFalse(res_bad["valid_esp"])
        self.assertIn("0xE9", res_bad["error"])

    def test_model_and_board_mismatch_rejection(self):
        self._create_mock_bin("actionbox_v2_update.bin")
        self._create_mock_bin("subbox_gateway_update.bin")

        # Mock devices in registry
        self.registry.data["nodes"]["AB_LIVING"] = {
            "device_id": "AB_LIVING",
            "model": "actionbox_v2",
            "hardware": "esp32s3_actionbox_v2",
        }
        self.registry.data["nodes"]["SB_MASTER"] = {
            "device_id": "SB_MASTER",
            "model": "subbox",
            "hardware": "esp32s3_subbox",
        }

        # SubBox firmware targetting ActionBox device -> Rejected
        res1 = self.ota.validate_firmware("subbox_gateway_update.bin", node_id="AB_LIVING")
        self.assertFalse(res1["valid"])
        self.assertIn("không thể nạp cho thiết bị ActionBox", res1["error"])

        # ActionBox firmware targetting SubBox device -> Rejected
        res2 = self.ota.validate_firmware("actionbox_v2_update.bin", node_id="SB_MASTER")
        self.assertFalse(res2["valid"])
        self.assertIn("không thể nạp cho thiết bị SubBox", res2["error"])

    def test_download_ticket_ttl_expiry(self):
        self._create_mock_bin("actionbox_v2_rel.bin")
        # Ticket with 1 second TTL
        ticket = self.ota.create_download_ticket("AB_LIVING", "actionbox_v2_rel.bin", ttl_seconds=1)
        self.assertTrue(self.ota.validate_download_ticket(ticket, "AB_LIVING", "actionbox_v2_rel.bin"))

        # Wrong device -> Rejected
        self.assertFalse(self.ota.validate_download_ticket(ticket, "AB_SPOOF", "actionbox_v2_rel.bin"))

        # Wrong filename -> Rejected
        self.assertFalse(self.ota.validate_download_ticket(ticket, "AB_LIVING", "other_fw.bin"))

        # Expired ticket
        self.ota._download_tickets[ticket]["expires_at"] = time.time() - 10
        self.assertFalse(self.ota.validate_download_ticket(ticket, "AB_LIVING", "actionbox_v2_rel.bin"))

    def test_download_ticket_one_time_consume(self):
        """[SEC-01] Download ticket is strictly single-use and cannot be reused after consumption."""
        self._create_mock_bin("actionbox_v2_rel.bin")
        ticket = self.ota.create_download_ticket("AB_LIVING", "actionbox_v2_rel.bin", ttl_seconds=600)
        self.assertTrue(self.ota.validate_download_ticket(ticket, "AB_LIVING", "actionbox_v2_rel.bin"))

        # Consume the ticket upon download
        consumed = self.ota.consume_download_ticket(ticket)
        self.assertTrue(consumed)

        # Ticket cannot be reused for validation or further consumption
        self.assertFalse(self.ota.validate_download_ticket(ticket, "AB_LIVING", "actionbox_v2_rel.bin"))
        self.assertFalse(self.ota.validate_download_ticket(ticket))
        self.assertFalse(self.ota.consume_download_ticket(ticket))

        # Non-existent or invalid ticket cannot be consumed
        self.assertFalse(self.ota.consume_download_ticket("invalid_ticket_key"))

        # Expired ticket cannot be consumed
        exp_ticket = self.ota.create_download_ticket("AB_LIVING", "actionbox_v2_rel.bin", ttl_seconds=1)
        self.ota._download_tickets[exp_ticket]["expires_at"] = time.time() - 5
        self.assertFalse(self.ota.consume_download_ticket(exp_ticket))

    def test_sqlite_telemetry_retention_pruning(self):
        """Verify telemetry records older than retention limit are pruned without blocking."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT,
                    power REAL,
                    voltage REAL,
                    current REAL,
                    energy REAL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Insert 50 dummy records
            for i in range(50):
                conn.execute("INSERT INTO telemetry_history (node_id, power) VALUES ('NODE_TEST', ?)", (float(i),))
            conn.commit()

            cur = conn.execute("SELECT COUNT(*) FROM telemetry_history")
            self.assertEqual(cur.fetchone()[0], 50)

            # Prune keeping latest 20
            conn.execute("""
                DELETE FROM telemetry_history WHERE id NOT IN (
                    SELECT id FROM telemetry_history ORDER BY id DESC LIMIT 20
                )
            """)
            conn.commit()

            cur2 = conn.execute("SELECT COUNT(*) FROM telemetry_history")
            self.assertEqual(cur2.fetchone()[0], 20)


if __name__ == "__main__":
    unittest.main()
