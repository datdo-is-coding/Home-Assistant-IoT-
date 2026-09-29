#!/usr/bin/env python3
"""
ActionBox Automated Test Suite & Interactive Controller
Aetheria OS / Smart Home IoT Architecture

Sends and validates protocol commands for ESP32-S3 ActionBox:
- TURN_ON, TURN_OFF, TOGGLE
- GET_STATE, GET_CURRENT, GET_POWER
- CLEAR_FAULT, PING, SET_CONFIG
- Idempotency verification (duplicate request_id retransmission)
"""

import sys
import time
import json
import argparse

try:
    import serial
except ImportError:
    serial = None

COLOR_GREEN  = "\033[92m"
COLOR_CYAN   = "\033[96m"
COLOR_YELLOW = "\033[93m"
COLOR_RED    = "\033[91m"
COLOR_RESET  = "\033[0m"

class ActionBoxTester:
    def __init__(self, port="COM8", baudrate=115200, node_id="AB001"):
        self.port = port
        self.baudrate = baudrate
        self.node_id = node_id
        self.request_id = 1000
        self.ser = None

    def connect(self):
        if not serial:
            print(f"{COLOR_RED}[ERROR] 'pyserial' not installed. Run: pip install pyserial{COLOR_RESET}")
            return False
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1.0)
            self.ser.dtr = False
            self.ser.rts = False
            print(f"{COLOR_GREEN}>>> Connected to ActionBox on {self.port} at {self.baudrate} baud.{COLOR_RESET}")
            return True
        except Exception as e:
            print(f"{COLOR_RED}[ERROR] Could not open port {self.port}: {e}{COLOR_RESET}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_command(self, cmd_name, channel=1, extra_params=None, custom_req_id=None):
        if custom_req_id is not None:
            req_id = custom_req_id
        else:
            self.request_id += 1
            req_id = self.request_id

        pkt = {
            "version": 1,
            "node_id": self.node_id,
            "request_id": req_id,
            "cmd": cmd_name,
            "channel": channel,
            "timestamp": int(time.time())
        }
        if extra_params:
            pkt.update(extra_params)

        payload = json.dumps(pkt)
        print(f"\n{COLOR_CYAN}TX -> {payload}{COLOR_RESET}")

        if not self.ser or not self.ser.is_open:
            print(f"{COLOR_YELLOW}[MOCK MODE] Serial port not open. Packet created successfully.{COLOR_RESET}")
            return pkt

        self.ser.write((payload + "\n").encode('utf-8'))
        
        # Read response
        start_time = time.time()
        while time.time() - start_time < 2.0:
            line = self.ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                print(f"{COLOR_YELLOW}[RAW] {line}{COLOR_RESET}")
                try:
                    resp = json.loads(line)
                    if "request_id" in resp and resp["request_id"] == req_id:
                        print(f"{COLOR_GREEN}RX <- {json.dumps(resp, indent=2)}{COLOR_RESET}")
                        return resp
                except json.JSONDecodeError:
                    pass

        print(f"{COLOR_RED}[TIMEOUT] No JSON ACK received for request_id {req_id}{COLOR_RESET}")
        return None

    def run_automated_suite(self):
        print("\n=======================================================")
        print("  STARTING AUTOMATED ACTIONBOX VALIDATION SUITE")
        print("=======================================================")

        # Test 1: PING
        print("\n--- Test 1: PING Heartbeat ---")
        self.send_command("PING", channel=0)
        time.sleep(0.5)

        # Test 2: Turn ON Channel 1
        print("\n--- Test 2: Turn ON Relay Channel 1 ---")
        self.send_command("TURN_ON", channel=1)
        time.sleep(0.5)

        # Test 3: Get State Channel 1
        print("\n--- Test 3: Query State Channel 1 ---")
        self.send_command("GET_STATE", channel=1)
        time.sleep(0.5)

        # Test 4: Idempotency Test (Retransmit identical TURN_ON request_id)
        print("\n--- Test 4: Idempotency Retransmission Test ---")
        print("Sending same request_id 1002 again; verify identical cached response returned...")
        self.send_command("TURN_ON", channel=1, custom_req_id=1002)
        time.sleep(0.5)

        # Test 5: Read Current & Power on Channel 1
        print("\n--- Test 5: Query Current & Power Sensor (BL0942) ---")
        self.send_command("GET_CURRENT", channel=1)
        time.sleep(0.2)
        self.send_command("GET_POWER", channel=1)
        time.sleep(0.5)

        # Test 6: Toggle Channel 2
        print("\n--- Test 6: Toggle Relay Channel 2 ---")
        self.send_command("TOGGLE", channel=2)
        time.sleep(0.5)
        self.send_command("TOGGLE", channel=2)
        time.sleep(0.5)

        # Test 7: Turn OFF Channel 1
        print("\n--- Test 7: Turn OFF Relay Channel 1 ---")
        self.send_command("TURN_OFF", channel=1)
        time.sleep(0.5)

        # Test 8: Invalid Channel Safety Rejection Test
        print("\n--- Test 8: Safety Rejection on Invalid Channel (Ch 99) ---")
        self.send_command("TURN_ON", channel=99)
        time.sleep(0.5)

        print("\n=======================================================")
        print("  AUTOMATED VALIDATION SUITE COMPLETE")
        print("=======================================================")

def main():
    parser = argparse.ArgumentParser(description="ActionBox Test CLI & Automated Verification")
    parser.add_argument("--port", default="COM8", help="Serial port (e.g. COM8)")
    parser.add_argument("--baud", default=115200, type=int, help="Baud rate (default: 115200)")
    parser.add_argument("--node-id", default="AB001", help="Target ActionBox Node ID (default: AB001)")
    parser.add_argument("--test", action="store_true", help="Run full automated test suite")
    parser.add_argument("--cmd", choices=["TURN_ON", "TURN_OFF", "TOGGLE", "GET_STATE", "GET_CURRENT", "GET_POWER", "CLEAR_FAULT", "PING"], help="Single command to execute")
    parser.add_argument("--ch", default=1, type=int, help="Relay channel (1 or 2)")

    args = parser.parse_args()

    tester = ActionBoxTester(port=args.port, baudrate=args.baud, node_id=args.node_id)
    connected = tester.connect()

    if args.test:
        tester.run_automated_suite()
    elif args.cmd:
        tester.send_command(args.cmd, channel=args.ch)
    else:
        print("No command specified. Use --test to run automated suite or --cmd <COMMAND> --ch <CHANNEL>.")
        if connected:
            tester.run_automated_suite()

    tester.close()

if __name__ == "__main__":
    main()
