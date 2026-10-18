# Home Competition SQLite Database Schema & Storage Model

## 1. Overview & Constraints

The Gateway serves as the authoritative source of truth for home structure, device ownership, channel bindings, and firmware artifacts.

- **Engine:** SQLite 3.x with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), Full Synchronous writes (`PRAGMA synchronous=FULL`), and Foreign Key enforcement (`PRAGMA foreign_keys=ON`).
- **Encryption:** Node operational secrets and credential ciphers are encrypted using 256-bit AES-GCM (Fernet) derived from the Gateway master key.
- **Transactions:** Atomic mutations using `BEGIN IMMEDIATE` transactions.

## 2. Relational Schema & Tables

### 2.1. Homes & Permissions
- `users`: User identity and authentication token hashes.
- `homes`: Homes registered on the Gateway.
- `home_members`: Role-based access control (`Owner`, `Member`, `Installer`).
- `rooms`: Rooms partitioned by home (`home_id`, `name` unique).

### 2.2. Hardware Registry & Identity
- `factory_devices`: Immutable manufacturer records (`factory_id`, `product_type`, `model`, `secret`, `setup_hash`, `revoked`).
- `registered_nodes`: Enrolled nodes (`node_id`, `factory_id`, `home_id`, `registration`, `connectivity`, `config_rev`, `reported_rev`, `boot_id`, `last_seen`, `firmware`).
- `node_assignments`: Hierarchical placement (`node_id`, `room_id`, `parent_id`, `primary_subbox`, `active`). Enforces that each room has at most one primary SubBox, and each ActionBox belongs to exactly one parent SubBox.
- `node_credentials`: Per-node encrypted cryptographic credentials.
- `pairing_claims`: Active time-bounded enrollment claims.
- `session_challenges`: Ephemeral session challenges for boot verification.
- `admitted_boots`: Verified boot generations preventing replay attacks.

### 2.3. SmartChannels & Electrical Devices
- `channels`: Hardware relay/CT channels (`channel_id` = `HC-{MAC}:CH{1..3}`, `node_id`, `number`, `command_generation`).
- `devices`: Logical electrical appliances (`device_id`, `home_id`, `name`, `kind`).
- `device_bindings`: Active mappings between `device_id` and `channel_id`.
  - Enforces `UNIQUE(channel_id) WHERE active=1`: Exactly one electrical device per channel.
  - Enforces `UNIQUE(device_id) WHERE active=1`: Exactly one channel per electrical device.
- `channel_states`: Reported hardware states (`relay_state`, `current_rms_a`, `ct_valid`, `fault_flags`, `boot_id`, `state_seq`, `config_rev`).

### 2.4. Telemetry, Snapshots & History
- `state_events`: Append-only event history for transitions, faults, and alerts.
- `room_state_snapshots`: Fast-reconciliation state snapshots per room.
- `config_revisions`: Versioned configuration payloads for delta synchronizations.
- `commands`: Durable command audit and idempotency table (`user_id`, `idempotency_key` unique).
- `audit_logs`: Administrative actions tracking.

### 2.5. Over-The-Air (OTA) Updates
- `firmware_artifacts`: Validated binary releases (`artifact_id`, `model`, `version`, `size`, `sha256`, `manifest`, `signature`, `path`).
- `ota_jobs`: Campaign tracking per home.
- `ota_targets`: Target node execution status (`QUEUED`, `TRANSFERRING`, `VERIFYING`, `REBOOTING`, `HEALTH_CHECK`, `SUCCEEDED`, `FAILED`, `ROLLED_BACK`).
