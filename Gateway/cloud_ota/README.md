# Fleet OTA service

This directory packages the independent aiohttp API. It does not replace
`gateway/main.py`, provision a board, or enable a campaign by itself.

## Deployment prerequisites

Target project: `home-companion-fed2e`, only after an authorized project
administrator enables billing and the required APIs. A Firebase app login or an
Editor role alone is not evidence of permission to attach billing or grant IAM.
No deployment was performed by this package's author.

Use a **dedicated OTA Realtime Database instance** and apply `rtdb.rules.json` at
its root. Every client read/write is denied; customer and Gateway operations use
the authenticated API. Admin SDK bypasses Rules, so all API paths enforce their
own authorization. Do not replace the existing application's database Rules with
this file. A deny at `/commercial_ota` cannot override an allow on an ancestor in
an existing shared database.

Runtime identity should be a dedicated service account. Grant only:

| Resource | Required permission / suitable predefined role |
| --- | --- |
| Firebase Auth users | `firebaseauth.users.get` for revoked-token checks; `roles/firebaseauth.viewer` is the read-only predefined role |
| OTA RTDB | `firebasedatabase.instances.get` and `firebasedatabase.instances.update`; `roles/firebasedatabase.admin` is broader and should be limited to the OTA instance where IAM supports that scope |
| Artifact bucket | `storage.objects.get`; bucket-scoped `roles/storage.objectViewer` is a broader predefined alternative |
| Grant signing secret | `roles/secretmanager.secretAccessor` on the one secret |
| Signed URL service account | `iam.serviceAccounts.signBlob`; `roles/iam.serviceAccountTokenCreator` on the exact signing account is a broader alternative |

If the runtime account signs URLs as itself, it still needs `signBlob` on itself.
Neither the container nor Gateway receives a service-account JSON private key.
The grant P-256 private key is a separate Secret Manager secret mounted read-only;
its public key must be provisioned/pinned in Gateway configuration through the
trusted factory/administrator process. `/v1/grant-key` is diagnostic discovery,
not a trust bootstrap. Keep release-signing keys separate from the online grant
key. This pilot supports one active grant key; trusted current/next key rotation
needs a separate signed trust rollout before changing this key.

A bootstrap administrator needs permissions to enable APIs, create the dedicated
RTDB instance/bucket/Secret Manager secret/runtime service account, and grant the
resource permissions above. A deployer needs Cloud Run deployment permissions
(e.g. `roles/run.admin`), `roles/iam.serviceAccountUser` on the runtime account,
Artifact Registry writer access on the image repository, and Cloud Build
permissions only if using remote builds. Do not give these deployment or IAM
administration roles to the runtime service account. Firebase custom-claim
administration is also a separate authorized administrative action; the service
only reads claims.

