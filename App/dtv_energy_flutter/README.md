# SIC Home for Android

Flutter client for the Gateway in this repository. Includes account/API-key
login, room filters, favorites, relay control, telemetry/history, device pairing
and firmware management. Admin actions remain subject to Gateway authorization.
No simulated telemetry or local account registration is used.

## Connect

1. Connect the phone to the same trusted network as the Gateway.
2. Enter a reachable Gateway URL, normally `http://<gateway-ip>:8000`.
3. Sign in with an existing Gateway account or its API key.

The Pi at `192.168.11.29` was listening on **127.0.0.1:8000** when inspected on
2026-10-02. It is not yet reachable directly from a phone. Configure an
authenticated HTTPS reverse proxy, or deliberately enable LAN binding with
the Gateway's authentication and firewall intact. Do not expose port 8000 to
the public Internet. HTTP is supported for trusted LAN use, but does not encrypt
credentials in transit. Android session tokens are encrypted with AndroidKeyStore;
passwords are not saved and app backup is disabled.

Deploy the matching `Gateway/gateway/web_server.py` relay fix before testing
physical controls: the old handler misread the verifier's tuple result. The app
distinguishes a relay acknowledgement from verified electrical load. Offline
devices and unknown relay states cannot be toggled.

## Build And Verify

Use Flutter 3.44.8 / Dart 3.12.2, JDK 17 and Android SDK 36 (the versions verified
for this change):

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

APK: `build/app/outputs/flutter-apk/app-debug.apk`.
This is a development build, not a production-signed Play Store release.
The repository's existing Gradle release configuration also uses the debug key;
configure your own signing key before distribution.

Widget tests exercise 360/390 px phone and 800 px tablet layouts, light/dark mode,
large text and offline controls. Screenshot baselines are in `test/goldens/`.
HTTP tests mock Gateway responses; no Android phone, AndroidKeyStore hardware,
real relay switching or firmware flashing was exercised by these tests.
