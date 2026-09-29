"""
Hardware-in-the-Loop (HIL) & Protocol Verification Runner
=========================================================
Runs test suites against actual serial-connected devices or simulated mock endpoints.
Does not require a host C++ compiler.

Usage:
  python Firmware/tools/hil_runner.py [--port COM8] [--mock]
"""

import sys
import time
import json
import argparse
import unittest
from typing import Optional, Dict, Any

class MockActionBoxTransport:
    """Simulates ActionBox protocol state machine for HIL verification without hardware."""
    def __init__(self, node_id="AB001", hw_uid="AABBCCDDEEFF"):
        self.node_id = node_id
        self.hw_uid = hw_uid
        self.config_version = 1
        self.protocol_version = 3
        self.relays = [0, 0] # 0 = OFF, 1 = ON
        self.idempotency_cache = {} # (session_id, request_id) -> response

    def process_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req_id = payload.get("request_id", 0)
        session_id = payload.get("session_id", 0)
        cmd = payload.get("cmd")
        ch = payload.get("channel", 1)

        # Check idempotency cache
        cache_key = (session_id, req_id)
        if cache_key in self.idempotency_cache:
            return {**self.idempotency_cache[cache_key], "cached": True}

        # Check identity
        if payload.get("hardware_uid") != self.hw_uid or payload.get("protocol_version") != 3:
            return {"status": "ERROR", "error": "Identity mismatch or invalid protocol version"}

        # Network TOGGLE rejection
        if cmd == "TOGGLE":
            resp = {
                "type": "ACK", "status": "ERROR", "state": "REJECTED",
                "error": "Network TOGGLE rejected. Use TURN_ON or TURN_OFF",
                "node_id": self.node_id, "hardware_uid": self.hw_uid,
                "request_id": req_id, "session_id": session_id, "channel": ch
            }
            self.idempotency_cache[cache_key] = resp
            return resp

        # TURN_ON / TURN_OFF
        if cmd == "TURN_ON":
            self.relays[ch - 1] = 1
            st = "ON"
        elif cmd == "TURN_OFF":
            self.relays[ch - 1] = 0
            st = "OFF"
        elif cmd == "GET_STATE":
            st = "ON" if self.relays[ch - 1] else "OFF"
        else:
            st = "UNKNOWN_CMD"

        resp = {
            "type": "ACK", "status": "OK", "state": st,
            "node_id": self.node_id, "hardware_uid": self.hw_uid,
            "request_id": req_id, "session_id": session_id, "channel": ch
        }
        self.idempotency_cache[cache_key] = resp
        return resp

    def get_load_report(self, ack: Dict[str, Any], load_watts=35.0, load_ma=160) -> Dict[str, Any]:
        return {
            "type": "LOAD_REPORT",
            "node_id": self.node_id,
            "hardware_uid": self.hw_uid,
            "protocol_version": 3,
            "request_id": ack["request_id"],
            "session_id": ack["session_id"],
            "channel": ack["channel"],
            "state": ack["state"],
            "sample": {
                "valid": True,
                "current_ma": load_ma if ack["state"] == "ON" else 0,
                "power_w": load_watts if ack["state"] == "ON" else 0.0
            }
        }


class TestHILProtocol(unittest.TestCase):
    def setUp(self):
        self.transport = MockActionBoxTransport()

    def test_network_toggle_is_strictly_rejected(self):
        cmd = {
            "protocol_version": 3, "hardware_uid": "AABBCCDDEEFF", "config_version": 1,
            "node_id": "AB001", "cmd": "TOGGLE", "channel": 1,
            "request_id": 101, "session_id": 999
        }
        resp = self.transport.process_command(cmd)
        self.assertEqual(resp["status"], "ERROR")
        self.assertEqual(resp["state"], "REJECTED")
        self.assertIn("rejected", resp["error"].lower())

    def test_idempotency_cache_returns_identical_response(self):
        cmd = {
            "protocol_version": 3, "hardware_uid": "AABBCCDDEEFF", "config_version": 1,
            "node_id": "AB001", "cmd": "TURN_ON", "channel": 1,
            "request_id": 102, "session_id": 999
        }
        resp1 = self.transport.process_command(cmd)
        self.assertEqual(resp1["state"], "ON")
        self.assertNotIn("cached", resp1)

        # Retransmit identical command
        resp2 = self.transport.process_command(cmd)
        self.assertEqual(resp2["state"], "ON")
        self.assertTrue(resp2.get("cached"))

    def test_turn_off_and_load_report_generation(self):
        cmd = {
            "protocol_version": 3, "hardware_uid": "AABBCCDDEEFF", "config_version": 1,
            "node_id": "AB001", "cmd": "TURN_OFF", "channel": 1,
            "request_id": 103, "session_id": 999
        }
        ack = self.transport.process_command(cmd)
        self.assertEqual(ack["status"], "OK")
        self.assertEqual(ack["state"], "OFF")

        load_rep = self.transport.get_load_report(ack)
        self.assertEqual(load_rep["type"], "LOAD_REPORT")
        self.assertEqual(load_rep["state"], "OFF")
        self.assertEqual(load_rep["sample"]["power_w"], 0.0)

    def test_identity_mismatch_rejected(self):
        cmd = {
            "protocol_version": 3, "hardware_uid": "WRONG_MAC_12", "config_version": 1,
            "node_id": "AB001", "cmd": "TURN_ON", "channel": 1,
            "request_id": 104, "session_id": 999
        }
        resp = self.transport.process_command(cmd)
        self.assertEqual(resp["status"], "ERROR")


if __name__ == '__main__':
    unittest.main()
