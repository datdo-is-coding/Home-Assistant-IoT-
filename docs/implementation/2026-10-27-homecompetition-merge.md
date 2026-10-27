# HomeCompetition — merge implementation

Scope confirmed: merge App/dtv_energy_flutter and Application/dtv_home_assistant;
leave App/iot_dashboard alone. Canonical folder App/HomeCompetition, Dart package
home_competition, display name HomeCompetition. No model training or device flash.

Plan:
1. Retain device/room/scenes/preferences UI; reuse existing Firebase project/Auth.
2. Replace default Gateway session/data transport with Firebase Auth + RTDB.
   No LAN URL login, polling HTTP, SSE, or fallback to port8000 in the default app.
3. Map RTDB devices/channels into existing repository; expose live energy report
   and connection alerts with empty/error/stale states, never demo readings.
4. Keep existing state-write protocol compatible with the Firebase simulator;
   explicitly label it as cloud state, not a verified physical relay ACK.
   Gateway-only commissioning/OTA/voice operations must not silently succeed.
5. Move merged legacy source into archive, update package/build references.
6. Test mapping, session isolation, denied writes, empty/error states, analyze and
   build Android. No live device control or Firebase rules deployment in tests.

Existing cloud source: home-companion-fed2e RTDB, devices/action_box_01.
Simulator currently publishes uptime in last_updated. Treat first uptime sample
as freshness unknown; subsequent timestamp changes establish observed activity.
Keep original auth Android applicationId to match existing Firebase registration.
Rollback: Git working diff and archived source; no cloud data migration/deletion.

## Completed 2026-10-27

- Canonical app App/HomeCompetition; shell home_competition_app.dart; Dart package
  home_competition; Android namespace com.homecompetition.app. IDE launch entries,
  package imports/tests, web/Linux titles and deployment instructions updated.
  Android applicationId retains existing Firebase registration, deliberately.
- Original dtv_home_assistant archived under archive/Application; verified90/90
  tracked files identical to HEAD. iOS platform source copied into canonical app.
- Firebase session + realtime devices replace default local URL/API-key/SSE flow.
  Reads stop on sign-out; generation checks discard old-session async results.
  Read denial clears raw/cache-visible readings even after freshness timer ticks.
- Legacy uptime timestamps require observed changes; missing states stay disabled,
  stale/offline readings are unavailable. Sparse channels retain correct indexes.
- Authenticated HTTPS RTDB writes avoid SDK offline command queuing. State saved
  on Firebase is explicitly not a physical relay/load acknowledgement.
- Report/connection-alert screen replaces sample report values; empty history is
  disclosed, not synthesized. Automation preferences are isolated by account.
- Gateway-only operations have an explicit unsupported-cloud result. Original
  Gateway implementation remains for regression/rollback, not default execution.

## Verification

- flutter analyze --no-pub: no issues.
- flutter test --no-pub:146 passed, including12 Firebase mapping/session/UI cases.
- flutter build apk --debug --no-pub: passed.
- git diff --check: passed.
- Named APK: App/HomeCompetition/build/app/outputs/flutter-apk/HomeCompetition.apk
- SHA256:5df56d4f09a0a0fa29c7f0fb650aeb43c7839c1ca9b7633dafb20c7b122318c4
- Android Firebase project/app/API configuration matches retained google-services.

Tests use mocked Firebase/HTTPS; no Firebase writes/rules deployment, no real
account sign-in, no relay actuation, no firmware changes. iOS/web runtime not
verified. Native Firebase initialization/Google signing fingerprints still need
on-device acceptance. Firebase firmware simulator data is not physical metering.
A future Gateway cloud bridge is separate work; this merge reuses the existing
Firebase data source and protocol rather than migrating the Pi firmware system.

## Firebase startup correction — 1.1.1+12

User reported initialization failure after installation. The shipped Android
`google-services.json` lacked `project_info.firebase_url`; Gradle therefore did
not generate `firebase_database_url`. Android's auto-created default Firebase
app had databaseURL=null, while Dart supplied an explicit RTDB URL. The installed
FlutterFire implementation compares those values and throws core/duplicate-app.
The original field comparison checked project/app/key but missed databaseURL.

Added the matching firebase_url to native configuration, retained the same app
identity, and bumped the install version to1.1.1+12. Startup failures now show
a sanitized plugin/error code instead of swallowing all diagnostic information.
Regression tests use the actual JSON and FlutterFire platform implementation:
the old configuration reproduces duplicate-app; the corrected configuration and
repeated initialization pass. No Firebase server settings or user data changed.

Correction verification: analyze clean;148 tests passed; debug build passed.
`aapt dump` verifies version1.1.1/code12 and the RTDB URL inside the APK resources.
Artifact: App/HomeCompetition/build/app/outputs/flutter-apk/HomeCompetition-1.1.1.apk
SHA256:46d8b1a688cf6f2d4369dcd98cad45c5f7abb895fa2fdc783dd8faf0a2c1e9c3
No Android device was attached to adb; native startup on the user's phone and
real account login remain unverified. Install this update over the old app.

## On-device Google sign-in diagnosis — 2026-10-27

USB Android model23116PN5BC connected. Verified installed1.1.1/code12; updated
in place to diagnostic1.1.2/code13 with adb install -r (Success), retaining data.
Analyze clean;14 focused Firebase tests passed; debug APK built successfully.
Diagnostics log only provider/error code, never email/password/token.
After user reproduced Google sign-in on1.1.2, app-process log:
`[AUTH] provider=google platform=sign_in_failed api=10`.
This is the current observed Google configuration error, distinct from the
previously reported operation-not-allowed message (provider not yet identified).

APK signing certificate SHA1:
69:52:90:33:FA:F8:FF:A5:9B:BD:BE:53:37:EF:85:11:6A:14:9A:E5
Bundled Android OAuth config certificate SHA1:
C5:9B:C0:D3:9F:51:48:19:1E:D5:34:E2:7B:EC:CB:D5:BA:3A:05:34
Firebase project home-companion-fed2e, registered Android package
com.dtv.homeassistant.dtv_home_assistant. Add the installed signing SHA1 in
Project settings > Your apps > Android > SHA certificate fingerprints. Retain
existing fingerprints for other builds. Verify Google provider enabled in Auth.
Download refreshed google-services.json if OAuth configuration changes.

Firebase CLI/admin credentials unavailable; browser control disabled. No live
cloud configuration altered. Successful Google authentication remains pending
server-side registration and a fresh on-device attempt.

## Signed-in Overlay correction — 1.1.3+14

User confirmed Google login now works, then reported "No Overlay" in the UI.
A regression test using the Firebase-mode signed-in app reproduced:
`No Overlay widget found` in RawTooltip for the report IconButton. The global
status row had been placed in MaterialApp.router.builder, above the Navigator
which supplies the Overlay. Existing app tests used Gateway mode and omitted it.

Moved the same row into SmartHomeScaffold under the route Navigator. Retained
status/retry/report controls; removed the root builder wrapper. The regression
now builds the cloud shell, long-presses the tooltip and opens the energy report
without framework exceptions (RED before change, GREEN after). No auth/cloud
configuration or device data changed. Bumped version1.1.3/code14.

Verification: analyze clean;149 tests passed; debug APK build passed. Installed
1.1.3 in place on connected phone (adb Success) and started MainActivity.
New process is running; its captured startup log contains zero Flutter error
lines, no No Overlay and no framework exception. Actual visual acceptance by
user and full report/relay actions on live data remain unverified.
Artifact: App/HomeCompetition/build/app/outputs/flutter-apk/HomeCompetition-1.1.3.apk
