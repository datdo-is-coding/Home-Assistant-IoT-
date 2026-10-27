# HomeCompetition1.2.1 — restore Add device through Firebase

## Problem and resulting code

The Firebase merge routed `/actionbox/add-device` to `_gatewayFeature`, which
returned a missing-service message instead of the existing wizard. Merely
removing that guard would still leave every lifecycle request unsupported by
`FirebaseHomeClient`, and would send the Firebase hostname as the SubBox broker.

The original wizard now opens for Firebase accounts. Candidate discovery,
identify, claim and operation polling use authenticated HTTPS RTDB mailbox
records. No IP/port login or local HTTP fallback is introduced. Discovery errors
are visible and retryable. Broker settings come from the assigned Gateway's
trusted status, never from the Firebase database hostname.

The optional worker runs inside the existing legacy `SmartHomeGateway`. It
calls that process's existing `DeviceLifecycleManager` on the same MQTT event
loop. Physical discovery/proof, room/SubBox capacity, revision/route checks and
the original device-apply acknowledgement remain in force. A stored Firebase
request or accepted claim never becomes a successful device registration by
itself. Registered entries are projected only after the original lifecycle
creates them; setup proofs and credentials are excluded.

Explicit installer UIDs in a private Gateway config are mapped to its local
admin authority. The browser/app cannot self-assign that authority. The worker
requires the exact protected Rules before initialization and each request
batch, rejects expired/oversized/forged requests, persists responses before
removing requests, and uses the lifecycle's durable logical idempotency key
across transport retries. Reset/remove/OTA/relay endpoints are not exposed by
this commissioning transport. The worker is disabled by default, so existing
Gateway deployments do not need new credentials to keep running.

## Verification completed

- `flutter analyze --no-pub`: no issues.
- `flutter test --no-pub --concurrency=1 --reporter expanded`:162 passed.
- Gateway full suite with the RTDB emulator enabled:442 passed.
- Official Firebase RTDB emulator4.11.2: real Rules compiled; own-UID access,
  unauthorized UID/response/status/access forgery, immutable requests, deadline
  validation, empty-object normalization, and request→simulated device ACK→
  registry→Firebase projection passed. This is an actual local RTDB process;
  radio input is simulated and is not physical commissioning acceptance.
- APK debug build: passed. Package remains
  `com.dtv.homeassistant.dtv_home_assistant`; version1.2.1/code16. Signing SHA1
  remains `69:52:90:33:FA:F8:FF:A5:9B:BD:BE:53:37:EF:85:11:6A:14:9A:E5`.
- `git diff --check`, Python compilation and APK signature verification passed.

APK: `App/HomeCompetition/build/app/outputs/flutter-apk/HomeCompetition-1.2.1.apk`

SHA256: `91adb26deabe19d28628349041f8371f271aa10cf1413234b68ab703d28de5ca`.

The initial parallel Flutter run had an intermittent voice-alias test failure.
The isolated rerun and two full sequential runs passed. The first Gateway
integration run found four missing-optional-attribute errors in legacy test
fixtures; startup now handles the optional worker with `getattr`, and the full
rerun passed. No failing check is treated as acceptance.

## Deployment and physical acceptance pending

The user confirmed the Pi/phone cannot be reconnected at present. The workstation
is on10.74.236.x, the previous Pi address192.168.11.29 times out, no matching Pi
peer was found on Tailscale, and ADB has no phone attached. Browser control became
disabled in Work settings before the live Rules could be exported. No Gateway
restart, real Firebase write/Rules deployment, phone installation or relay action
was performed in this repair. The Console displayed a public-Rules warning; the
actual full Rules document must be backed up and reviewed before activation.
No Firebase Admin credential/installer UID was invented or copied into the APK.

Resume with `Gateway/firebase/README.md`: back up current deployment, merge the
protected namespaces preserving existing device data, provision credentials and
the real installer UID privately, run the non-mutating preflight, enable the
worker in the existing Gateway service and install the APK without clearing
phone data. Then verify a compatible Box's physical setup, identify, claim,
matching device ACK, terminal success and appearance in Firebase/app.

Core-only OTA pilot devices still require their explicit legacy registry/control
adapter; this repair does not claim their radio/app/voice controls work. DDF4
remains unflashed because its full backup was interrupted by USB loss. Model
training stays stopped. These changes preserve unrelated dirty app/OTA work.
