# Gateway commissioning through Firebase

`commissioning.rules.json` is a **merge fragment**, not a replacement Rules
document. It contains only the root deny defaults and these commissioning
namespaces. Do not apply it as the entire database Rules document: doing so would
remove the existing `/devices` Rules. The separate
`Gateway/cloud_ota/rtdb.rules.json` belongs to the dedicated OTA database and must
remain unchanged.

Back up and inspect the live Rules first. Preserve existing literal namespaces
such as `devices` while merging the three protected subtrees. The root `.read`
and `.write` must be absent or constant `false`, and root wildcards are refused.
A root permission cannot be revoked by a denial below it; do not enable the RPC
runner until the merged, deployed full document passes
`gateway.commissioning_rules.validate_commissioning_rules(document)`.
The helper returns `None` on success and raises `ValueError` otherwise. It uses
a pinned digest of canonical JSON to check every descendant Rule exactly; any
intentional fragment change requires review and an updated digest.

- `/gateway_access/<uid>/<gateway_id> = true` is written by trusted Admin
  credentials. A signed-in user can list only their own access map and cannot
  grant themselves access. A false or missing value denies access.
- `/gateways/<gateway_id>/status` is written by trusted Admin credentials with
  `online`, `last_seen`, `mqtt_host`, and `mqtt_port`. Only an authorized UID can
  read it.
- `/gateway_rpc/<gateway_id>/requests/<uid>/<request_id>` permits an authorized
  UID to create its own immutable request. Clients cannot read, modify, delete,
  or recreate an existing request. The request ID must match its key. The
  envelope has `request_id`, `method`, `path`, `created_at`, and `expires_at`,
  and may include `body`. Unknown envelope fields are rejected.
- `body` remains a JSON object. Empty `{}` disappears in RTDB, so it is optional
  and the runner defaults it to `{}`. Rules require children when it is present;
  the runner must separately reject arrays and other non-object bodies and cap
  the encoded request/body size at 16,384 bytes before dispatch.
- Request timestamps are Unix milliseconds. Expiry must follow creation by at
  most 30,000 ms, creation cannot be more than 5,000 ms in the future, and expiry
  cannot be more than 5,000 ms in the past. The runner enforces the same limits
  before invoking an allowlisted local endpoint.
- `/gateway_rpc/<gateway_id>/responses/<uid>/<request_id>` is server-written.
  Only that UID with gateway access can read its responses. No client can write
  status, responses, or access grants; there are no request/response ancestor
  read grants.

Admin SDK credentials bypass client Rules, so the runner must validate inputs,
authorization, timestamp bounds, and its path/method allowlist itself. This
fragment must be merged and checked in each deployment. The namespace authorization and request/response
flow have also been verified with the official RTDB emulator, separately from
the Python preflight checks. Physical device commissioning still requires HIL.

## Enable the existing Gateway worker

The transport is part of the existing `gateway/main.py` process, using that
process's lifecycle, registry and MQTT loop. Do not launch a second Gateway.
It is disabled unless `HOME_COMPETITION_FIREBASE_CONFIG` is set. The optional
dependency is pinned in `requirements.txt` in this directory.

1. Back up the running Gateway code/config/DB and live RTDB Rules. Merge the
   fragment into the full Rules document; preserve existing device data and its
   branch Rules. If the live database has public root grants, those must first
   be removed or narrowed to the existing legacy branches. Do not publish the
   fragment alone or automatically open new branches.
2. Copy `commissioning-config.example.json` to a private location owned by the
   Gateway service account and set mode600. Set its real `gateway_id`, MQTT
   host/port and the Firebase Auth UIDs permitted to install devices. This is
   explicit local owner/installer authorization; registering a Google account
   does not grant it. Do not put setup proofs or passwords in this config.
3. Use existing ADC, or add a `credential_file` path to a separately provisioned
   private Admin SDK credential. Never put that credential in the app/repo or
   copy the workstation release-signing key. The service needs RTDB Admin I/O
   and read access to the deployed Rules for fail-closed preflight. SDK
   installation alone does not create or authorize credentials.
