# Home Competition Core V1 Test Report & HIL Test Plan

## 1. Automated Test Results Summary

Evidence refreshed on **2026-10-15** from the current working tree. A build or
host test is software evidence only; every physical scenario below is **UNVERIFIED**.
This supersedes the earlier 58-test/4-test report, which predated secure commissioning.

| Test Suite | Scope | Target | Result | Notes |
|---|---|---|---|---|
| `Gateway/tests/test*.py` | 138 executions | Core and legacy Gateway suites | **138/138 PASS** | 112 distinct test IDs / 99 distinct methods; imported and inherited fixture tests execute repeatedly. Core contributes 89 executions, including 5 new commissioning cases. |
| Flutter `test/` | 24 tests | Core client and existing app | **24/24 PASS** | Includes 6 Core tests; malformed command replies keep an uncertain outcome and reuse the idempotency key; unrelated polling replies cannot complete a command. |
| `Firmware/tests/test*.py` | 7 host tests | Relay, metering, safety, audio, NLU, MQTT initialization | **7/7 PASS** | Real driver code with host doubles at hardware/transport boundaries; MQTT uses enrolled URI and still requires TLS trust. |
| Firmware SubBox | ESP-IDF v6.0.2 | ESP32-S3 | **PASS** | `SubBox.bin`: 0x113370 bytes, 63% of smallest app partition free. SSID/password retain complete input; enrolled MQTT URI is preserved. |
| Firmware ActionBox_V2 | ESP-IDF v6.0.2 | ESP32-S3 | **PASS** | `ActionBox_V2.bin`: 0x145240 bytes, 57% of smallest app partition free. Corrected command field reference. |
| Android debug APK | Flutter 3.44.8 / Dart 3.12.2 | Native provisioning bridge and final Core client | **PASS** | `App/dtv_energy_flutter/build/app/outputs/flutter-apk/app-debug.apk`. This does not verify an Android-to-Box session. |
| Dart analysis | Entire Flutter project | Static diagnostics | **106 informational findings; 0 warnings/errors** | Mainly deprecated styling APIs and braces; not a clean lint result. Earlier `flutter analyze` exited 1 for these infos; final `dart analyze` exited 0 with the same count. |

Commands (run from repository root unless noted):

```bash
PYTHONPATH=Gateway /home/tuan/.venv/bin/python -m unittest discover -s Gateway/tests -v
python3 -m unittest discover -s Firmware/tests -p 'test*.py' -v
# In App/dtv_energy_flutter:
/home/tuan/snap/flutter/common/flutter/bin/flutter test --reporter expanded
/home/tuan/snap/flutter/common/flutter/bin/flutter build apk --debug
/home/tuan/snap/flutter/common/flutter/bin/dart analyze
# In each firmware target directory:
idf.py build
```

The explicit Python/Flutter paths identify the existing local environments used
for this run. Other machines should use their installed equivalents. System
Python lacks Gateway dependencies; the Snap Flutter launcher returned 255 for
some commands, while the installed SDK executable ran successfully.

New commissioning tests cover the 547-byte envelope and firmware offsets,
maximum Wi-Fi credential lengths on the wire, authenticated receipts arriving
in either order, tampering, expiry, foreign-user access, one-envelope-per-claim,
and lost-accept retry through the real binary Gateway bridge. They do not execute
the firmware provisioning parser or prove radio interoperability.

Independent review of the command-field, Wi-Fi-length and Flutter-response fixes
found no issues. It also reran the 5 commissioning and 6 Core Flutter tests.
The later MQTT URI correction has its own failing-then-passing host regression.

---

## 2. Hardware-In-The-Loop (HIL) Test Plan

All scenarios below remain **UNVERIFIED**. Use one Gateway, two SubBoxes and
multiple ActionBoxes; include four children under one SubBox and a rejected fifth.

### HIL-1: SubBox & ActionBox Provisioning
1. Install unique factory credentials and SubBox TLS trust/credentials as described in the provisioning guide. Hold BOOT for 3 seconds and release. Verify `siciot_sub_XXXXXX` SoftAP appears; its channel can follow STA when already connected.
2. Complete pairing from the Android Flutter App using the setup code and private AP password. Verify the Gateway reports `REGISTERED`, then verify NVS retains credentials across power cycle. Repeat with a 32-byte SSID and supported maximum-length Wi-Fi key.
3. Boot unconfigured ActionBox_V2. Verify pairing discovery by SubBox and successful claim authorization.
4. Verify Gateway registers `HC-{MAC}:CH1`, `CH2`, and `CH3` in `UNBOUND` state.

### HIL-2: Relay Actuation & Safe Initialization
1. Issue `SET_STATE` (ON) to Relay 1. Measure 50ms pulse on SET GPIO 16 with oscilloscope.
2. Cut device power while Relay 1 is latched ON.
3. Restore power. Verify boot initialization applies safe RESET pulses without contact chatter. Check actual contacts rather than trusting only software state.
4. Issue `SET_STATE` (OFF). Measure 50ms pulse on RESET GPIO 15.

### HIL-3: BL0942 Current Metering & Fault Detection
1. Connect 100W resistive load to Relay 1 output.
2. Read `current_rms_a` via Gateway API. Verify reading matches calibrated ammeter (±2% tolerance).
3. Disconnect BL0942 UART RX wire. Verify ActionBox transitions channel state to `ct_valid = 0` and `current_rms_a = null` (no fake zero readings).

### HIL-4: ESP-NOW & Wi-Fi Coexistence
1. Change Wi-Fi channel on router from Channel 1 to Channel 6.
2. Verify SubBox follows Wi-Fi channel change.
3. Measure ActionBox channel-recovery time and verify it locates SubBox on Channel 6 without rebooting. Do not report a timing guarantee from host tests.

### HIL-5: Three-Tier OTA with Power Loss
1. Initiate OTA on ActionBox over ESP-NOW.
2. Disconnect ActionBox power at 50% chunk progress.
3. Power on ActionBox. Verify it boots into the previously selected working partition and remains operational.
4. Re-run OTA to 100%. Verify ActionBox boots the alternate slot, passes self-test, and only then Gateway marks the job `SUCCEEDED`. Repeat for SubBox and inject a failing health check to exercise rollback.
