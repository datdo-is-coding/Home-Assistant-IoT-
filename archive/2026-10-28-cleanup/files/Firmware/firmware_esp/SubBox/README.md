# SubBox / SubGateway Firmware

## Current voice mode: Pi4 processing only

ActionBox captures 16 kHz mono PCM and sends it over ESP-NOW. SubBox forwards
the PCM over WebSocket with the originating ActionBox `node_id`,
`audio_relay: true`, and `asr_only: false`. Pi4 performs speech recognition,
intent extraction and device selection, then sends commands through
MQTT -> SubBox -> ActionBox. Audio sockets are not relay-command transports.

Local DummyASR/offline fallback and the SubBox voice NLU task are disabled.
Gateway transcripts are diagnostic only: they never trigger a second local
command. If the audio connection fails, no fallback command is generated.
ActionBox keeps energy VAD and push-to-talk for recording boundaries, with
WakeNet disabled; saying "Hi ESP" is no longer required.

Deploy the updated `Gateway/gateway/audio_server.py` and restart the Gateway,
then build/flash both ActionBox and SubBox. The WebSocket URI must point to the
Pi audio server (port 8765); the existing security configuration overrides the
default URI in `src/config/subbox_config.h`.

Offline checks from the repository root:

```sh
python3 -m unittest discover -s Gateway/tests -p test_audio_relay.py -v
python3 -m unittest discover -s Firmware/tests -p test_audio_relay.py -v
```

The older local-ASR/NLU architecture described below is historical and is not
the active microphone path.

Production-grade firmware for the **ESP32-S3 SubBox (SubGateway)** — the intelligent local room brain and distributed audio hub of the smart-home IoT ecosystem, built on **ESP-IDF 6.0.2** and **FreeRTOS** (PlatformIO compatible).

---

## 1. System Role & Architecture

```
ActionBox 1 (Mic, Spk, Relay, Current) ──┐
ActionBox 2 (Mic, Spk, Relay, Current) ──┤ UDP Audio:5005   ┌──────────────────────────────────────────────┐
ActionBox 3 (Mic, Spk, Relay, Current) ──┼─────────────────>│                   SubBox                     │
ActionBox 4 (Mic, Spk, Relay, Current) ──┘                  │                                              │
                                                            │ • Audio Manager (RMS & VAD arbitration)      │
ActionBox 1..4 Speakers <───────────────────────────────────┤ • Single-Stream ASR Pipeline (Replaceable)   │
                          UDP Audio:5006 (Targeted Downlink)│ • Vietnamese Text Normalizer                 │
                                                            │ • Local Deterministic NLU (Intent & Entity)  │
                                                            │ • Dialogue Context Manager ("tắt nó")       │
                                                            │ • Local Command Router & Rule Engine         │
                                                            │ • ActionBox State Registry                   │
                                                            └──────────────────────┬───────────────────────┘
                                                                                   │ MQTT (home/subbox/...)
                                                                                   ▼
                                                                        Raspberry Pi 4 / Cloud
                                                                  (Complex reasoning, LLM, historical)
```

### Key Architectural Tenets:
1. **No Direct Microphone on SubBox**: SubBox does **NOT** initialize an onboard I2S microphone driver. All audio input originates from ActionBox microphones transmitted over the network (UDP / ESP-NOW).
2. **Multi-ActionBox Arbitration**: Supports up to 4 ActionBoxes per room. Instead of running 4 concurrent ASR engines (which would overwhelm memory/compute), the **Audio Manager** tracks packet loss, RMS energy, and VAD state to dynamically route the single *best* active stream to the ASR engine.
3. **Targeted Voice Response**: Audio feedback / TTS is routed specifically to the ActionBox where the user spoke (`last_input_audio_node`), avoiding whole-room audio chaos.
4. **Local Independence**: Basic voice commands ("bật đèn", "tắt quạt", "nhiệt độ bao nhiêu") and local protection rules (overcurrent trips, automatic fan cooling) execute locally on SubBox without Raspberry Pi 4.
5. **Complex Intent Forwarding**: Multi-condition, temporal, or cross-room whole-house logic ("nếu nhiệt độ trên 30 độ thì bật quạt") is detected and forwarded to Raspberry Pi 4 via MQTT.

---

## 2. Directory Structure (Section 26 Compliance)