Primary references: [Firebase product roles](https://firebase.google.com/docs/projects/iam/roles-predefined-product),
[IAM signBlob](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures),
[Python signed URLs](https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob#google_cloud_storage_blob_Blob_generate_signed_url).

## Build and run

From the repository root:

```sh
docker build -f Gateway/cloud_ota/Dockerfile -t homecompetition-ota:pilot .
```

Deploy the built image by its registry **digest** after the account/project gates
above are satisfied. Initial Cloud Run settings: minimum instances 0, maximum
instances 1, concurrency 8, 1 CPU, 512 MiB, request timeout 60s. Enable budget
alerts and review request/storage/egress quotas; alerts and maximum instance
count are not a hard spending cap. Do not assume Spark supplies Cloud Run or
artifact-storage billing.

Required environment:

```text
GOOGLE_CLOUD_PROJECT=home-companion-fed2e
FIREBASE_DATABASE_URL=https://<dedicated-instance>.<region>.firebasedatabase.app
OTA_GRANT_KEY_FILE=/run/secrets/ota-grant.pem
OTA_GRANT_KEY_ID=pilot-grant-1
OTA_ARTIFACT_BUCKET=<private-ota-bucket>
OTA_SIGNING_SERVICE_ACCOUNT=<signed-url-account>@home-companion-fed2e.iam.gserviceaccount.com
PORT=8080
```

`OTA_GRANT_KEY_FILE` contains an externally generated unencrypted P-256 PEM
private key supplied by the read-only secret mount, never a file copied into the
image or repo. ADC uses the attached Cloud Run account. Missing configuration,
Firebase credentials, or a signing key fails startup; no anonymous/test fallback
is selected. The service must be reachable over HTTPS without Cloud Run IAM
identity checks, because it verifies Firebase ID tokens and device tokens itself.
Only `/healthz`, `/v1/grant-key`, and device challenge/token exchange are public;
exchange requires proof of possession of an enrolled key. Keep any public
invoker binding limited to this API service.

The service writes only `/commercial_ota` in the configured OTA database. All
mutations use RTDB compare/retry transactions. A transaction spans this pilot
namespace to atomically fence ownership, campaigns, policy, leases, and grants.
This favors correctness at small pilot scale: reads/transactions still load the
namespace on the server. Before broad fleet rollout, shard homes with an explicit
campaign-revocation fence and retention/archival jobs; simply splitting these
transactions would introduce a policy/revocation race. Do not use Cloud Run local
SQLite for production state.

## Artifact preparation

Upload a previously signed artifact to private Cloud Storage at
`sha256/<lowercase digest>` using create-only generation preconditions, with
custom object metadata `sha256=<digest>`. The uploader should have object-create
permission, not overwrite/delete permission. Retain referenced generations and
stable/recovery artifacts (at least 90 days and two stable releases per class).
Record the returned object generation as a decimal string. The API stores
immutable metadata and checks generation, size, and the digest metadata before
issuing a 900-second generation-pinned GET URL. The Gateway still checks the
actual bytes, signature, size, compatibility, freshness, counter, and local
preflight; bucket metadata and HTTPS do not replace those checks.

`POST /v1/artifacts` requires all these fields:

```json
{
  "artifact_id": "subbox-v2",
  "sha256": "<64 lowercase hex>",
  "size": 1024,
  "compatibility_id": "<64 lowercase hex>",
  "version": "2.0.0",
  "storage_key": "sha256/<same digest>",
  "storage_generation": "123456789",
  "signing_key_id": "release-1",
  "signed_target": "<exact 176-byte target-v2 packet as 352 hex characters>"
}
```

For Gateway runtime archives replace `signed_target` with `signed_manifest`, a
bounded signed-envelope object containing a nonempty `signature`. The service
requires signed metadata but treats it as opaque vendor input in this pilot;
release-key cryptographic verification is performed independently by the pinned
Gateway/Box verifiers. Exactly one metadata form is allowed. Reposting identical
artifact data is idempotent; changed data under the same ID returns 409. There is
no API to overwrite or delete an artifact/release definition.

## Authentication and API

Send `Authorization: Bearer <token>` to protected paths. Human tokens are Firebase
ID tokens verified with revoked-token checking. Only server-managed custom claim
`ota_roles: ["vendor_release_operator", "vendor_release_approver"]` grants vendor
rights. Ordinary signup creates neither role. Pilot may assign both roles to one
approved person, but staging and approval remain separate audited operations.
Home membership is stored by the service, not supplied by a client/token claim.
IDs use `[A-Za-z0-9_-]{1,100}`; Firebase owner UIDs are stored as hashed membership
keys. JSON unknown fields are rejected.

| Method/path | Caller and body |
| --- | --- |
| `POST /v1/homes/{home}/enrollment` | Operator: `tenant_id`, `gateway_id`, `owner_uid`, P-256 `public_key_pem`. Authorized factory/home assignment, never public signup |
| `POST /v1/artifacts` | Operator: immutable artifact record above |
| `POST /v1/releases` | Operator: `release_id`, `artifacts` ID array, `dependencies` map artifact ID to prerequisite ID array, optional `notes`; DAG validated |
| `POST /v1/releases/{release}/approve` | Approver: nonempty `reason` |
| `POST /v1/campaigns` | Operator: `campaign_id`, approved `release_id`, stable `seed`, integer `percentage` 1..100 |
| `POST /v1/campaigns/{campaign}/state` | Operator: `state` ACTIVE/PAUSED/CANCELLED, nonempty `reason`; cancelled campaign cannot resume |
| `GET /v1/homes/{home}/updates` | Member/owner/operator or matching Gateway: own policy, jobs, releases and campaign states |
| `GET /v1/homes/{home}/policy` | Same read authorization |
| `PUT /v1/homes/{home}/policy` | Home owner only: previous `revision`, `consent` bool, IANA `timezone`, `start_minute`/`end_minute` 0..1439, `days` Monday0..Sunday6, `excluded_targets`, optional UTC `hold_until` |
| `PUT /v1/homes/{home}/inventory` | Matching Gateway: `targets` array of `target_id`, `compatibility_id`, `boot_id`, `sha256`, optional `version` |
| `GET /v1/homes/{home}/desired` | Matching Gateway: creates stable home-cohort assignments and returns `jobs`, referenced `artifacts`, `policy`, `campaigns` |
| `POST /v1/homes/{home}/lease` | Matching Gateway: stable process `worker_id`; returns `fence`, `expires_at`, `worker_id` |
| `GET /v1/homes/{home}/artifacts/{artifact}/download` | Matching Gateway with an assigned artifact: returns `url`, `expires_in`900, `sha256`, `size`, `storage_generation` |
| `POST /v1/homes/{home}/jobs/{job}/grants` | Matching Gateway: `worker_id`, `lease_fence`, job `generation`, `target_id`, current `policy_revision` |
| `POST /v1/homes/{home}/grants/{nonce}/consume` | Matching Gateway: `worker_id`, `lease_fence`, job `generation`; atomically consumes once and records INSTALLING |
| `POST /v1/homes/{home}/jobs/{job}/reports` | Matching Gateway: same binding plus `target_id`, `state`, optional `boot_id`, `sha256`, `version`, bool `health`, bounded `reason` |

A policy write compares/increments revision; new homes have consent false.
Equal start/end minutes means the explicitly consented whole selected day;
overnight windows attribute the early-morning portion to the previous selected
day. Excluded/held/off-window targets cannot get a grant. Downloads may occur
outside the maintenance window.

Enrollment with an identical binding is idempotent. Changing owner, home
Gateway, or device key increases the ownership epoch, resets consent/inventory/
lease/grants, revokes the old Gateway identity and cancels unstarted jobs. An
already-started old-owner job remains blocked for operator reconciliation; a
transfer must not silently claim an in-flight physical operation stopped.

Release assignments use a stable SHA-256 home/Gateway/seed cohort. Missing bundle
dependencies and ambiguous compatibility block assignment. Each prerequisite
must be confirmed before the dependent target starts. A home has one active
lease and one installing/validating/report-pending target. Lease lasts 120s;
renew it before expiry. Reacquisition after expiry increments the fence even
when the same worker ID is reused. Old fences cannot report, consume or start.
A replacement worker must reconcile the persistent local journal and observed
boot state, then report using the new fence; a lease timeout alone never
concludes that the old hardware operation stopped.

### Gateway proof and token

1. Generate a unique P-256 device key locally, protect it mode0600, enroll only its
   public PEM through the authorized operator endpoint.
2. `POST /v1/device-challenges` with `{"gateway_id":"..."}`. Response contains
   `nonce`, `message` (base64url bytes), and UTC `expires_at` (120s).
3. Sign the decoded exact `message` bytes using ECDSA SHA-256. Encode raw 64-byte
   `r || s` big-endian signature as base64url without padding.
4. `POST /v1/device-token` with `gateway_id`, `nonce`, `signature`. Response:
   `access_token`, `token_type` Bearer, `expires_in`900. Challenge is one-use.
5. Device JWT is ES256 with dedicated issuer/audience. Every protected operation
   additionally checks live home/Gateway/tenant/ownership epoch and revocation.

### Signed install grant and state reports

Grant response is `{"payload":{...},"signature":"<base64url raw64>",
"key_id":"...","algorithm":"ES256"}`. Signature covers canonical JSON of
**payload only**: ASCII JSON, keys sorted recursively, compact separators,
`ensure_ascii=True`, no NaN. Use `identity.verify_signed(envelope, pinned_public_key)`
on Gateway; never trust a key supplied inside the response.

Payload fields: `type`=`ota-install-grant-v1`, `tenant_id`, `home_id`, `gateway_id`,
`target_id`, `artifact_sha256`, `job_id`, `generation`, `owner_epoch`, `lease_fence`,
`policy_revision`, `nonce`, `issued_at`, `expires_at`. Expiry is exactly issue+120
UTC seconds. Verify every binding and trusted clock locally, journal the consumed
grant durably, then call the consume endpoint before activation. If offline or
response is uncertain, reconcile cloud/local journal instead of retrying flash.
Every next target/retry needs a fresh grant. Only one unexpired outstanding grant
is issued per home. A paused campaign/policy change stops new grants; an already
issued grant may be used within its 120s bound. Ownership changes always revoke.
Already started work can finish local validation/rollback after the window or
lease ends; cloud reports wait until a valid lease is reacquired.

No report can directly move OFFERED to SUCCEEDED or INSTALLING. Consume sets
INSTALLING; normal progression is REBOOTING → LOCAL_VALIDATING → SUCCEEDED.
SUCCEEDED requires matching artifact version/hash, a new boot ID relative to the
recorded pre-update boot, health true and a consumed install nonce. Duplicate
identical reports are idempotent; changed duplicate evidence, terminal-state
changes, stale generations/fences/owners and customer result writes are denied.
ROLLED_BACK requires a new boot ID, the recorded previous hash, and health true.
REPORT_PENDING holds the hardware lane until reconciliation. A rollback,
NEEDS_SERVICE, or explicit brick/relay/signature/compatibility incident pauses
new grants immediately. Failure ratio >1% after at least20 install outcomes also
pauses. Offline/blocked states are excluded from that denominator.

## Verification and pilot limits

```sh
PYTHONPATH=Gateway <private-venv>/bin/python -m unittest discover \
  -s Gateway/tests -p test_fleet_ota_service.py
```

Tests inject a memory transaction backend, test auth, and ephemeral P-256 keys.
The Firebase adapter test deliberately retries the callback and checks one
committed increment. No production memory backend, embedded account secret, or
service account is generated by tests.

This service has no automatic install retries, promotions, artifact garbage
collection, audit archival, or signing-key rotation daemon. Terminal failures
require an operator decision/new campaign; this avoids unattended reboot loops.
Keep lab/pilot gates and24h promotion observation (48h pilot target) as manual
operator checks. Plan signed key rotation and 90-day log/artifact / one-year audit
retention before wider fleet rollout. Host tests do not establish Internet IAM,
Firebase security-rule deployment, real GCS signed downloads, board safety,
radio behavior, power-cut recovery, or relay acceptance.
