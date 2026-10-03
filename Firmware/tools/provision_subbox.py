#!/usr/bin/env python3
"""Provision a SubBox over USB while its physical BOOT button is held.
Input: private JSON with ssid, password, mqtt_uri, mqtt_user, mqtt_pass, ca_pem.
Optional ws_uri/ws_token enable voice separately. Never prints input or secrets.
"""
import argparse
import json
import time
from pathlib import Path
import serial


def send(port, command, prefix, timeout=5):
    port.write((command + '\n').encode())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = port.readline().decode(errors='replace').strip()
        if line.startswith('PROVISION_ERROR'):
            raise RuntimeError(line)
        if line.startswith(prefix):
            return line
    raise TimeoutError('No USB provisioning response')


def provision(port_name, config, wait_seconds=120):
    required = ('ssid', 'password', 'mqtt_uri', 'mqtt_user', 'mqtt_pass', 'ca_pem')
    if any(not isinstance(config.get(k), str) for k in required):
        raise ValueError('Missing string configuration fields')
    if not config['mqtt_uri'].startswith('mqtts://'):
        raise ValueError('MQTT TLS is required')
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = port_name, 115200, .2
    port.dtr = port.rts = False
    port.open()
    try:
        print('Hold BOOT on the powered SubBox (do not press RESET). Waiting...', flush=True)
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            try:
                reply = send(port, 'PROVISION_STATUS', 'PROVISION_STATUS ', 3)
                if json.loads(reply[len('PROVISION_STATUS '):])['boot_pressed']:
                    break
            except TimeoutError:
                pass
            time.sleep(.3)
        else:
            raise TimeoutError('BOOT was not held; no configuration written')
        for key in ('mqtt_uri', 'mqtt_user', 'mqtt_pass', 'ca_pem', 'ws_uri', 'ws_token'):
            if key in config:
                send(port, 'SEC ' + json.dumps({'key': key, 'value': config[key]}), 'PROVISION_OK')
        send(port, 'WIFI ' + json.dumps({'ssid': config['ssid'], 'password': config['password']}), 'PROVISION_OK')
        # Release BOOT before restart: otherwise ESP32 could enter download mode.
        print('Configuration saved. Release BOOT now.', flush=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            reply = send(port, 'PROVISION_STATUS', 'PROVISION_STATUS ', 3)
            if not json.loads(reply[len('PROVISION_STATUS '):])['boot_pressed']:
                print('Press RESET once to apply the new configuration.', flush=True)
                return
            time.sleep(.3)
        raise TimeoutError('Release BOOT, then press RESET to apply saved configuration')
    finally:
        port.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--wait', type=int, default=120)
    args = parser.parse_args()
    provision(args.port, json.loads(args.config.read_text()), args.wait)