```
SubBox/
├── platformio.ini               # PlatformIO 16MB Flash + PSRAM environment
├── CMakeLists.txt               # ESP-IDF 6.0.2 / 5.5 top-level project CMake
├── partitions.csv               # 16MB partition map (NVS, OTA0/1, Model, Storage)
├── sdkconfig.defaults           # 240MHz, 16MB Flash DIO, 16MB Octal PSRAM
├── build.ps1                    # One-click native ESP-IDF build script
├── flash.ps1                    # One-click flash & monitor script
└── src/
    ├── main.cpp                 # Firmware entry point & subsystem assembly
    ├── CMakeLists.txt           # Component registration & dependencies
    │
    ├── config/
    │   ├── subbox_config.h      # Network ports, buffer sizes, FreeRTOS priorities
    │   └── board_pins.h         # GPIO definitions (LEDs, buttons, relays; NO MIC)
    │
    ├── audio/
    │   ├── audio_transport/     # Abstract transport + UDP implementation
    │   │   ├── audio_packet.h   # Universal audio protocol packet struct
    │   │   ├── audio_transport.h
    │   │   └── udp_audio_transport.h / .cpp
    │   ├── audio_buffer/        # Circular audio ring buffer (PSRAM supported)
    │   │   └── audio_ring_buffer.h / .cpp
    │   ├── vad/                 # Adaptive energy-based Voice Activity Detection
    │   │   ├── vad_interface.h
    │   │   └── energy_vad.h / .cpp
    │   ├── asr/                 # Replaceable Vietnamese ASR abstraction + DummyASR
    │   │   ├── asr_engine.h
    │   │   └── dummy_asr.h / .cpp
    │   ├── audio_manager/       # Multi-stream arbitrator & ASR feeder
    │   │   └── audio_manager.h / .cpp
    │   └── audio_output/        # Targeted downlink router to ActionBox speakers
    │       └── audio_output_router.h / .cpp
    │
    ├── nlu/
    │   ├── normalizer/          # Vietnamese diacritics & text cleaner
    │   │   └── vietnamese_normalizer.h / .cpp
    │   ├── intent/              # Deterministic intent parser & complex detector
    │   │   ├── intent_types.h
    │   │   └── intent_parser.h / .cpp
    │   ├── entity/              # Device, Room, Value extraction
    │   │   ├── entity_types.h
    │   │   └── entity_extractor.h / .cpp
    │   └── context/             # Speaker vs Target room, pronoun resolution ("nó")
    │       └── context_manager.h / .cpp
    │
    ├── actionbox/
    │   ├── registry/            # ActionBox node status, capabilities & telemetry
    │   │   └── actionbox_registry.h / .cpp
    │   ├── protocol/            # JSON command serializer
    │   │   └── actionbox_network_protocol.h
    │   └── router/              # Command execution (Local, Cross-Room, Pi4)
    │       └── command_router.h / .cpp
    │
    ├── room/                    # Local room identity & configuration
    │   └── room_manager.h / .cpp
    ├── rules/                   # Edge rule engine (overcurrent, thermal thresholds)
    │   └── rule_engine.h / .cpp
    ├── tts/                     # TTS interface, chime generator & Pi4 audio relay
    │   ├── tts_engine.h
    │   └── tts_manager.h / .cpp
    ├── mqtt/                    # ESP-IDF MQTT client for Pi4 integration
    │   └── mqtt_client.h / .cpp
    ├── storage/                 # NVS persistent configuration
    │   └── nvs_manager.h / .cpp
    └── system/                  # FreeRTOS Task Manager & Interactive Dev Console
        ├── task_manager.h / .cpp
        └── dev_console.h / .cpp
```

---

## 3. Audio & Data Pipeline

```
 [ActionBox Mic]
       │ (16kHz, 16-bit Mono PCM, 20ms frames)
       ▼ UDP:5005
 [audio_rx_task]
       │
       ▼
 [audio_mgr_task] ──> [energy_vad per node] ──> Best Source Selection
       │
       ▼ (Active Speech Frames)
 [asr_task] ──> ASREngine (DummyASR / TinyML Vietnamese ASR)
       │
       ▼ (Recognized Vietnamese Text)
 [nlu_task]
       ├── Vietnamese Normalizer (lowercase, tone marks, synonym collapse)
       ├── Intent Parser (TURN_ON, TURN_OFF, TOGGLE, SET_TEMPERATURE, COMPLEX)
       ├── Entity Extractor (Device: LIGHT, FAN; Room: BEDROOM; Values: 26°C)
       └── Context Manager (Speaker Room vs Target Room; pronoun "nó" resolution)
       │
       ▼
 [cmd_router_task]
       ├── Local Room ActionBox? ─────────> Dispatch UDP command to ActionBox relay
       ├── Other Room SubBox?    ─────────> Dispatch via Inter-SubBox MQTT
       └── Complex Sentence?     ─────────> Forward to Pi4 (`home/subbox/ID/voice/request`)
       │
       ▼
 [tts_manager] ──> Audio Output Router ──> UDP:5006 ──> [Target ActionBox Speaker]
```

