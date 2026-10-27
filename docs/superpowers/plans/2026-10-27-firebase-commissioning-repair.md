# Restore Firebase device commissioning

> Execute in the existing dirty checkout; the user explicitly requested restoring the old working logic without more design questions. Do not reset, rename or replace unrelated work.

**Goal:** Restore Add Device using the existing legacy Gateway lifecycle over authenticated Firebase transport, keeping the Firebase app's data source and the existing physical claim/ACK checks.

**Architecture:** The existing `AddDeviceFlowScreen` calls the same `GatewayClient` methods. `FirebaseHomeClient` transports an allowlisted subset through per-user RTDB request/response records. One optional worker inside the existing `SmartHomeGateway` invokes its existing lifecycle on the same event loop; there is no second control Gateway or generic HTTP proxy.

## Work and acceptance

- [x] Restore the app route and implement authenticated HTTPS mailbox requests; show discovery failures and retain logical claim idempotency. Never derive the SubBox broker from the Firebase hostname.
- [x] Reuse `get_candidates`, `start_claim`, `start_operation(identify)` and `get_operation`; reject unauthorized UID, expired/replayed/modified requests and dangerous API paths before side effects. A queued request is not successful commissioning.
- [x] Add a disabled-by-default worker to the main Gateway, with private configuration, explicit installer UID grants, trusted broker metadata, safe registered-device projection and persisted responses.
- [x] Supply strict Rules and fail-closed preflight, verified with the official emulator. Preserve existing device data and take a Rules backup before deployment.
- [x] Verify app regressions (162), full Gateway suite including emulator (442), and build APK1.2.1.
- [ ] Back up and merge live Rules, configure the real installer UID/credentials and activate the worker; the user cannot reconnect the Pi/phone yet. Confirm live pairing separately from host/emulator checks.

## Limits that must remain explicit

This repair reuses legacy commissioning. It does not silently migrate Core-only OTA pilot devices into the legacy registry or claim app/voice/relay acceptance. It does not enable billing, train models, write relay commands, remove devices, burn eFuses or flash DDF4 without a verified backup. No local-port fallback or fabricated Firebase device is an acceptable substitute.

## Deployment checks

Before activation: back up the current Gateway sources/config/database and live RTDB Rules, identify the actual Firebase account UID and Gateway identity, verify the protected Rules, and configure credentials privately on the Pi. Install the APK over the current app without clearing its data. Confirm a physical device's registration ACK and its appearance in Firebase/app separately from unit/build results.
