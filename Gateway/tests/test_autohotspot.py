"""Exercise hotspot decisions with a fake NetworkManager, never real interfaces."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AutoHotspot(unittest.TestCase):
    def run_scenario(self, state, saved_connects='0'):
        script = Path(__file__).resolve().parents[1] / 'systemd' / 'autohotspot.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nmcli = root / 'nmcli'
            nmcli.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALL_LOG"
case "$*" in
  '-t -f DEVICE,STATE device status') printf '%s\\n' "$NETWORK_STATE" ;;
  '-t -f UUID,TYPE connection show') printf 'wifi-id:802-11-wireless\\nhotspot-id:802-11-wireless\\n' ;;
  '-g connection.id connection show uuid wifi-id') printf 'Home WiFi\\n' ;;
  '-g connection.id connection show uuid hotspot-id') printf 'Aetheria-Hotspot\\n' ;;
  '--wait 10 connection up uuid wifi-id') [ "$SAVED_CONNECTS" = 1 ] ;;
  '--wait 15 connection up id Aetheria-Hotspot') exit 0 ;;
  *) exit 99 ;;
esac
''')
            nmcli.chmod(0o755)
            logger = root / 'logger'
            logger.write_text('#!/bin/sh\nexit 0\n')
            logger.chmod(0o755)
            env = dict(os.environ, PATH=f'{root}:/usr/bin:/bin', NETWORK_STATE=state,
                       SAVED_CONNECTS=saved_connects, CALL_LOG=str(root / 'calls'))
            subprocess.run(['bash', str(script)], env=env, check=True, capture_output=True, timeout=5)
            return (root / 'calls').read_text()

    def test_existing_ethernet_and_wifi_are_never_changed(self):
        for state in ('eth0:connected', 'wlan0:connected'):
            self.assertNotIn('connection up', self.run_scenario(state))

    def test_saved_network_precedes_hotspot(self):
        calls = self.run_scenario('wlan0:disconnected', '1')
        self.assertIn('connection up uuid wifi-id', calls)
        self.assertNotIn('connection up id Aetheria-Hotspot', calls)

    def test_hotspot_only_after_saved_network_fails(self):
        calls = self.run_scenario('wlan0:disconnected')
        self.assertIn('connection up id Aetheria-Hotspot', calls)
        self.assertNotIn('connection up uuid hotspot-id', calls)


if __name__ == '__main__':
    unittest.main()
