# Commercial Fleet OTA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap eligible connected devices, implement signed remote OTA and verify Gateway/SubBox/ActionBox recovery without losing the current application or customer data.

**Architecture:** Firebase/Auth + cloud job service, an independent Gateway agent/updater, and authenticated Core OTA transport. Existing gateway/main.py remains the application runtime. Work is staged so host checks, local hardware OTA and Internet acceptance have separate evidence.

**Tech Stack:** Existing Python/aiohttp/cryptography/SQLite, Firebase Admin, ESP-IDF6.0.2/P-256, systemd, Flutter.

**Spec:** docs/superpowers/specs/2026-10-27-commercial-fleet-ota-design.md

**Current deployment scope (user decision):** internal pilot first; no billing.
Firebase is Spark and the signed-in account is Editor. Cloud deployment,
Internet campaigns and customer OTA UI remain deferred; local testing does not
count as Internet acceptance. Live results are in the implementation progress log.

## Global Constraints

- No erase-flash, eFuse burn, partition migration or model training.
- Keep ActionBox relay authority; do not pulse relays for OTA health tests.
- Native USB MAC mapping and fresh verified rollback image before any write.
- Project/control credentials must come from authorized administration; app login is not IAM authority.
- Preserve active Gateway main.py and all data/secrets; use independent OTA services.
- Cloud grants expire120s for starting one target; offline defers new work.
- Cloud-signature and board-incompatibility rejection are mandatory.
- Never report SUCCEEDED from download/chunk ACK alone.
- Preserve dirty HomeCompetition app changes; no unrelated cleanup or commit.

## Review Focus

1. Loss of power at each boot/activation boundary must preserve a recoverable slot.
2. Missing enrollment/OTA trust root blocks updates rather than enabling an unsigned path.
3. Cross-home/old owner/old grant requests cannot start updates.
4. App-only rollback does not repair bootloader/model/layout changes; reject such packages.
5. Gateway backup covers the actual active runtime/data, not just a new Core DB.

### Task1 — Inventory and rollback evidence

**Files:** docs/implementation/2026-10-27-commercial-ota-progress.md; private /home/tuan/.codex/device-backups/20261027-ota-bootstrap/.
- [x] Read actual live serial/boot identity, NVS enrollment, partition and bootloader.
- [x] Back up every written region with SHA-256; fail closed on incomplete read.
- [x] Back up live Pi source/config/SQLite consistently and record active unit.
- [x] Record actual connected model/revision/capability and safe-load condition.

### Task2 — Signed target metadata and checks

**Files:** Gateway/gateway/fleet_ota/manifest.py; Firmware/firmware_esp/common/hc_core/hc_ota_manifest.{h,c}; Gateway/tests/test_fleet_ota_manifest.py; Firmware/tests/test_fleet_ota_manifest.py.
- [x] RED: test112-byte header/176-byte signed target, wrong identity/hash/key/version/counter.
- [x] Implement strict spec fields and compatibility IDs; old metadata explicitly versioned.
- [x] GREEN: shared Python/C vectors and existing Core OTA suites.

### Task3 — Cloud policy/job control

**Files:** Gateway/gateway/fleet_ota/{service,policy,store,identity}.py; Gateway/tests/test_fleet_ota_service.py; deployment files for Cloud Run and RTDB Rules.
- [x] RED: tenant isolation, no self-admin, revoked campaign, stale policy, single-use120s grant, lease fencing.
- [x] Implement authenticated endpoints and persistent transitions; Firebase adapter denies missing credentials.
- [x] GREEN: local test backend.
- [ ] Authorized project deployment and Internet contract tests (deferred, no billing).

### Task4 — Gateway agent and legacy adapter

**Files:** Gateway/gateway/fleet_ota/{agent,coordinator,inventory}.py; Gateway/systemd/homecompetition-ota-agent.service; Gateway/tests/test_fleet_ota_agent.py.
- [ ] RED: offline staging, fresh grant per target, restart reconciliation, mixed versions, no concurrent updater.
- [x] Reuse Core OTA/bridge selectively; never start a competing full Core command server.
- [ ] GREEN: mocked network tests; deploy independent agent without changing main.py modes.

### Task5 — Gateway updater recovery

**Files:** Gateway/gateway/ota_updater.py; Gateway/systemd/homecompetition-ota-updater.service; Gateway/tests/test_fleet_ota_updater.py.
- [x] RED: main.py runtime profile, all live DB backup, path traversal, signature/ABI failure, fsync journal crash phases.
- [x] Reuse verifier/extractor patterns from core_v1/release.py; no artifact-supplied shell.
- [x] GREEN: deterministic crash/recovery tests on host and Pi; actual Gateway source/runtime stage and import on Pi.
- [ ] Main system-service bootstrap, activation/rollback health checks on Pi (requires system administration).

### Task6 — Device bootstrap and local OTA HIL

**Files:** existing hc_core OTA/provisioning/runtime and SubBox/ActionBox main integration; private factory assets and evidence.
- [x] Build/bootstrap only after backups and enrollment mapping are verified.
- [x] Install public trust/enrollment using authorized local factory process, preserving existing names/calibration/credentials.
- [x] Flash only regions needed for the bootstrap with explicit target/offset and verified hash.
- [x] Signed local OTA through Gateway/SubBox/ActionBox; wrong-target/signature fail before activation.
- [x] Verify new boot/hash/version and local health; controlled rollback test; capture logs.
- [x] Verify NVS preservation, persistent counter, old-counter rejection and duplicate coordinator exclusion on the bench.
- [ ] Power-cut HIL only with a safe controllable power setup; do not substitute serial reset for power loss.

### Task7 — Customer/operator surfaces and fleet acceptance

**Files:** HomeCompetition OTA screens/client; protected operator UI; integration tests; deployment report.
- [ ] Policy windows/consent, waiting/install/reboot/rollback state and release notes.
- [ ] Pilot release via Internet, same home identity, then update each eligible component without USB transport.
- [ ] Test offline, revoked campaigns, schedule expiry, user/role isolation and recovery.
- [ ] Fresh review of full scoped change, fix important findings, rerun affected checks.

## Execution ledger

2026-10-27: user authorized deployment and full checks. Cloud administrator/project choice and current physical-load state requested asynchronously; neither is inferred from prior app login. Pi192.168.11.29 is currently reachable; smarthome-gateway.service active/main.py. USB present: SB0B54, ABDDF8, ABDDE8. Existing .bin files predate this OTA design, so do not flash them as if they implement the new cloud system.