4. With the Gateway Python environment, run the non-mutating check:

   ```sh
   PYTHONPATH=Gateway/gateway python -m firebase_commissioning --config /private/firebase-commissioning.json
   ```

   The check reads the deployed Rules using the configured credentials; it
   does not send any device operation. Configure the service environment using
   `firebase-commissioning.conf.example`, then restart the existing Gateway
   when reachable. That worker grants only the configured installer UIDs to
   its ID, publishes a heartbeat/broker metadata, and consumes allowlisted
   requests. It must not be enabled against public root Rules.
5. Install HomeCompetition1.2.3 over the existing app, preserving its identity
   and login data. Open Add device, put the actual compatible Box into its
   physical setup mode, scan/identify it, choose room/channels and confirm.
   A claim accepted by Gateway remains pending until the original device ACK.
   Verify both the terminal operation and the new live registry/Firebase entry.

Requests are removed after their response is persisted. Responses expire after
five minutes. Lost response writes retry with the lifecycle's durable logical
idempotency key; stale mailbox requests cannot start commissioning later.
The worker projects only whitelisted registered metadata/current readings and
never creates sample devices or exports pending proofs. It does not read cloud
state writes to turn relays on, and does not add maintenance/OTA/reset APIs.
Missing reported state/measurements remain unavailable.

Without a `core` config section this uses **legacy** commissioning. With `core`
configured, `/api/commissioning/context` selects the existing Core Security1
workflow in the app. The worker opens the existing Core registry with recovery
disabled; the running radio coordinator remains the sole radio bridge. Claims
remain pending until independently authenticated device and parent receipts
arrive. Registered Core nodes publish inventory and availability; relay control
and binding management are separate from this commissioning transport.

The private `core` section requires `data_dir` (the existing `core.db` and
`master.key` directory), `home_id`, actual radio `channel`, TLS `mqtt_uri`,
65-byte uncompressed P-256 `ota_pubkey` as hex, and `parents`. Each parent key is
its decimal Core node ID and contains its actual `sta_mac` and current persisted
`generation`. Read these from the enrolled hardware; do not invent identities,
keys or generation counters. The worker preserves the greater stored generation
and does not reset coordinator sessions. Configured Firebase installers receive
only Installer membership in the configured Core home.

Core provisioning stores each SubBox's radio PMK encrypted in
`commissioning_radio_keys`; its ActionBoxes must share that PMK and have their
own LMKs. A SubBox enrolled through this API creates its record automatically.
An existing USB-enrolled SubBox needs an explicit import from its trusted
manufacturing record, checked against physical NVS first. Do not add the PMK to
the app context or `parents` config. A missing key is rejected with
`parent_radio_key_missing`; a conflicting import is rejected rather than
silently rotating an active network key.

Run `flutter pub get` after a fresh checkout or branch switch before building
the app. The ignored Android plugin registrant must be generated before using
`flutter build ... --no-pub`; otherwise native Firebase initialization can fail
even when Dart tests pass.

Do not relabel a successful unit/emulator test as radio acceptance. Remove a UID from the
private config and its `gateway_access/<uid>/<gateway_id>` grant when revoking
an installer. To roll back the code, remove the service environment override
and restore the previous source; do not erase device NVS or registry data.

## Repeat the emulator verification

Start the official RTDB emulator on loopback port19000, then:

```sh
HC_TEST_RTDB_EMULATOR=127.0.0.1:19000 python -m unittest discover -s Gateway/tests -p test_firebase_commissioning_emulator.py -v
```

This test refuses every other host/port, uses only namespace
`demo-homecompetition`, and clears that isolated namespace between cases. It
checks real Rules compilation, own-UID access, forged response/access/status
denials, request immutability/expiry/unknown fields, RTDB normalization of empty
objects and the claim→device-ACK→inventory path with simulated radio input.
It also checks the Core context and pending claim through the same protected
mailbox, including empty arrays disappearing in RTDB.

Firebase references: [Rules inheritance](https://firebase.google.com/docs/database/security),
[conditions and validation](https://firebase.google.com/docs/database/security/rules-conditions),
and [Rules API](https://firebase.google.com/docs/reference/security/database).
