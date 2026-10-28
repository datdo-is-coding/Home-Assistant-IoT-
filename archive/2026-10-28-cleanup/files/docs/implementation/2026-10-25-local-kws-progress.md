# SDD ledger — plan: docs/superpowers/plans/2026-10-25-subbox-local-kws.md

Ruling: Continue in the existing dirty workspace without commits — the implementation already spans firmware, Gateway and app and the plan explicitly preserves uncommitted work; isolating only tracked HEAD would omit it. Risk: overlapping changes require scoped review.

Pre-flight: Task 1 utterance -> Task 2 control queue already connected. Task 2 snapshots -> Task 3 identity/remote uses shared global revision. Task 3 result -> Task 4 Gateway requires channel 1–3; discovered remote ACK channel 0. Task 3 MQTT -> deployment ACL did not authenticate publisher; replace with source/destination topics outside device-owned subtree.

Task 1: Existing implementation, verification pending this session.
Task 2: Existing implementation, verification pending this session.
Task 3: Remote ACK exact channel regression RED→GREEN. Source-bound command/ACK topics regression RED→GREEN; pair-specific ACL grants remain deployment-dependent.
Task 4: Existing implementation, five-client exercise and regressions pending.
Task 5: Fresh-context review dispatched per executing-plans; no deployment attempted.

Ruling: Hardware deployment remains pending until devices, backups and safe test loads can be verified; software builds/tests cannot supply hardware calibration evidence. Risk: realtime and recognition thresholds remain unverified.

## Final software verification

- Task 1: Audio discontinuity/overflow/END-loss tests RED→GREEN; 8-bit wrap remains valid, no START cannot emit commands. Model/MFCC + firmware suite 25/25 pass.
- Task 2: Existing app and config tests pass; new cold controller restores saved binding and actuates CH3 with broker unavailable (host peer double). Real cold-boot peer recovery remains hardware work.
- Task 3: Channel ACK, source-bound topics, late ACK/playback, actual WS follow-up envelope, remote age and full dedup-cache pressure RED→GREEN. MQTT topic-less continuation RED→GREEN. No unexpired replay evidence is evicted.
- Task 4: Stale result and shared speaker lock tests RED→GREEN. Five-client host exercise confirms independent speakers, bounded queue and 25 current records with null power.
- Task 5: Fresh reviewer reported six important gaps (audio truncation, follow-up envelope, remote age, stale results, playback locks, MQTT fragments); all fixed. Archive references clean. Gateway 41 modules / 360 test invocations pass with PYTHONPATH=Gateway, separate processes. Firmware 25 tests pass; latest focused KWS check also passes. Flutter 134 tests pass, analyze clean, debug APK built. Both ESP-IDF projects build.
- Environment: sandbox async worker shutdown hung, resolved by approved execution outside sandbox. Initial hc_* import errors resolved using required PYTHONPATH. No production workaround added for test-environment failures.
- Hardware: /dev/ttyUSB*, /dev/ttyACM*, /dev/serial/by-id absent. No firmware flashed, no NVS/reset operation, no load energized, no live broker ACL change.
- Plan/workspace retained: changes intentionally uncommitted per plan. No merge/push.

## Hardware pilot — 25–26/10/2026 (supersedes earlier no-hardware status)

- User confirmed no loads connected; explicitly approved DDF8 Arduino → ActionBox_V2 migration.
- Backed up Pi config/SQLite and both boards' overwritten regions. DDF8 backup covers original 8 MiB layout, not physical 16 MiB. SubBox active app0 + NVS saved.
- Flashed SubBox app-only and DDF8 boot/table/app/WakeNet; esptool hash verified. NVS/ownership retained. Pi service healthy; DDF8 telemetry current, all relay states OFF.
- Actual broker EMQX, old allow-all failed publisher spoof checks. Installed KWS deny/grant block before old rules; 13 live rule-evaluator checks pass. No cross-SubBox pair enabled.
- Revision-zero config falsely showed error; Gateway regression RED→GREEN (9 tests on Pi and host), deployed and confirmed empty sync.
- Task 1 hardware timing RED: 263–288 ms exceeds 250 ms. Ruling: optimize only KWS/MFCC source compilation with -O2, preserving model/math/stride — targeted flags avoid changing unrelated firmware behavior. Host parity6 and firmware25 pass. Hardware timing GREEN: 138–163 ms across33 windows/two sessions.
- Recognition remains failing: requested normal/slow “bật đèn phòng ngủ” yielded “tắt đèn”, no sequence/overflow errors. Keep bindings empty while diagnosing; speed is not recognition acceptance.
- PCM diagnosis found ~200 ms WakeNet tail included in command PCM/VAD; one session ended at1s during the requested pause and classified tail as “tắt”. Host and ESP probabilities agree within1e-6, excluding a target-specific inference discrepancy for these samples.
- ActionBox wake-tail skip40 chunks/300ms RED→GREEN; follow-up skips no samples. Full firmware25 pass, ActionBox build and app-only flash hash verified. New physical sample captures3.12s but still misclassifies; no threshold/gain overfit applied.
- Temporary USB PCM-dump firmware removed after diagnosis; restore final timing-only SubBox build. Private PCM retained outside Git. Recognition acceptance, offline cold boot, follow-up/TTS, multi-SubBox and actual loads remain pending.
- Fresh scoped reviewer: no actionable findings in wake-tail skip, follow-up behavior, 1.2s SubBox timeout, -O2 precedence, revision0 handling; 10 targeted tests passed. Known limitation: commands begun immediately after wake detection can lose their first300ms.
- Final production SubBox hash matches recorded 72840b6b…4030; dump code absent, esptool hash verified. At03:42(+07), Pi confirms both pilot devices online, owner_epoch7 retained, 57,606 telemetry records and KWS revision0/empty bindings/sync. Thirteen effective ACL checks still pass. Verification logs retained privately under device-backups/20261025-local-kws/verification-20261026.

