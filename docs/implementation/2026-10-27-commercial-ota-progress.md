# Commercial OTA deployment progress — 2026-10-27

## Authorized objective
Deploy the approved commercial OTA design and perform full checks. Keep truthful
separation between source/build, local signed OTA, actual Internet deployment and
physical power-loss/relay acceptance. No new model training.

## Latest result
- Both eligible bench boards run 2.0.0-b1 installed over the network; actual
  version, running-image hash, new boot and local health verified.
- Passed on hardware: bad signature, wrong compatibility, failed-boot rollback,
  coordinator restart/reconnect, interrupted-transfer resume, and replay of the
  already-confirmed counter on both boards. Replay tests intentionally produce
  FAILED/device_verification_failed with offset 0 and unchanged boot IDs.
- Original NVS user/factory keys preserved: 56 SubBox keys, 12 ActionBox keys,
  no missing keys. Only RF calibration data and ActionBox boot metadata changed;
  lifecycle owner_epoch/reset_generation are unchanged. Both confirmed counter=1,
  security epoch=0, compatibility binding correct and ota_pending cleared.
- Final source checks: Gateway 408 passed; firmware 39 ran (34 passed, 5 skipped).
  Pi updater suite 14 passed; actual Gateway source/runtime stage and import,
  encrypted six-DB backup/decrypt/integrity checks passed. No main-service OTA
  activation is claimed.
- Scope remains internal only: no billing, Cloud Run/Internet rollout, customer
  OTA UI or main.py-to-Core control adapter deployed. DDE8 excluded; physical
  power-cut and loaded-relay acceptance untested. Not a customer rollout build.

## Current preflight
- Gateway pi4@192.168.11.29: service active, existing gateway/main.py.
- USB: SB288485350B54, AB28848533DDF8, AB28848533DDE8.
- Existing .bin artifacts are previous firmware, not the just-designed cloud OTA.
- Firebase Console verified: project home-companion-fed2e is Spark, current user
  is Editor. User selected internal pilot without enabling billing (2026-10-27).
- Fresh backup work is in private /home/tuan/.codex/device-backups/20261027-ota-bootstrap/.
- Pilot deployment is in progress; no cloud Rules/IAM, billing or eFuse changed.

## Decisions and prerequisites confirmed
- User authorizes home-companion-fed2e; live Console permissions are Editor.
- User confirms USB boards have no electrical load connected.
- Work continues on codex/commercial-ota in the existing active checkout, retaining
  all unrelated dirty app changes; no commits or destructive checkout operations.
- Live Pi backup: /home/pi4/.local/state/commercial-ota/1793070667,3 SQLite files
  verified with integrity_check. Source archive SHA256 c103267c27adb6e505a0e8ff9bff22db52f93f4179b27746a1883a06bb88d310.
- Old /home/tuan/.venv resolves to Python3.14 and lacks cryptography after host
  upgrade. OTA/release baseline rerun with IDF Python3.12; no global env modified.

## Internal pilot preparation and current results
- Fresh 0..0x610000 flash backups completed on all three boards, SHA256 recorded
  privately. Bootloader, partition table, NVS and both application slots covered;
  model partition is untouched. ROM reads used after repeated stub read failures.
- DDE8 has the old Arduino layout and is excluded from this pilot. No layout
  migration or firmware write performed on DDE8.
- SubBox 0B54 and ActionBox DDF8 received per-device factory bootstrap 2.0.0-b0
  in both app slots, with successful flash hash verification. Existing
  bootloader/layout/model preserved. Enrollment uses normal NVS APIs and GC;
  no raw NVS replacement, calibration erase, or relay pulse.
- Runtime verification found SubBox main-task stack exhaustion. Bootstrap
  buffers moved out of its stack; both boards use an 8192-byte main stack.
  SubBox boot/fully operational/MQTT and ActionBox safety/relay/sensor task boot
  verified from live serial. No relay actuation requested.
- Isolated OTA user service is installed on Pi with a private venv/config/DB,
  separate from the existing control Gateway service, which remains unchanged.
- Bench factory enrollment enables the existing Core firmware path. The legacy
  main.py-to-Core control adapter is not implemented in this pilot; app/voice
  relay operation after this enrollment is not accepted. Do not migrate customer
  devices using the pilot roster/service. Boards remain unloaded bench devices.
- EMQX ACL adds only the pilot hc/v1 topics, preserving prior rules. TLS broker
  connection from the coordinator verified. Python 3.13 rejected the legacy CA
  missing KeyUsage; explicit local pilot compatibility disables only strict X509
  parsing, retaining chain and hostname verification. Remove when CA rotates.
  Added an explicit hc/v1/# deny after the exact grants. Live subscription test
  passed: upstream SUBACK=1, forbidden downstream SUBACK=128. aiomqtt returns
  rejected SUBACK codes instead of raising; the initial test wrongly assumed an
  exception. Corrected the test using the actual return codes. No account/IAM
  changes or additional broker identity were needed.
- Source checks: Gateway 401 passed; firmware 39 ran, 5 skipped. Additional local
  coordinator checks cover immutable signed target metadata and status reads
  preserving a running transfer. Final rerun required after hardware fixes.
- Pi user service initially died when SSH closed; enabled lingering for pi4.
  Existing main system service is unchanged. Both pilot nodes now authenticate
  and report ONLINE via MQTT-TLS/ESP-NOW.
