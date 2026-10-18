# HOME COMPETITION PROTOCOL SPECIFICATION V1 (HC-V1)

**Version:** 1.0.0  
**Status:** RELEASED / ACTIVE  
**Product:** Home Competition Core V1  
**Architecture:** Gateway (Raspberry Pi 4) ↔ SubBox (ESP32-S3) ↔ ActionBox (ESP32-S3)

---

## 1. Overview & Architecture

Home Competition Core V1 uses a unified logical protocol model running across two physical/transport layers:

1. **HC-WIFI (Transport Layer 1):**
   - **Endpoints:** Gateway ↔ SubBox.
   - **Medium:** Wi-Fi 2.4 GHz STA, TCP/IP, MQTT with TLS (Port 8883) & Per-Device Client ACLs.
   - **Serialization:** JSON structured payloads with binary payload base64 encoding where appropriate.

2. **HC-NOW (Transport Layer 2):**
   - **Endpoints:** SubBox ↔ ActionBox.
   - **Medium:** ESP-NOW 2.4 GHz Unicast radio with CCMP hardware encryption (LMK per peer).
   - **Serialization:** Binary Little-Endian Fixed-Header Frame (Max frame length: 250 bytes).

---

## 2. HC-NOW Binary Frame Wire Format

Each HC-NOW packet has a 38-byte binary header, followed by a payload of 0 to 196 bytes, and ends with a 16-byte HMAC-SHA256 authentication tag (truncated from 32 bytes). Total wire frame size is strictly between 54 and 250 bytes.

### 2.1. Frame Layout

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Magic: 'H' 'C'        |    Version    | Message Type  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Flags     |  Payload Len  |       Message ID (Low 32)     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Message ID (High 32)     |        Source Node ID         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Destination Node ID       |       Boot / Session ID (Low) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Boot / Session ID (High)   |        Sequence Number        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Config Revision         |     Payload (0 to 196 bytes)  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
...                             |  HMAC-SHA256 Tag (16 bytes)   ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 2.2. Header Field Definitions (38 Bytes Total)

| Offset | Field | Type | Description |
|---|---|---|---|
| `0..1` | `magic` | `uint8_t[2]` | ASCII `"HC"` (`0x48`, `0x43`). Mandatory validation check. |
| `2` | `version` | `uint8_t` | Protocol version = `1`. |
| `3` | `type` | `uint8_t` | Message type (1..29). |
| `4` | `flags` | `uint8_t` | Bit 0: ACK requested (`0x01`), Bit 1: Fragmented (`0x02`). |
| `5` | `payload_len` | `uint8_t` | Length of payload: `0 <= len <= 196`. |
| `6..13` | `message_id` | `uint64_t` | Globally unique message ID (little-endian). Must be non-zero. |
| `14..17` | `source` | `uint32_t` | Sender logical Node ID (0 = Gateway / broadcast during pairing). |
| `18..21` | `destination` | `uint32_t` | Target logical Node ID. |
| `22..29` | `boot_id` | `uint64_t` | Sender boot generation / session random nonce. Must be non-zero. |
| `30..33` | `sequence` | `uint32_t` | Monotonically increasing sequence number per boot_id. |
| `34..37` | `config_rev` | `uint32_t` | Active configuration revision of sender. |

### 2.3. Tail Field (16 Bytes)

| Offset | Field | Type | Description |
|---|---|---|---|
| `38+len..53+len` | `hmac_tag` | `uint8_t[16]` | Truncated HMAC-SHA256 computed over bytes `0..(38+len)` using the per-device 256-bit application key. |

---

## 3. Message Types Enumeration

