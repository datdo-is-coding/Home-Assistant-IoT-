# Home Competition — repository audit

Audited 2026-10-15, starting revision `8d9d5ad`. Working tree initially clean.
This document records source inspection, not hardware acceptance.

## Active implementation

| Area | Existing source | Findings |
|---|---|---|
| Gateway | `Gateway/gateway/` | Python asyncio, custom HTTP/SSE server, aiomqtt, JSON/SQLite registry, authentication, ASR/TTS, HA discovery, legacy HTTP/MQTT OTA. Registry treats a Box as a device; no independent immutable electrical-device binding model. |
| SubBox | `Firmware/firmware_esp/SubBox/` | ESP-IDF C++, Wi-Fi STA/MQTT, ESP-NOW audio and command routing, four-child room registry, local NLU, remote ASR, I2S output. TLS credentials and per-peer LMKs can be installed using physical USB console. |
| ActionBox production target | `Firmware/firmware_esp/ActionBox_V2/` | User confirmed this board pin map. Three dual-coil latching relays, three BL0942 metering RX paths on UART1, INMP441, WakeNet, local buttons, watchdog, safe RESET pulses on startup. Network transport currently auto-pairs and installs unencrypted peers. |
| Older ActionBox | `Firmware/firmware_esp/ActionBox/` | Two monostable relays, two BL0942 paths; preserve as a separate legacy board target. |
| App | `App/dtv_energy_flutter/` | Existing Flutter/Riverpod app, Gateway client and repository, rooms, ActionBoxes, devices, authentication and tests. Uses legacy APIs; keep available during migration. |
| Support | `MQTT_Server/`, `Firmware/tools/` | Mosquitto/docker configuration, development provisioning and HIL scripts. |
| Historical | `archive/`, `Esp32S3_Master`, KWS training | Reference only; no migration by blindly copying historical implementations. |

## Hardware and toolchain

- `idf.py --version`: **ESP-IDF v6.0.2**, installed locally; GCC/CMake and Flutter commands available.
- ActionBox_V2 relay SET/RESET GPIO: CH1 16/15, CH2 7/6, CH3 5/4; 50 ms pulses. BL0942 TX9/RX10,11,12. No direct CT ADC pin map exists: reuse calibrated BL0942 current readings; do not invent an ADC driver or infer watts from RMS current.
- ActionBox_V2 microphone BCLK47/WS48/DIN8; amplifier shutdown GPIO38. SubBox I2S speaker BCLK17/LRC18/DOUT21, shutdown GPIO2; source calls this MAX98357, exact BOM suffix remains UNVERIFIED.
- Existing 16 MiB flash partitions: NVS, OTA metadata, two application slots (0x2f0000 and 0x300000), 8 MiB voice model, storage. Preserve offsets; OTA must honor the smaller slot capacity.
- ESP-SR pinned 2.5.5; cJSON and MQTT/WebSocket versions resolved in project lock files. Preserve WakeNet/model flashing and audio tasks.
- Safety and relay FreeRTOS tasks outrank networking. RX callbacks queue data; no flash writes or relay execution should be added to radio callbacks.

## Incompatibilities and missing production guarantees

- Current JSON protocol is **v3**, unrelated to new **HC protocol v1**; legacy short WS relay protocol also exists. Explicit version/magic/topic routing is required; never reinterpret one as another.
- Legacy node ID and MAC-derived identity are not cryptographic ownership. Autodiscovery cannot authorize Core nodes.
- Network JSON can exceed ESP-NOW v1's 250 bytes. New HC control frames must stay within 250 bytes; keep existing voice packets distinct.
- ActionBox_V2 currently accepts heartbeat-based parent association. A Core-enrolled device must reject legacy commands and unauthorized parents.
- Existing OTA checks ESP image headers/MD5 and can report upload completion; it is not signed, model-bound, post-boot-verified three-tier OTA.
- Configured encrypted SubBox peers do not imply ActionBox_V2 secure enrollment is implemented.
- IR pins in V2 are reserved, not an implemented IR feature. Do not claim local offline ASR or trained quick commands solely from WakeNet/remote ASR code.
- Old documentation predates V2 and security changes; use source and tests as evidence.

## Baseline evidence

`python3 -m unittest discover -s Firmware/tests -p test_actionbox_v2.py -v`:
**4/4 passed** (host compilation of real relay/meter/storage/protocol/safety code).
This does not test relay contacts, radio propagation, calibration or power loss.
No board was flashed and no irreversible eFuse operation was performed.

## Migration decision

Keep existing directory layout and services. Add the HC implementation under
`Firmware/firmware_esp/common/hc_core` and `Gateway/gateway/core_v1`; mount its
management service separately from legacy API to avoid interpreting an old
authentication session as new home ownership. Add an explicit Core entry point
to the existing Flutter project. No automatic claims from existing JSON data.
Legacy firmware remains buildable; migration requires physical enrollment and
explicit channel-to-Device-ID mapping. A Core-enrolled Box has exactly one command
authority. Database backups and a read-only migration inventory precede adoption.

## Version-specific references

- [ESP-NOW 6.0.2](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/api-reference/network/esp_now.html): 250-byte baseline, channel coexistence, application ACK, peer encryption and callback restrictions.
- [OTA 6.0.2](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/api-reference/system/ota.html): dual slots, validation and rollback.
- [Official network provisioning](https://github.com/espressif/idf-extra-components/tree/master/network_provisioning): ESP-IDF 6 external component; prefer protocomm security over bespoke crypto.
