"""Host test runner for Firmware device_lifecycle.h contract and fixtures."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
COMMON_DIR = HERE.parent / "firmware_esp/common"
FIXTURES_DIR = HERE.parent.parent / "tests/fixtures/device_lifecycle"


class TestDeviceLifecycleFirmware(unittest.TestCase):
    def test_cpp_device_lifecycle_host_binary(self):
        host_cpp = HERE / "test_device_lifecycle_host.cpp"
        self.assertTrue(host_cpp.is_file(), f"Host test source missing: {host_cpp}")
        header = COMMON_DIR / "device_lifecycle.h"
        self.assertTrue(header.is_file(), f"Header missing: {header}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            bin_path = Path(tmp_dir) / "test_device_lifecycle"
            cmd_compile = [
                "g++",
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-I",
                str(COMMON_DIR),
                str(host_cpp),
                "-o",
                str(bin_path),
            ]
            compile_proc = subprocess.run(cmd_compile, capture_output=True, text=True)
            self.assertEqual(
                compile_proc.returncode,
                0,
                f"C++ Compilation failed:\nSTDOUT: {compile_proc.stdout}\nSTDERR: {compile_proc.stderr}",
            )

            run_proc = subprocess.run([str(bin_path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(
                run_proc.returncode,
                0,
                f"C++ Execution failed:\nSTDOUT: {run_proc.stdout}\nSTDERR: {run_proc.stderr}",
            )
            self.assertIn("ALL HOST TESTS PASSED", run_proc.stdout)

    def load_fixture(self, name: str) -> dict:
        fixture_path = FIXTURES_DIR / name
        self.assertTrue(fixture_path.is_file(), f"Fixture missing: {fixture_path}")
        with fixture_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def test_fixtures_against_firmware_contract_rules(self):
        # 1. ActionBox V1 -> 2 channels
        v1 = self.load_fixture("actionbox_v1_2ch.json")
        self.assertEqual(v1["board_model"], "actionbox_v1")
        self.assertEqual(v1["protocol_version"], 2)

        # 2. ActionBox V2 -> 3 channels
        v2 = self.load_fixture("actionbox_v2_3ch.json")
        self.assertEqual(v2["board_model"], "actionbox_v2")
        self.assertEqual(v2["protocol_version"], 2)

        # 3. SubBox -> 0 relays
        sub = self.load_fixture("subbox_0relay.json")
        self.assertEqual(sub["board_model"], "subbox_v1")
        self.assertEqual(sub["protocol_version"], 2)

        # 4. Unknown model
        unk = self.load_fixture("unknown_model.json")
        self.assertNotIn(unk["board_model"], ["actionbox_v1", "actionbox_v2", "subbox_v1"])

        # 5. Unsupported protocol
        unsupported = self.load_fixture("unsupported_protocol.json")
        self.assertNotEqual(unsupported["protocol_version"], 2)

        # 6. Old epoch
        old_epoch = self.load_fixture("old_epoch.json")
        self.assertLess(old_epoch["owner_epoch"], old_epoch["current_epoch"])

        # 7. Duplicate UID
        dup = self.load_fixture("duplicate_uid.json")
        self.assertIn(dup["device_uid"], dup["existing_uids"])

        # 8. Stale timestamp
        stale = self.load_fixture("stale_timestamp.json")
        self.assertLess(stale["expires_at"], 1600000030.0)

        # 9. Oversize fragment
        oversize = self.load_fixture("oversize_fragment.json")
        self.assertGreater(oversize["chunk_size"], 160)
        self.assertGreater(oversize["config_total_len"], 4096)


if __name__ == "__main__":
    unittest.main()