| Code | Name | Direction | Description |
|---|---|---|---|
| `1` | `HELLO` | Node → SubBox/GW | Announce node presence, MAC, and boot ID. |
| `2` | `IDENTITY_CHALLENGE` | GW/SubBox → Node | Random 32-byte cryptographic nonce challenge. |
| `3` | `IDENTITY_RESPONSE` | Node → GW/SubBox | HMAC response over challenge using device master secret. |
| `4` | `PAIR_REQUEST` | Node → GW/SubBox | Request pairing during provisioning window. |
| `5` | `PAIR_ACCEPT` | GW/SubBox → Node | Pairing approved; credentials and assigned Node ID attached. |
| `6` | `PAIR_REJECT` | GW/SubBox → Node | Pairing rejected (unauthorized, expired, or mismatch). |
| `7` | `HEARTBEAT` | Both directions | Node availability check (default interval: 5 seconds). |
| `8` | `CAPABILITY_REPORT` | Node → GW | Hardware capabilities (3 relays, 3 CTs, model HC-A1/HC-S1). |
| `9` | `CONFIG_PUSH` | GW/SubBox → Node | Push updated configuration / channel bindings. |
| `10` | `CONFIG_ACK` | Node → GW/SubBox | Acknowledge applied configuration revision. |
| `11` | `COMMAND` | GW → SubBox → Node | Actuation command (e.g., SET_STATE for relay). |
| `12` | `COMMAND_ACK` | Node → SubBox → GW | Command status: RECEIVED, ACCEPTED, APPLIED, FAILED. |
| `13` | `STATE_REPORT` | Node → SubBox → GW | Channel state change (immediate on relay transition). |
| `14` | `TELEMETRY_REPORT` | Node → SubBox → GW | Periodic power / RMS current data (interval: 2 seconds). |
| `15` | `EVENT_REPORT` | Node → SubBox → GW | Critical event (fault, emergency cutoff, power loss). |
| `16` | `ROOM_SNAPSHOT` | SubBox → GW | Full state aggregate of all nodes in room. |
| `17` | `STATE_SYNC_REQUEST` | GW/SubBox → Node | Request full state re-broadcast after reconnect. |
| `18` | `ERROR_REPORT` | Node → GW | Hardware error code, sensor fault, or watchdog alert. |
| `19` | `OTA_OFFER` | GW/SubBox → Node | Announce firmware availability (model, version, size, sha256). |
| `20` | `OTA_START` | GW/SubBox → Node | Initiate OTA transfer session. |
| `21` | `OTA_PROGRESS` | Node → GW/SubBox | Report received chunk offset and written percentage. |
| `22` | `OTA_RESULT` | Node → GW/SubBox | Post-boot health check result (SUCCESS / ROLLBACK). |
| `23` | `OTA_ABORT` | Both directions | Cancel active OTA job with reason code. |
| `24` | `UNPAIR` | GW/SubBox → Node | Revoke credentials, clear peer keys, factory reset NVS. |
| `25` | `FACTORY_RESET_REQUEST`| GW/App → Node | Reset node to out-of-box unregistered state. |
| `26` | `OTA_CHUNK` | SubBox → Node | Firmware binary block (up to 184 bytes per chunk). |
| `27` | `OTA_CHUNK_ACK` | Node → SubBox | Chunk received, hash checked, and flashed. |
| `28` | `FRAGMENT` | Both directions | Multi-packet data fragment for configs > 196 bytes. |
| `29` | `CHANNEL_PROBE` | Node → SubBox | Wi-Fi channel sync and peer existence probe. |

---

## 4. Reliability, Duplicate Detection & Idempotency

### 4.1. Replay Window & Session Admission
- A receiving node maintains a 32-packet bitmask replay window per admitted session.
- A newly discovered `boot_id` requires explicit admission via `IDENTITY_CHALLENGE`/`IDENTITY_RESPONSE`. A random unverified `boot_id` is rejected with `SESSION_REQUIRED`.
- In-window duplicates (`mask & (1 << delta)`) are silently acknowledged with the cached ACK and discarded.
- Packets older than 32 sequences (`delta >= 32`) are discarded as `STALE`.

### 4.2. Idempotent Relay Control
- Network controls use strictly idempotent operations:
  - `SET_STATE(relay_idx, state)` where `state` is `0` (OFF) or `1` (ON).
  - Network `TOGGLE` is prohibited to prevent state inversion on retransmissions.
- Each command carries:
  - `command_id` (UUID / 64-bit int).
  - `generation`: Monotonically increasing command generation per channel. Stale generations are rejected.
  - `config_rev`: Active configuration revision. If mismatch, rejected with `CONFIG_MISMATCH`.
  - `ttl`: Maximum lifetime (e.g. 1000 ms). Commands older than TTL are dropped.

### 4.3. Retry Queue & Application ACKs
- Application ACK timeout: 250 ms.
- Max retries: 3 attempts.
- Total queue capacity: 16 items. Backpressure returns `BufferError` if saturated.

---

## 5. Security & Key Hierarchy

1. **Factory ID:**
   - Format: `HC-{12_HEX_MAC}` (e.g., `HC-7C9EBD42A153`).
   - Derived from immutable eFuse Base MAC.
   - Used for identification only, never as an authentication token.

2. **Factory Secret:**
   - 256-bit unique random key provisioned at factory per device in NVS / eFuse.
   - Setup code: 8-character unique alphanumeric base32 / QR string.

3. **Application Session Key:**
   - 256-bit symmetric key derived during secure provisioning via Protocomm Security 1 (Curve25519 + AES-CTR).
   - Used for HMAC-SHA256 message authentication on all HC-NOW frames.

4. **ESP-NOW Link Master Key (LMK):**
   - 128-bit CCMP encryption key installed into ESP-NOW peer table.
   - Provides physical-layer radio frame confidentiality.

---

## 6. SmartChannel & Data Model

Each ActionBox possesses exactly 3 SmartChannels:
- `CH1`: Relay 1 + CT 1
- `CH2`: Relay 2 + CT 2
- `CH3`: Relay 3 + CT 3
- Format: `HC-{12_HEX_MAC}:CH{1..3}`

### Channel State Packet Payload (16 bytes):
- `channel_number`: `uint8_t` (1..3)
- `relay_state`: `uint8_t` (0 = OFF, 1 = ON)
- `ct_valid`: `uint8_t` (0 = Invalid/Fault, 1 = Valid)
- `fault_flags`: `uint8_t` (Bit 0: Overcurrent, Bit 1: Relay Jammed, Bit 2: CT Comm Error)
- `current_rms_mA`: `uint32_t` (RMS current in milliamperes, little-endian)
- `reserved`: `uint8_t[8]`
