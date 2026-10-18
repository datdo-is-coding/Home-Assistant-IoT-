# Home Competition Core V1 Implementation Plan

**Goal:** Implement the supplied nine-phase contract in the existing repository.
**Architecture:** Shared HC codec; transactional Gateway; adapters in existing
firmware and Flutter. Preserve legacy behavior until explicit enrollment.
**Stack:** ESP-IDF 6.0.2 C/C++, Python 3.12 + SQLite, Flutter/Dart.
**Spec:** `docs/architecture/core_v1_design.md` and the supplied master prompt.

## Constraints and review focus

- No network TOGGLE, fake APPLIED result, inferred W/kWh, shared production key,
  unapproved eFuse operation or hardware PASS based on simulation.
- Cross-home references must fail before mutation; duplicate packets must not
  actuate twice; stale boots/revisions must not overwrite newer state.
- Pending commands must be canceled on rebinding/revocation; API/WS credentials
  must never be sent in query strings or log output.
- Failed OTA verification must leave the existing boot slot selected.
- Existing ActionBox_V2 pin map and voice/safety tasks are authoritative.

## Tasks, in dependency order

- [x] Phase 1: source audit and baseline driver tests; write current_state.md,
  architecture, migration strategy and this plan before product code.
- [ ] Phase 2: `common/hc_core/hc_protocol.{h,c}`, Gateway `core_v1/protocol.py`,
  shared vectors and host tests. Test bad length/version/MAC, endian parity,
  duplicates, boot admission, bounded retry and fragmentation before implementation.
- [ ] Phase 3: `core_v1/{database,registry,api,service}.py` and migrations;
  tests create homes/rooms, challenge/claim/confirm, 3 channels, unique binding,
  cross-home authorization, reboot, replay and command ACK/revision handling.
- [ ] Phase 4: integrate HC identity/storage/transport workers in SubBox and
  ActionBox_V2; build both with IDF 6.0.2. Test encrypted peer admission, four-peer
  capacity, channel resynchronization and config ACK through host simulation.
- [ ] Phase 5: connect actual three relay/BL0942 paths to HC state and command
  routing; test local changes, invalid CT, rebind and hardware error handling.
- [ ] Phase 6: typed Core client and management flow in existing Flutter;
  test authenticated requests, pending commands, reconnect snapshot and errors.
- [ ] Phase 7: signed artifact validation, bounded OTA sender/receiver and
  post-boot result; test wrong model/hash/signature, missing/repeated chunks,
  interrupted transfer and rollback. Add release/backup tooling.
- [ ] Phase 8: regression suites, simulator, API integration, firmware builds,
  Flutter analysis/tests; fix verified failures and perform final independent review.
- [ ] Phase 9: protocol/API/build/flash/provisioning/OTA/HIL docs and evidence
  report with file inventory and explicit PASS/FAIL/UNVERIFIED status.

Each implementation task starts with a failing behavioral test, then runs the
relevant suite after implementation. Record commands/results in the delivery
report. Keep changes reviewable in this workspace; do not flash, deploy or commit
unrelated work. User explicitly requested continuous implementation, so no
additional design approval gate is inserted between phases.

## Continuation evidence — 2026-10-15

Implementation is present across the listed phases. Unchecked phase boxes remain
acceptance gates, not an instruction to recreate existing modules. This round
continues Phase 8 and refreshes Phase 9 documentation:

- Fixed actual IDF build failures: ActionBox command field and SubBox credential
  buffer sizes. Both firmware targets built successfully after those fixes.
- Added five Gateway commissioning regressions for envelope layout, proof ordering,
  tampering, expiry and lost-accept recovery.
- Reproduced and fixed Flutter command-state lockup on incomplete successful HTTP
  replies; retries retain the same idempotency key and polling verifies command ID.
- Reproduced SubBox ignoring the enrolled MQTT URI in favor of an old USB setting;
  keep the enrolled URI and continue requiring USB-installed TLS trust/credentials.
- Run results and hardware boundaries: `docs/testing/test_plan_and_report.md`.
- No flash, deployment or commit was performed. Physical provisioning, radio,
  relay contacts, CT calibration and power-cut OTA still require the HIL plan.