## Model calibration extension — user approved 26/10

- User confirmed complete/clear captured phrase; authorized calibration/retraining of the same ten labels. New plan: docs/superpowers/plans/2026-10-26-kws-model-calibration.md.
- Current checkpoint baseline355 samples: PyTorch79.44%, scalar INT8 C++79.15%, label agreement99.72%, max probability difference0.02767. Same wrong live-window labels in both. True training feature-floor comparison does not recover phrase.
- Added separate candidate-only calibration/export tool using existing TinyKWS and firmware MFCC. Export parity and recording-content split guards RED→GREEN; silent-word guard also passes (3 training tests in dedicated CPU-Torch environment).
- Seven multi-word collection sessions cannot be safely labelled: user reported missing words and app audio preview did not render. Keep them out of training; collect explicit single-word sessions instead. Original live phrase remains an independent diagnostic/holdout, not training input.

### Continuation 26/10 morning

- Local annotation page submission supplied seven human labels in order bật/tắt/đèn/quạt/phòng/khách/ngủ; these are now confirmed training data. Additional repeated “bật” recording reserved for test; user supplied missing “bếp” training recording.
- Candidate-v1 trained privately; 62 selected train windows fit100%, separate repeated-bật windows100%, old355 accuracy79.15%. Full diagnostic phrase still only “phòng ngủ”; not promoted.
- Eight new one-word validation attempts: first bật/tắt transport-cancelled; remaining six have ordered complete recordings. Candidate-v1 replay misses đèn/quạt/khách. No failed transport audio accepted for training.
- Added isolated-word crop/position/gain augmentation on training only. Fixed evaluator to retain quiet validation sessions and score one strongest window per session; full-utterance replay remains required separately. Five calibration tests pass. Candidate-v2b running with six microphone validation sessions; four additional validation/negative recordings requested.
- At continuation Pi192.168.11.29 is unreachable; SubBox still receives ESP-NOW PCM. Do not present earlier live Pi health as current. Model on SubBox remains original with temporary PCM diagnostic firmware for collection; remove diagnostic build after collection.
- Candidate-v2b with training-only crop/gain/position augmentation: five of six valid one-word replays correct; khách empty. Original355 accuracy78.59%. Full phrase at250ms stride still “bật phòng ngủ”. At125ms host spike the diagnostic phrase is complete, but measured hardware138–163ms/window cannot meet125ms, so no cadence change applied.
- Candidate-v2b scalar export has99.44% label agreement but max probability difference0.04466 exceeds preselected0.04 check: export gate FAIL, not promoted. Firmware+calibration tests30/30 pass.
- Source restored to non-dump production LocalKws. Board still runs temporary original-model capture binary while awaiting four requested sessions (bật,tắt,silence,unknown); no candidate or bindings deployed. Private source copies saved to device-backups for reproducibility. Independent review of calibration tool could not run because reviewer hit account usage limit; self-checks/test evidence only for this new tool.

## User stops training — 26/10

- User instruction “tiếp tục, ko train nữa”: cancel pending training-negative request and do not run further training. No training/capture/web annotation process running at cleanup. Preserve candidate artifacts; none deployed.
- Four fresh checks complete: v2b correct bật/tắt, silence empty, unknown phrase falsely recognized as room words. Still fails acceptance.
- Verified all18 model weight/scale/bias arrays equal original; production source contains no PCM diagnostic dump. Rebuild and app-only restore underway; NVS/ownership untouched. Pi SSH reports No route to host.
- Production SubBox app-only restore complete, esptool hash verified; size0x121f80 SHA25695848bafde4eeb781d924b167d913baf220be3e0cd4081b201931445bf2c3445. No NVS/table/model writes. Build passed, diff-check clean.
- Post-boot USB check: LocalKws ready at250ms, Wi-Fi192.168.11.159, registry repopulated from heartbeat with DDF8 all3 channels online/OFF/0mA. Initial status before heartbeat was0 entries; later status confirms recovery. No capture process left running. Pi connection timeout remains.
