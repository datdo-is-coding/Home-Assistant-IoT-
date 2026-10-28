# HomeCompetition 1.2.3 — Firebase device commissioning

## Implemented behavior

Add device now uses an authenticated, UID-scoped Firebase RTDB mailbox in the
existing Gateway process. It selects the legacy wizard or the existing Core
Security1 workflow from the Gateway's trusted commissioning context. Broker,
room, parent, channel and OTA key checks remain on the Gateway. There is no
fallback to a Gateway HTTP port.

Core claims remain pending until independently authenticated device and parent
receipts arrive. Logical claim/prepare retries are idempotent; expired claims
are reported as expired. Configured Firebase users receive Installer membership
only in the configured Core home. The existing radio coordinator remains the
only radio bridge; the Firebase worker opens its registry with `recover=False`.

Physical testing exposed and corrected these integration defects:

- Vietnamese input changed `DD` in a device ID to `Đ`. The ID field now uses a
  password-style keyboard with correction/suggestions disabled, and Vietnamese
  labels. Exact input was verified on the real phone.
- Android could select a different Wi-Fi network on a phone with multiple
  active Wi-Fi connections. Both native provisioning paths now select the
  Box's `192.168.4.x` network unless a setup network was explicitly requested.
- ESP-IDF rejects empty HTTP bodies. Security1 info/status reads now carry a
  byte before encryption.
- A zeroed protocomm config selected port zero and task priority zero. The
  firmware now uses the SDK defaults with its larger existing stack; the host
  fixture checks port 80 and nonzero priority.
- ActionBox was given a random PMK that differed from its SubBox. The Gateway
  now retains the parent's PMK in an encrypted registry table and uses it for
  that parent's children, while generating distinct per-link LMKs. Missing or
  conflicting imported radio keys are rejected. The private pilot importer
  checks parent identity before importing its key. No radio key is exposed by
  commissioning context. See the [Espressif network example](https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP_NOW/examples/ESP_NOW_Network/ESP_NOW_Network.ino).
- SDK Security1 informational key dumps are suppressed in the new firmware;
  warnings and errors remain enabled.

The physical window remains 180 seconds; BOOT instructions recommend four
seconds to exceed the three-second threshold. Ten seconds still means reset.
Model training remains stopped, and the stock model partition was retained.

## Deployment and backups

The dedicated `homecompetition-gateway` service account has Firebase Realtime
Database Admin in `home-companion-fed2e`. Its RSA key was generated and retained
on the Pi; only the public certificate was uploaded. The unused earlier key was
removed. The uploaded certificate expires on 2027-10-27.

Live Rules were backed up, then the reviewed commissioning namespaces were
published with root grants disabled. Existing public `/devices` Rules were
preserved for existing clients. This remains an internal pilot; that public
legacy branch is not production tenant isolation.

The existing Pi main service was updated after code, environment and consistent
SQLite backups. Credentials and deployed Rules passed the real preflight. The
phone account's grant and fresh Firebase heartbeat were verified. PMK import
matched a fingerprint read from the actual SubBox NVS and stored the key under
the registry master key. The radio service was not restarted for this change.

The source work is on `codex/commercial-ota`; the commit on `main` was preserved.
After a branch switch, run `flutter pub get` before a no-pub build so the ignored
Android plugin registrant is regenerated. Dart tests alone cannot establish
that native Firebase plugins are packaged. The final APK was installed without
clearing app data; Firebase startup and login retention were checked on-device.

DDF4 had an uncommitted factory enrollment for node 1 when re-inspected. No
registered DDF4 entry existed in the Pi. A complete 16 MiB backup was assembled
and compared against the physical flash with the ROM digest check:
`558e3057bbdaabecee7f39e2b2edbd71056b0a96a7ef25ddad2579a7a43e5186`.
Only its application partition was flashed. The model matched the stock build;
factory calibration/UID and manufacturing credentials were verified unchanged.
Enrollment, PHY calibration cache and boot metadata changed through their normal
runtime paths. The application contains no per-device factory bundle.

## Physical commissioning acceptance

DDF4 completed the real Android/Firebase/Security1 flow. The successful claim is
`CLAIM-de04d946689243b9e663522e`, logical node 3476309, parent 3476308 (SubBox 0B54).
The registry contains both independently verified receipts, `REGISTERED` and
`ONLINE`, and channels 1, 2, 3. The phone displayed step 5/5 and “Gateway đã xác minh
đăng ký”. Screenshot: `/tmp/homecompetition-ddf4-registered.png`.
After repository cleanup, the installed APK is retained at
`releases/android/HomeCompetition.apk`; stock regression data and archived
historical evidence are indexed by `archive/2026-10-28-cleanup/manifest.json`.

The earlier mismatched-PMK claim expired without receipts and was not treated as
successful. No registration, receipt, channel or relay telemetry was fabricated.
The UI test driver encountered a timing race when its Check button disappeared
after success; the captured success screen and independent registry evidence
confirmed the result.

## Verification and limits

- Gateway: 449 tests passed with the official RTDB emulator 4.11.2, including real
  Rules, UID boundaries, forged writes, immutable deadlines, empty RTDB values,
  pending claims, encrypted PMK persistence, key non-disclosure and expiry.
- Flutter: 164 passed; analysis found no issues. APK 1.2.3/code 18 retains the
  existing application identity and signing key.
- Firmware: 39 host tests ran successfully, including 5 opt-in skips, using the IDF Python runtime.
  The updated HTTP-config regression also passed. ActionBox and SubBox builds
  passed for 2.0.1-b1.
- Actual radio receipts and the real phone success screen establish physical
  commissioning, separately from host/emulator checks.

On the continuation into 2026-10-28, both boards completed signed OTA 2.0.1-b1
through the local Pi pilot:

| Board | Job | Final status | Transferred bytes |
| --- | --- | --- | ---: |
| DDF4 | `OTA-44d28e8ee5c1c10e58003f59` | `SUCCEEDED` | 1,351,232 |
| SubBox 0B54 | `OTA-72609e2afd20e5e9fc36219c` | `SUCCEEDED` | 1,189,632 |

Each rebooted and reported the expected version and image digest. After an
additional controlled reboot to capture final NVS backups, both remained
`REGISTERED`, reported configuration revision 1, and sent fresh heartbeats.
Firebase projected both online with firmware 2.0.1-b1 and three DDF4 channels.

The post-OTA NVS checks confirmed committed enrollment, channel 11, matching
parent/child PMKs and grant nonces, and release counter 3 / security epoch 0 on
both boards. Manufacturing credentials, ActionBox `factory_data` and
`user_config`, and SubBox hardware identity/user configuration were unchanged.
Only expected enrollment, OTA confirmation, PHY cache and boot metadata changed.
The updated NVS and a consistent Core SQLite snapshot were saved privately for
recovery. No private keys or setup codes are included in this report.

Core projections in this commissioning transport contain registered inventory
and availability. Relay control/bindings and load confirmation are separate;
missing reported states/current are not invented. No real loads are connected.
DDE8 was not flashed. Internet fleet deployment/billing remains disabled by the
user's choice to test internally first.
