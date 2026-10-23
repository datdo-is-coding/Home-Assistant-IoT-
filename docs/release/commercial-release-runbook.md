# Commercial Release, OTA & Operational Maintenance Runbook (Milestone M4 - Task T15)

*Target: SIC Home Commercial Production*  
*Scope: ActionBox V2, SubBox Gateway, Gateway Python Server, Android Flutter App*  
*Audit Reference: Findings #9, #10, #11, #16, #17, #18, #19, #20*

---

## 1. Executive Summary

Task T15 closes out the operational requirements from previous audits, establishing a hardened release pipeline across:
1. **Signed OTA Firmware Delivery:** Strict model-to-board binding, TTL download tickets, magic header verification, and automatic rollback.
2. **Database Integrity & Retention:** SQLite WAL mode, asynchronous retention pruning, and atomic backup procedures.
3. **Production Android Signing:** Dedicated release keystores, Keystore-backed session tokens, and zero-debug key policy in production.

---

## 2. Firmware Release Manifest Specification

Every commercial firmware release artifact must be published alongside a structured manifest:

```json
{
  "artifact_id": "fw_actionbox_v2_20261020_v1.2.0",
  "board_model": "actionbox_v2",
  "board_revision": "rev_c",
  "firmware_version": "1.2.0",
  "protocol_version": 1,
  "chip": "ESP32-S3",
  "magic_header": "0xE9",
  "flash_size_bytes": 1048576,
  "sha256": "4a72d6349b18361093f18e95c13f6381ab924d5e94b29f9c73b06381bc26c891",
  "md5": "e2c3882a17957e62a5fe8f0a5f8e5621",
  "min_bootloader_version": "1.0.0",
  "capabilities": ["relay_3ch", "energy_pzem", "espnow_mesh"],
  "signing_key_fingerprint": "SHA256:7f3b89a1c4...",
  "created_at": "2026-10-20T00:00:00Z"
}
```

### Manifest Enforcement Rules (Audits #10 & #11):
1. **Magic Header Byte:** Firmware binaries must begin with byte `0xE9` (ESP-IDF image header). Files failing this check are rejected immediately upon upload.
2. **Board Matching Guard:** A SubBox firmware binary will **never** be flashed onto an ActionBox device, and vice versa.
3. **One-Time Download Tickets (Audit #10):**
   - OTA download URLs do not require user session cookies or long-lived API keys.
   - The Gateway issues a cryptographically random, temporary download ticket (`ticket=...`) tied to the target `device_id` with a 900-second TTL.
   - Attempting to download with an expired ticket or a mismatched device ID returns `403 Forbidden`.

---

## 3. Database Maintenance & SQLite WAL Retention (Audits #16 & #17)

To prevent unbounded disk growth and write stalls on Raspberry Pi / Gateway hosts:

### SQLite Configuration Standards
All database connections (`registry.db`, `auth.db`, `lifecycle.db`) enforce:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

### Telemetry History Retention
- High-frequency telemetry (voltage, current, power) is pruned asynchronously.
- The retention window maintains a maximum of **10,000 samples per node** or **30 days** of rolling history:
  ```sql
  DELETE FROM telemetry_history WHERE id NOT IN (
      SELECT id FROM telemetry_history ORDER BY id DESC LIMIT 10000
  );
  ```

### Atomic Database Backup Runbook
Daily backups must use SQLite's native online backup API (zero downtime, no locking):
```bash
# Execute daily via cron
sqlite3 /home/pi4/Home-Assistant-IoT-/Gateway/data/registry.db ".backup /home/pi4/backups/registry_$(date +%Y%m%d).db"
sqlite3 /home/pi4/Home-Assistant-IoT-/Gateway/data/auth.db ".backup /home/pi4/backups/auth_$(date +%Y%m%d).db"
```

---

## 4. Android Production Signing & Keystore Policy (Audit #18)

### Key Management
1. Production APKs and App Bundles (AAB) must **never** be built using debug keystores.
2. The release keystore is stored outside the Git repository and referenced via `key.properties`:
   ```properties
   storePassword=<SECURE_PASSWORD>
   keyPassword=<SECURE_PASSWORD>
   keyAlias=sic_home_release
   storeFile=/secure/keystores/sic_home_release.jks
   ```
3. In `android/app/build.gradle.kts`:
   - Builds without `key.properties` emit a build-time warning and fail CI release gates.
   - R8 / ProGuard rules are enabled to strip unused code while preserving MethodChannel reflection for native bridges.

---

## 5. Rollback & Emergency Recovery Procedures

| Scenario | Impact | Recovery Protocol |
| :--- | :--- | :--- |
| **Failed OTA Flash** | Device power cut during flashing | ESP-IDF 2-slot partition table automatically boots the previous valid slot (`ota_0` or `ota_1`). Zero user intervention required. |
| **Firmware Boot Crash Loop** | Crash within 30s of new firmware boot | Bootloader self-test watchdog rolls back to the previous boot slot and marks the new partition invalid. |
| **Corrupted Gateway Database** | Database corruption from ungraceful shutdown | Restore the latest snapshot from `/home/pi4/backups/` using `sqlite3 .restore`. |
| **Lost SubBox Route** | SubBox reset or hardware failure | ActionBoxes enter Route Recovery. Hold CONFIG button for 5 seconds to pair with the replacement SubBox. All room names and BL0942 calibration remain preserved. |