- Found a radio recovery bug: ActionBox hopped immediately after HELLO, before
  the Gateway challenge returned. Added a 500 ms response window after HELLO.
  Actual coordinator restart test requires fresh last_seen timestamps; both
  boards reconnected in 7.05 s, with unchanged boot IDs (no board USB reset).
- Initial OTA runs were intentionally superseded during diagnosis; recorded as
  FAILED with gateway_restart/superseded reasons, never counted as success.
- Local coordinator now sends at most four sequential 192-byte chunks and
  uses cumulative progress, bounded five-second retry budget, and authenticated
  same-manifest resume. Tests cover partial/future ACKs, duplicate metadata,
  restart/status behavior, resume and timeout. Legacy callers keep window=1 and
  one-second retries. The first full transfer timed out at 1,247,232 bytes of
  1,351,184; SubBox's following start also timed out. Neither counts as success.
  Fixed partial cumulative ACK handling to retry from the first missing chunk,
  rather than repeatedly retransmitting an already accepted prefix. Slowed the
  local retry interval to 500 ms; partial forward progress resets retry attempts.
  Authenticated stale/duplicate ACKs are ignored without advancing state.
  The interrupted transfer did resume on hardware: old job stopped at 127296;
  the first progress event for new job OTA-4d714e92aaee86ac08c01b59 was 127488,
  with the same device boot. Its later timeout remains separately recorded.
- Negative probes exposed another reporting bug: device rejection can carry an
  offset from its previous transfer, larger than the newly offered image. The
  coordinator now accepts status=2 as failure independently of that offset;
  no offset is committed. Regression test covers UINT32_MAX rejection offset.
  Physical signature and wrong-compatibility probes now both return FAILED /
  device_verification_failed at offset 0. These deliberately alter the private
  pilot target row to bypass host admission and exercise the device verifier;
  local coordinator upload itself also rejects both. Valid target restored afterward.
- A separate 163,936-byte app fixture (2.0.0-b2) intentionally restarts after
  three seconds, never confirms boot, and contains no GPIO calls. Transferring
  it via normal signed radio OTA tested automatic bootloader rollback: serial
  shows ota_1 / 2.0.0-b2, then ota_0 / 2.0.0-b0. Gateway received the actual
  rollback report and recorded ROLLED_BACK / boot_health_failed, 163936 bytes,
  job OTA-d8c3a4e679abaa711840efaa; ActionBox returned ONLINE with a new boot ID.
  The larger failed-health fixture was built privately but is not installed.
  Full healthy DDF8 b1 update then passed: OTA-07f54b6232c876b8cd85e1ae,
  SUCCEEDED, 1351184 bytes, actual version 2.0.0-b1 and SHA256
  4f7f8e4fc70d2c8a95dc8a8e6d326b090f4acf47e699866a020e62005f3c4306,
  new boot ID 16126928337983955889.
- SubBox installed the full 1189600-byte image, but its image verification took
  longer than the old five-second chunk timeout. Authenticated actual result:
  version 2.0.0-b1, SHA256
  6726f864612a9ca57aeea780f62205cf278fa452192c5d774393fb9b964c5a41,
  health=1, boot 13959943458773595413. Added an explicit VERIFYING phase with a
  300-second bound, stopped sending offers on a new boot, and accepted only a
  matching late result for the latest failed full transfer. Job
  OTA-fcd6f2dc6b27e048dd6153bb reconciled to SUCCEEDED/late_boot_confirmation.
  The original timeout event remains in its history. Regression checks reject
  same-boot or wrong-hash late results; retries/receipts cannot invent success.
- Result receipt ACKs now remain idempotent after a job is terminal; the device
  only clears pending metadata after its own local health check. Duplicate
  coordinator startup is locked before DB recovery; tested against the live Pi
  service. MQTT SUBACK rejection is checked explicitly rather than inferred from
  absence of a Python exception. Existing Gateway service remains active.
- Pilot channel names corrected to the Registry's factory-ID:CHn format. Actual
  reports now show relay states 0/0/0 and CT current 0 A. This is reported
  electrical/software state, not load confirmation.
- Actual Gateway code and pinned runtime staged on Pi as releases/2.0.0;
  relocated runtime successfully imported the real main.py. Staging refused
  unlisted DBs; inventory expanded to all six SQLite files, including legacy
  auth/memory and registry_core. This is staging/import evidence, not service
  activation or runtime health acceptance. Stage-only config has no credential
  file inventory and must not be promoted to production activation as-is.
- Real six-DB encrypted snapshot created with the updater's backup routine:
  database-snapshot-1793077480.enc, 16957540 bytes, SHA256
  ab2fe1edb6678404d41e89b6014d25ceedea68ca9f81977d958166c4f7ee596f.
  Decryption verified all six members; SQLite backup integrity/schema checks
  passed. Archive and separate recovery-key file also backed up privately on
  the developer workstation. Configuration-file inventory is still incomplete.
- Anti-rollback HIL: OTA-aec373826e970023e73bfb5c (DDF8) and
  OTA-d99f2d44118abab1f4151009 (SubBox) rejected their already-confirmed counter=1
  before any transfer, preserving running version/boot. Both remain ONLINE.
- No cloud deployment, Internet OTA, main Gateway activation, app/voice control
  integration or physical power-cut acceptance has passed yet.
