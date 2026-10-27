# Independent Gateway updater

This updater targets the existing `gateway/main.py`, profile `legacy-main-v1`.
It does not run the Core-only Gateway, install dependencies from the Internet,
change OS/boot firmware, restore databases automatically, or update itself in the
application transaction. No live services are changed by adding these files.

## Operator configuration and bootstrap

Install the updater and its pinned Python environment outside the application
releases, for example `/opt/homecompetition-updater/{Gateway,venv}`. Create
`/opt/homecompetition/releases` owned by the updater with mode `0755` or `0700`
as appropriate for the Gateway service account. Its contents must not be writable
by the Gateway account. Keep application data, credentials, config, model assets
and logs outside that directory. The updater needs P-256 public verification
material and an independent raw 32-byte recovery encryption key; it never needs
the signing private key.

Example `/etc/homecompetition/ota-updater.json` (mode `0600`):

```json
{
  "root": "/opt/homecompetition/releases",
  "public_key": "/etc/homecompetition/release-public.pem",
  "recovery_key": "/etc/homecompetition/recovery.key",
  "runtime_source": "/home/pi4/voice_gateway_venv",
  "service": "smarthome-gateway.service",
  "health_url": "http://127.0.0.1:8080/api/health",
  "inventory": {
    "databases": {
      "registry": "/home/pi4/Home-Assistant-IoT-/Gateway/gateway/gateway.db",
      "auth": "/home/pi4/smarthome/auth.db",
      "memory": "/home/pi4/smarthome/memory.db"
    },
    "files": {
      "gateway.env": "/etc/homecompetition/gateway.env",
      "device.key": "/etc/homecompetition/device.key"
    },
    "data_roots": ["/home/pi4/smarthome", "/home/pi4/Home-Assistant-IoT-/Gateway/gateway"]
  }
}
```

These are illustrative paths, not an assertion that all three DBs are enabled or
that port `8080` is the deployed port. Audit the active service environment and
all stores first. Include lifecycle/registry, auth, memory or other enabled DBs,
all needed config/credential files and every data directory in `data_roots`.
An unlisted SQLite-header file or `.db`, `.sqlite` or `.sqlite3` file in those
roots blocks activation.
Inventory names are stable manifest identifiers. Files must exist; omit disabled
stores rather than creating empty production DBs. SQLite API snapshots include
committed WAL data and pass integrity/foreign-key checks. Encrypted `0600`
archives retain the exact private config/key bytes. Keep the recovery key backed
up separately; the archive does not contain it. Existing secrets are never
overwritten or loaded from the release.

Stage a signed package of the current known-good software first and establish
`current -> <version>` only after verifying it on the intended service. Bootstrap
is an explicit operator step: the updater will not turn an arbitrary source tree
into an implicitly healthy rollback release. Change the service's trusted unit
configuration to use:

```ini
[Unit]
Requires=homecompetition-ota-updater.service
After=homecompetition-ota-updater.service

[Service]
WorkingDirectory=/opt/homecompetition/releases/current/gateway
Environment=PYTHONPATH=/opt/homecompetition/releases/current/gateway
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=/etc/homecompetition/gateway.env
ExecStart=
ExecStart=/opt/homecompetition/releases/current/runtime/bin/python3 /opt/homecompetition/releases/current/gateway/main.py
```

Keep all DB paths and writable cache/model/log paths explicit in the external
environment. The legacy Gateway otherwise has relative-path fallbacks which
must not write inside the immutable release. Install/enable the recovery unit
only once its paths and bootstrap release exist. Do not point the updater's own
`PYTHONPATH` or Python binary at `current`.

## Signed package contract

The artifact is a bounded tar archive containing `gateway/main.py` and its
application files. Only regular files/directories are accepted; traversal,
links, special files, duplicate paths, setuid bits and reserved `.ota/` metadata
are rejected. Python application sources must parse. Files are frozen read-only;
executable files retain execution permission.

Sign the exact UTF-8 JSON manifest bytes with ECDSA P-256/SHA-256, DER signature:

```json
{
  "format": 2,
  "target": "home-competition-gateway",
  "entrypoint": "gateway/main.py",
  "version": "2.0.1",
  "runtime": {
    "os": "linux",
    "architecture": "aarch64",
    "python_abi": "cpython-312",
    "profile": "legacy-main-v1"
  },
  "runtime_sha256": "<canonical runtime digest>",
  "size": 12345,
  "sha256": "<artifact SHA-256>",
  "database_schema": {"registry": 0, "auth": 0, "memory": 0},
  "rollback_compatible": true,
  "release_counter": 3,
  "security_epoch": 0,
  "expires_at": 1793149200
}
```

