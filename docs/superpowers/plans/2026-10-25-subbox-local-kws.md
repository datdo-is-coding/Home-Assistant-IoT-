# SubBox local KWS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Run the existing Vietnamese KWS on SubBox, execute through ActionBox_V2, and use Pi only for structured responses and measurement analysis.
**Architecture:** Keep WakeNet/PCM on ActionBox, infer/resolve/dispatch on SubBox. Keep authenticated MQTT and downstream TTS WebSocket. Archive replaced code only after tracing references.
**Tech Stack:** ESP-IDF C++, existing INT8 model/MFCC, FreeRTOS, Python asyncio, Flutter.
**Spec:** docs/superpowers/specs/2026-10-25-subbox-local-kws-design.md

## Global Constraints
- ActionBox_V2 owns all three relay channels, pins, pulse generation and safety.
- Existing KWS vocabulary only; no free-form ASR or command inference on Pi.
- Preserve enrollment, reset, manual app commands, measurement and uncommitted work.
- No successful actuation claim without matching ACK; unknown measurements remain unknown.
- Archive replaced files with original paths/reasons; never move code still used by active callers.
- User approved implementation 2026-10-25. Execute inline without another approval gate.

## Review Focus
- Overlapping windows and end-of-sentence room words must not cause premature or duplicate relay operation (Task 1).
- Restart with Pi unavailable must preserve local bindings and trusted peers (Task 2).
- Fragmented config, stale ownership and delayed remote commands must not actuate (Task 2/3).
- A slow/disconnected speaker must not block another SubBox or telemetry (Task 4).
- Archived files must not remain in active build/test imports; current-only readings must not become fake kWh (Task 5).

### Task 1: Local recognition and safe sentence assembly
**Files:** SubBox/src/audio/kws/{local_kws.h,local_kws.cpp,kws_command.h}; reuse model/MFCC in common/kws; SubBox/src/audio/audio_manager/audio_manager.cpp; main.cpp; task_manager.cpp; Firmware/tests/test_local_kws.py.
**Interfaces:** LocalKws implements ASREngine. KwsCommand::add(int,float), finish() return strict canonical text or incomplete/error status. Recognition only within start/stop; result emitted once via existing utterance callback.
- [x] Write host tests for vocabulary, room suffix, conflicting action/device, silence, duplicate windows and incomplete clauses; run and observe failure.
- [x] Extract reusable model/MFCC without ActionBox transport coupling; bounded input window and KWS work outside receive callback.
- [x] Connect final result to existing command queue and wire a separate WsASR connection for downstream playback only; never feed it microphone PCM.
- [x] Run host tests and SubBox build.
- [x] Measure inference timing before hardware actuation deployment: initial 263–288 ms failed; per-source -O2 measured 138–163 ms across two voice sessions. Recognition accuracy still fails; no actuation binding enabled.
- [ ] Pass representative real microphone utterances/noise before enabling bindings. Pilot currently misclassifies “bật đèn phòng ngủ” as “tắt đèn”; host replay matches hardware, so recognition acceptance remains open.

### Task 2: Explicit voice bindings and ActionBox_V2 execution
**Files:** SubBox registry/router/task_manager, storage; Gateway/gateway/kws_service.py, web_server.py; Flutter ActionBox detail/repository/client; corresponding tests.
**Interfaces:** Configuration envelope cmd=KWS_CONFIG, revision, sources[{node_id,room}], bindings[{room,device,node_id,subbox_id,channel,hardware_uid,config_version}]. Enumerations use existing RoomType/DeviceType string values; no inferred channel role. Config ACK carries revision.
- [x] Test missing/duplicate binding, exact channel 1–3, unknown/changed identity, unavailable target and persisted config reload before implementation.
- [x] Store/apply bounded validated snapshots on SubBox; remove CH1=light/CH2=fan fallback; resolve through explicit binding to authoritative ActionBox identities.
- [x] Provide authenticated config API and app controls using registered channel pickers, show pending/applied state; no automatic assignment.
- [x] Run firmware/Gateway/Flutter relevant tests and builds.

### Task 3: Multi-SubBox delivery, bounded sessions and result events
**Files:** SubBox MQTT/router/task_manager and protocol tests; Gateway broker provisioning config where present.
**Interfaces:** Event home/subbox/<origin>/event/kws_result; JSON schema_version=1, session_id, request_id, origin_node, target_node, target_subbox, channel, action, status, reason, state, follow_up. Direct remote request topics include authenticated publisher source and destination, never infer publisher from JSON alone.
- [x] Test replay, wrong ACK, target ownership, expired remote request and queue overflow.
- [x] Add source-bound remote command/ACK transport with expiry and dedup; local execution must not require Pi/broker.
- [x] Preserve one bounded follow-up for incomplete supported words, no repeated question loop; target same source only after playback ends.
- [x] Run transport/command tests and reconnect tests; document any physical multi-radio coverage unavailable.

### Task 4: Pi structured responses and current-data history
**Files:** Gateway/gateway/kws_service.py, main.py, audio_server.py, registry_manager.py; Gateway/tests/test_local_kws_gateway.py.
**Interfaces:** KwsService handles validated config/result events; no process_voice_command call. Per-speaker output locks; bounded synthesis queue. Existing telemetry payload retains validity and per-channel timestamp.
- [x] Tests assert no ASR/NLU/command redispatch on result; dedup/wrong source/stale result rejected; two speaker outputs independent.
- [x] Disable Pi microphone recognition initialization/path, preserve authenticated downstream TTS, explicit registered speaker selection and structured follow-up.
- [x] Reuse existing telemetry storage with per-channel current/quality, preserve null W/Wh; show historical current without invented power.
- [x] Run Gateway regression suite and bounded five-client result/telemetry exercise.

### Task 5: Archive, integration and delivery
**Files:** archive/local-kws-migration/README.md and replaced originals; active references/build/test docs; docs/implementation/2026-10-25-local-kws.md.
- [x] Trace imports/CMake/training references before moving each obsolete file; preserve original directory paths in archive.
- [x] Update active references and tests; leave shared functional code in place with recorded reason.
- [x] Run firmware host tests, IDF builds, Gateway tests, Flutter tests/build sequentially; inspect every failure.
- [x] Fresh reviewer checks implementation against spec, including failure classes above; fix important findings and rerun affected tests.
- [x] Back up live config/binaries and verify hardware topology before deployment; deploy verified SubBox/Pi builds and user-approved DDF8 migration to ActionBox_V2. Preserve NVS; no erase-flash or load actuation.
- [x] Record deployment evidence and remaining hardware checks. Keep changes uncommitted until integration is reviewed; do not include unrelated pre-existing changes in a bulk commit.

## Verification update — 25/10/2026

Software steps verified in the current workspace. Firmware host: 25 passing tests,
plus focused KWS control checks after offline-restore coverage. Gateway: 41 test
modules / 360 test invocations, all passing with `PYTHONPATH=Gateway` (separate
process per module); standalone intent diagnostic is not a unittest module. Flutter:
134 tests, analyze and debug APK build pass. SubBox and ActionBox_V2 ESP-IDF builds pass.
Fresh-context review findings fixed with RED→GREEN regression coverage; see
`docs/implementation/2026-10-25-local-kws-progress.md`.

The five-client exercise uses real Gateway scheduling/playback + SQLite with fake
sockets and synthesized PCM. Pilot backup/flash, inference timing and EMQX ACL checks are now recorded in the
implementation report. Recognition calibration, radio concurrency, cross-SubBox
pair grants, cold boot without Pi and relay load checks remain pending. A checked software step does not claim hardware verification.
