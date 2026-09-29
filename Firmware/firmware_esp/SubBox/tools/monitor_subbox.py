#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubBox Real-time Serial Monitor & Verification Tool
Monitors COM9 for ESP-NOW audio streaming, NLU resolution, and ActionBox actuation commands.
"""

import sys
import time
import serial

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM9'
BAUD = 115200

print(f"================================================================")
print(f"  SubBox ESP-NOW Real-time Monitor on {PORT}")
print(f"  Listening for Audio Streams & Command Dispatch...")
print(f"================================================================")

try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
except Exception as e:
    print(f"Error opening {PORT}: {e}")
    sys.exit(1)

buffer = ""
start_time = time.time()
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 0

try:
    while True:
        if timeout > 0 and (time.time() - start_time) > timeout:
            break
        raw = ser.read(ser.in_waiting or 1)
        if raw:
            try:
                text = raw.decode('utf-8', errors='replace')
            except Exception:
                text = str(raw)
            buffer += text
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip('\r')
                if not line:
                    continue
                # Highlight important events
                if "ESPNOW RX" in line or "Audio STREAM" in line:
                    print(f"\033[96m[AUDIO ESP-NOW]\033[0m {line}")
                elif "NLU Processing" in line or "IntentParser" in line:
                    print(f"\033[93m[NLU PIPELINE]\033[0m  {line}")
                elif "LOCAL EXECUTION" in line or "ESPNOW TX CMD" in line:
                    print(f"\033[92m[RELAY ACTUATE]\033[0m {line}")
                elif "ERROR" in line or "error" in line or "failed" in line:
                    print(f"\033[91m[WARN/ERROR]\033[0m    {line}")
                else:
                    print(f"  {line}")
                sys.stdout.flush()
        else:
            time.sleep(0.01)
except KeyboardInterrupt:
    print("\nMonitor stopped by user.")
finally:
    ser.close()