Use actual `PRAGMA user_version` values for the audited DB inventory. Every DB
must be named. Destructive/incompatible migrations are unsupported; old and new
releases must declare identical schema versions. Counter must increase and
security epoch must not decrease. An unexpected schema change during new
runtime health leaves `NEEDS_SERVICE`; the updater keeps the customer's new
writes and does not restart incompatible old code or restore a snapshot.

Bundle a pinned, host-compatible runtime under `runtime/`, with the fixed
executable `runtime/bin/python3`. Alternatively, set trusted `runtime_source`
to an audited local venv/runtime; staging copies it, dereferences its links, and
verifies its content against the *signed* `runtime_sha256`. No path or command in
the artifact chooses a host interpreter. Venvs still depend on their matching
host Python standard library/native libraries: test relocation and imports on
the actual OS/ABI before signing. `host_profile()` reports the required fields;
the CLI compares signed fields to its host Python/OS/CPU. The signature and
runtime digest do not independently prove native-library ABI correctness.

```bash
PYTHONPATH=/opt/homecompetition-updater/Gateway /opt/homecompetition-updater/venv/bin/python -m gateway.ota_updater runtime-digest /home/pi4/voice_gateway_venv
PYTHONPATH=/opt/homecompetition-updater/Gateway /opt/homecompetition-updater/venv/bin/python -m gateway.ota_updater --config /etc/homecompetition/ota-updater.json stage app.tar.gz manifest.json manifest.sig
```

After a fresh grant and the coordinator's maintenance/preflight gates:

```bash
PYTHONPATH=/opt/homecompetition-updater/Gateway /opt/homecompetition-updater/venv/bin/python -m gateway.ota_updater --config /etc/homecompetition/ota-updater.json activate 2.0.1
```

The CLI controls only `smarthome-gateway.service` or
`homecompetition-gateway.service`; manifest fields never become commands.
The library exposes `GatewayUpdater(root, public_key, runtime_profile, inventory,
recovery_key, runtime_source=None)`, `stage(...)`, `activate(version, stop=...,
start=..., health=...)`, `recover(...)`, and `prepare_boot_recovery()`. Lifecycle
callbacks are trusted operator code. The library's explicit profile is for
trusted integration/tests; the CLI derives the host profile itself.

## Recovery and health

An exclusive process lock covers staging, activation and recovery. Activation
reverifies signatures, artifact content, runtime digest and live schemas before
stopping the service. Fsynced atomic journal writes surround each boundary:
`PREPARED`, `STOPPED`, `SWITCHED`, `VERIFYING`, `COMMITTED`. Private backup files,
runtime files, pointer changes and parent directories are fsynced. Any unfinished
transaction rolls back to the verified previous software directory, regardless
of whether the new `current` pointer was already switched. Recovery can itself
be interrupted and repeated. Previous/new DB writes are preserved throughout.

The boot unit calls `boot-recover`: it verifies/restores the previous pointer
before the Gateway can start, leaving the journal `RECOVERING` and reporting
`RECOVERY_PENDING_HEALTH`. It intentionally does not start an ordered systemd
unit from its `Before=` gate. Once boot completes, the independent coordinator
must call `recover` to stop/start/health-check and finalize `ROLLED_BACK`:

```bash
PYTHONPATH=/opt/homecompetition-updater/Gateway /opt/homecompetition-updater/venv/bin/python -m gateway.ota_updater --config /etc/homecompetition/ota-updater.json recover
```

`NEEDS_SERVICE` returns exit status 1 and blocks the boot gate. It requires
operator diagnosis, never factory reset. `inspect_backup(path, recovery_key)`
decrypts a backup to a file-name/bytes mapping for inspection; no automatic
restore path is exposed.

The default CLI health is a bounded literal-loopback HTTP check. The existing
legacy `/api/health` only returns `status: ok`: it proves an HTTP/event-loop
response, not transport/worker readiness. Production integration must supply a
trusted richer `health` callback checking config/DB loading, local transport and
workers, and no crash loop. A cloud connection or an offline Box must not be a
health requirement. The updater itself checks SQLite integrity/schema before
commit and rollback. Host tests with fake service callbacks do not establish
Pi runtime, systemd, cloud-grant, hardware OTA or physical power-cut acceptance.
