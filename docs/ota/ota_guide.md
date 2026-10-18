# Home Competition Three-Tier OTA Guide

## 1. Architecture

OTA in Home Competition Core V1 encompasses three coordinated tiers:
1. **Gateway Software:** Managed via signed release packages, pre-update SQLite backup, and automated service health check.
2. **SubBox Firmware:** Delivered from Gateway to SubBox via Wi-Fi (HTTPS/MQTT).
3. **ActionBox Firmware:** Coordinated by SubBox and delivered to ActionBox via ESP-NOW binary chunks.

```
[Gateway] ──(Wi-Fi / HTTPS)──> [SubBox Coordinator] ──(ESP-NOW Chunks)──> [ActionBox Responder]
```

## 2. Safety Guarantees & Constraints
- **Signed Images:** All firmware binaries must include a cryptographic signature and manifest verifying model ID, version, and SHA256.
- **Dual Partitioning:** Devices utilize standard ESP-IDF dual-app partitions (`ota_0`, `ota_1`, and `otadata`).
- **Post-Boot Verification:** Writing the image is NOT considered completion. The new firmware must:
  1. Boot into the pending partition.
  2. Complete hardware self-tests (NVS integrity, relay safety check, radio init).
  3. Report its identity and active boot ID to Gateway.
  4. Call `esp_ota_mark_app_valid_cancel_rollback()`.
- **Automatic Rollback:** If the new firmware fails self-test or encounters a watchdog crash, the hardware bootloader automatically reverts to the previous working slot.
- **Relay Invariance:** Relays maintain their active state or safe default through reboot without spurious contact closure.
- **Batching & Sequencing:** SubBox coordinators update ActionBoxes sequentially or in small batches to preserve emergency control.

## 3. ESP-NOW OTA Chunk Protocol (SubBox ↔ ActionBox)

Each ActionBox chunk contains:
- `OTA_CHUNK` (Type 26, flags: 0x02): Offset (32-bit), chunk length (up to 184 bytes), and binary slice.
- `OTA_CHUNK_ACK` (Type 27): Confirms receipt, flash write, and running CRC/SHA.
- In-memory buffer footprint is strictly bounded to <= 256 bytes per chunk to avoid heap exhaustion.