---

## 4. FreeRTOS Task & Core Architecture

| Task Name | Core | Priority | Stack (Bytes) | Role |
| :--- | :---: | :---: | :---: | :--- |
| `audio_rx_task` | 1 | 9 | 4,096 | High-speed UDP receiver for incoming microphone packets |
| `audio_mgr_task`| 1 | 8 | 4,096 | Multi-stream tracking, VAD processing, arbitrator |
| `vad_task`      | 1 | 7 | 4,096 | Frame-level energy calculation & onset/offset tracking |
| `asr_task`      | 1 | 6 | 8,192 | Speech-to-text inference (INT8 PSRAM model or Dummy) |
| `nlu_task`      | 0 | 5 | 6,144 | UTF-8 normalization, intent parsing, entity/context resolution |
| `cmd_router_task`| 0 | 5 | 4,096 | Command routing, safety check, rule evaluation |
| `audio_tx_task` | 1 | 8 | 4,096 | Transmits audio feedback/chimes to target ActionBox speaker |
| `mqtt_task`     | 0 | 4 | 6,144 | Bi-directional communication with Raspberry Pi 4 |
| `telemetry_task`| 0 | 2 | 3,072 | Node heartbeat, registry health & current watchdog |
| `dev_cli_task`  | 0 | 3 | 4,096 | UART/USB-JTAG interactive development console |

---

## 5. Development Console (CLI)

The firmware includes an interactive CLI over Native USB Serial / UART at 115200 baud for testing the complete pipeline without hardware audio:

### Commands:

1. **`CMD <text>`**: Directly injects a command into the NLU pipeline:
   ```bash
   CMD bật đèn phòng ngủ
   CMD tắt quạt
   CMD tắt nó
   CMD nếu nhiệt độ trên 30 độ thì bật quạt
   ```
2. **`SAY <text>`**: Simulates an ASR recognition event:
   ```bash
   SAY bật đèn
   SAY tăng nhiệt độ điều hòa phòng khách
   ```
3. **`TEST_NLU`**: Executes the comprehensive built-in unit test suite verifying:
   - Simple local commands (`bật đèn` -> local room light ON)
   - Cross-room commands (`bật đèn phòng bếp` -> kitchen light ON)
   - Device aliases (`máy lạnh` -> `AIR_CONDITIONER`)
   - Context reference resolution (`tắt nó` after `bật quạt` -> turn off fan)
   - Complex conditional sentences (`nếu trời mưa...` -> forwarded to Pi4)
4. **`STATUS`**: Dumps system uptime, free internal RAM, free PSRAM, Wi-Fi status, and registered ActionBoxes.
5. **`REG <id> <room> <device>`**: Manually registers an ActionBox for test routing:
   ```bash
   REG AB001 BEDROOM LIGHT
   ```
6. **`TOPIC <payload>`**: Publishes an event to Pi4 MQTT broker.

---

## 6. MQTT Topics (Raspberry Pi 4 Integration)

| Topic | Direction | Payload Example / Description |
| :--- | :---: | :--- |
| `home/subbox/{id}/state` | SubBox $\rightarrow$ Pi4 | `{"status":"online","room":"BEDROOM","free_heap":...}` |
| `home/subbox/{id}/event` | SubBox $\rightarrow$ Pi4 | `{"event":"overcurrent_trip","node":"AB001","current":16.2}` |
| `home/subbox/{id}/command` | Pi4 $\rightarrow$ SubBox | External commands issued by Home Assistant or Pi4 |
| `home/subbox/{id}/voice/request` | SubBox $\rightarrow$ Pi4 | Forwarded complex intents requiring LLM / reasoning |
| `home/subbox/{id}/voice/response` | Pi4 $\rightarrow$ SubBox | Pi4 response text / synthesized TTS audio metadata |

---

## 7. Build and Flash Instructions

### Prerequisites:
- **ESP-IDF v6.0.2** or **ESP-IDF v5.5** installed.
- Target hardware: ESP32-S3 (WROOM-1 / WROOM-2 N16R8 / N16R2).

### Option A: Using PowerShell Scripts (ESP-IDF 6.0.2)
```powershell
cd Firmware/firmware_esp/SubBox

# 1. Clean & Build
.\build.ps1 -Clean

# 2. Flash to COM port & open Monitor (default COM9)
.\flash.ps1 -Port COM9
```

### Option B: Using Native ESP-IDF CLI
```bash
idf.py set-target esp32s3
idf.py build
idf.py -p COM9 flash monitor
```

### Option C: Using PlatformIO
```bash
pio run -e esp32s3_subbox
pio run -e esp32s3_subbox -t upload --upload-port COM9
pio device monitor -b 115200
```
