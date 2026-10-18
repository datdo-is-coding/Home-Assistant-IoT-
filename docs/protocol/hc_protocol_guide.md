# Home Competition Protocol V1 Guide

## 1. Protocol Architecture

Home Competition Core V1 establishes an authenticated, reliable, two-tier communication network:

```
[Flutter App] 
     │ (HTTPS / WebSocket)
     ▼
[Gateway (Pi 4)] 
     │ (HC-WIFI: MQTT TLS + ACL)
     ▼
[SubBox (ESP32-S3)] 
     │ (HC-NOW: ESP-NOW 250-byte Binary Frames + CCMP + HMAC)
     ▼
[ActionBox (ESP32-S3)]
```

### Key Protocol Principles
- **No Network Toggle:** Relay actuation uses explicit `SET_STATE(channel, 0|1)`. Retransmissions can never invert relay state.
- **Explicit Result Codes:** `RECEIVED`, `ACCEPTED`, `APPLIED`, `FAILED`, and `TIMEOUT`. A message transmission callback does NOT imply relay actuation.
- **Replay Window:** 32-entry bitmask sequence tracker with mandatory cryptographic boot admission.
- **Bounded Frame:** Maximum frame length on ESP-NOW is 250 bytes (38-byte header, <= 196-byte payload, 16-byte HMAC-SHA256 tag).
- **Wi-Fi & ESP-NOW Coexistence:** SubBox tracks Wi-Fi channel on STA; ESP-NOW radio locks to the active STA channel. ActionBoxes utilize channel synchronization probes to track channel hops.

## 2. Packet Codecs & Validation

### C Driver (`Firmware/firmware_esp/common/hc_core/hc_protocol.c`)
- Strict little-endian encoding/decoding.
- Constant-time HMAC comparison using MbedTLS / PSA Crypto.
- Rejection of malformed magic, version != 1, illegal flags, and mismatched lengths.

### Gateway Python Codec (`Gateway/gateway/core_v1/protocol.py`)
- Standard library `struct` and `hmac` implementations.
- Mirror test vectors verified identically between C and Python in `protocol/test_vectors/hc_v1.json`.

## 3. Reliability & Queuing
- Bounded retry queue with exponential/fixed backoff and strict TTL expiration.
- In-memory Reassembler for chunked configurations and firmware manifests with overlap consistency checks.
