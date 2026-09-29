# ActionBox Firmware — ESP32-S3 Smart-Home Actuator Node

Production-grade embedded C++ firmware for the **ActionBox** actuator node running on ESP32-S3, ESP-IDF 6.0.2 / FreeRTOS, and PlatformIO.

---

## 1. Hardware Role & Philosophy

The ActionBox is a low-level, high-reliability actuator and sensor node.

* **It is NOT an AI device.**
* **It does NOT run an LLM.**
* **It does NOT perform speech recognition or audio capture.**
* **It does NOT interpret natural language or execute high-level automations.**

### Primary Responsibilities:
1. **Relay Control**: Safely drives 2 isolated relay channels (monostable or magnetic-latching).
2. **Current & Power Sensing**: Interrogates dual Belling BL0942 energy measurement ICs over UART.
3. **Physical Buttons**: Debounces local push buttons with short-press toggle and long-press reset.
4. **State Reporting & Idempotency**: Reports channel states and telemetries via a cached idempotent JSON protocol.
5. **Safety Supervisor**: Autonomous, local overcurrent cutoff and fault isolation without network dependency.
6. **Robust Network Resilience**: Communicates primarily with its assigned SubBox over ESP-NOW, continuing 100% full local operation when network or SubBox is offline.

---

## 2. Hardware Pinout (`IoT_Board.kicad_sch`)

Directly traced from schematic `D:\Downloads\IoT_Board.kicad_sch`:

| Function | Schematic Net | ESP32-S3 GPIO | Electrical Interface | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Relay Channel 1** | `RL1` | **GPIO 4** | Optocoupler PC817 (U5) | Relay 1 (K1) drive |
| **Relay Channel 2** | `RL2` | **GPIO 5** | Optocoupler PC817 (U6) | Relay 2 (K2) drive |
| **Button Channel 1**| `BUT1` | **GPIO 1** | Internal Pull-Up to 3.3V | Local Push Button 1 |
| **Button Channel 2**| `BUT2` | **GPIO 3** | Internal Pull-Up to 3.3V | Local Push Button 2 |
| **Status LED 1** | `LED1` | **GPIO 48** | Series Resistor to GND | Channel 1 Indicator LED |
| **Status LED 2** | `LED2` | **GPIO 47** | Series Resistor to GND | Channel 2 Indicator LED |
| **BL0942 TX** | `BL_TX` | **GPIO 9** | UART TX (Shared) | Broadcast query to BL0942 #1 & #2 |
| **BL0942 RX Ch1** | `BL_RX1` | **GPIO 10** | UART1 RX | Ch1 BL0942 (#1) Response Stream |
| **BL0942 RX Ch2** | `BL_RX2` | **GPIO 11** | UART2 RX | Ch2 BL0942 (#2) Response Stream |
| **Speaker SD (Mute)**| `SP_SD` | **GPIO 2** | Hardware Shutdown Pin | **Cố định mức LOW** -> Tắt hẳn IC MAX98357 |
| **Speaker I2S (BCLK/LRC/DOUT)**| `SP_*` | **GPIO 17, 18, 21**| I2S Tri-state Pull-down | Chân âm thanh đặt ở trạng thái cô lập, tiêu thụ 0W |
| **USB D-** | `USB_D-` | **GPIO 19** | Native USB | USB Serial / JTAG Console |
| **USB D+** | `USB_D+` | **GPIO 20** | Native USB | USB Serial / JTAG Console |
| **Debug TX0** | `TX0` | **GPIO 43** | UART0 TX | Hardware Debug Terminal |
| **Debug RX0** | `RX0` | **GPIO 44** | UART0 RX | Hardware Debug Terminal |

---

## 3. Project Architecture

```
ActionBox/
├── platformio.ini                 # PlatformIO configuration (esp32-s3-devkitc-1, 16MB)
├── CMakeLists.txt                 # ESP-IDF Root Project CMake
├── partitions.csv                 # 16MB Partition Table (nvs, otadata, ota_0, ota_1)
├── sdkconfig.defaults             # Hardware configuration defaults
├── src/
│   ├── CMakeLists.txt             # Component registration & dependency mapping
│   ├── main.cpp                   # Application entry point & banner
│   ├── config/
│   │   ├── board_pins.h           # Hardware GPIO mapping from schematic
│   │   └── app_config.h           # Timing, limits, queue capacities & task priorities
│   ├── drivers/
│   │   ├── relay/
│   │   │   ├── relay_driver.h     # Relay driver interface (monostable & latching)
│   │   │   └── relay_driver.cpp   # Staggered inrush delay & thread-safe actuation
│   │   ├── current_sensor/
│   │   │   ├── current_sensor.h   # Abstract current measurement interface
│   │   │   ├── bl0942.h           # BL0942 driver header
│   │   │   └── bl0942.cpp         # Dual-UART BL0942 parsing & calibration
│   │   ├── button/
│   │   │   ├── button_driver.h    # Button driver header
│   │   │   └── button_driver.cpp  # Non-blocking debounce & long-press detection
│   │   └── led/
│   │       ├── led_driver.h       # Status LED pattern header
│   │       └── led_driver.cpp     # Visual pattern generator (steady, blink, pulse)
│   ├── protocol/
│   │   ├── actionbox_protocol.h   # JSON schema, commands & responses
│   │   └── actionbox_protocol.cpp # cJSON parsing & 32-entry idempotency cache
│   ├── network/
│   │   ├── espnow_transport.h     # ESP-NOW transport header
│   │   └── espnow_transport.cpp   # Station Wi-Fi & unicast/broadcast transport
│   ├── device/
│   │   ├── device_manager.h       # Coordinator header
│   │   └── device_manager.cpp     # Command dispatch, button events & LED sync
│   ├── safety/
│   │   ├── safety_supervisor.h    # Safety supervisor header
│   │   └── safety_supervisor.cpp  # Local overcurrent trip & TWDT watchdog
│   ├── storage/
│   │   ├── nvs_storage.h          # NVS persistent configuration header
│   │   └── nvs_storage.cpp        # Flash-wear-protected NVS storage
│   └── system/
│       ├── task_manager.h         # FreeRTOS task & queue definitions
│       └── task_manager.cpp       # Core task loops & queue orchestration
└── tools/
    └── test_actionbox.py          # Python test CLI & automated verification suite
```

---

## 4. FreeRTOS Task Architecture

The ActionBox organizes its concurrency into discrete FreeRTOS tasks communicating via queues and semaphores:

| Task Name | Priority | Stack | Function |
| :--- | :--- | :--- | :--- |
| `safety_task` | `MAX-1` (Highest) | 4 KB | Blocks on sensor queue. Evaluates overcurrent limits instantly; trips relays and dispatches urgent alerts. Feeds TWDT. |
| `relay_task` | `MAX-2` | 4 KB | Consumes command queue; manages inrush stagger delay and coil pulse timing. |
| `button_task` | `MAX-3` | 3 KB | Ticks button state machine every 10ms for non-blocking debounce and long-press gestures. |
| `sensor_task` | `MAX-4` | 4 KB | Interrogates dual BL0942 UART channels every 100ms; posts valid measurements to `sensor_queue`. |
| `network_task`| `MAX-5` | 5 KB | Processes incoming ESP-NOW packets from SubBox, validates idempotency cache, dispatches commands, and sends responses. |
| `telemetry_task`| `IDLE+2` | 3 KB | Broadcasts periodic JSON telemetry every 1000ms; monitors SubBox heartbeat timeout; ticks LED animations. |

---

## 5. Relay Control & Magnetic Latching

* **Monostable Mode** (`BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_MONOSTABLE`):
  * Continuous HIGH energizes optocoupler (Relay Closed/ON).
  * Continuous LOW de-energizes optocoupler (Relay Open/OFF).
* **Magnetic Latching Mode** (`BOARD_RELAY_DRIVE_TYPE == BOARD_RELAY_TYPE_LATCHING_DUAL`):
  * `SET` pulse (50ms) closes contact, then releases coil to 0 immediately.
  * `RESET` pulse (50ms) opens contact, then releases coil to 0 immediately.
  * **Never holds coil continuously energized**, eliminating thermal dissipation and saving power.

---

## 6. Safety & Overcurrent Protection

* **Autonomous Protection**: Runs locally in `safety_task`. Does **not** rely on SubBox, Wi-Fi, or Raspberry Pi.
* **Overcurrent Trip**:
  * Default threshold: `10000 mA` (10A RMS).
  * Inrush Debounce: Must persist > `300 ms` to prevent false tripping on capacitive/motor inrush.
  * Hard Ceiling Trip: Instantaneous cutoff if current exceeds `16000 mA` (16A).
* **Post-Trip Isolation**:
  * Relay is forced OFF immediately.
  * Channel is locked in `RELAY_FAULT_OVERCURRENT`.
  * Status LED blinks rapidly (5 Hz).
  * Urgent alert packet is sent to SubBox.
  * **No automatic re-engagement** is permitted until an explicit `CLEAR_FAULT` command is issued.

---

## 7. Communication Protocol

### Command Format (SubBox -> ActionBox)
```json
{
  "version": 1,
  "node_id": "AB001",
  "request_id": 1042,
  "cmd": "TURN_ON",
  "channel": 1,
  "timestamp": 1727400000
}
```

### Response Format (ActionBox -> SubBox)
```json
{
  "version": 1,
  "node_id": "AB001",
  "request_id": 1042,
  "status": "OK",
  "channel": 1,
  "state": "ON",
  "uptime_s": 42
}
```

### Supported Commands
* `TURN_ON`: Turn on relay for specified channel (1 or 2).
* `TURN_OFF`: Turn off relay for specified channel.
* `TOGGLE`: Toggle relay state.
* `GET_STATE`: Query relay contact and fault state.
* `GET_CURRENT`: Query instantaneous RMS current and voltage from BL0942.
* `GET_POWER`: Query active power (W) and accumulated energy (Wh).
* `CLEAR_FAULT`: Clears an active safety fault and re-enables channel control.
* `PING`: Heartbeat probe (replies with `state: "PONG"`).
* `SET_CONFIG`: Remotely update `node_id`, `room_id`, or `max_current_ma`.

### Idempotency
A 32-entry ring buffer tracks recent `request_id`s and their exact serialized response. If the SubBox re-transmits a command due to packet loss, the ActionBox returns the cached response without re-triggering relays or double-toggling.

---

## 8. Build, Flash & Monitor Instructions

### Option A: Using ESP-IDF 6.0.2 (Native PowerShell)

Activate the ESP-IDF 6.0.2 environment:
```powershell
& 'C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1'
```

Navigate to the project root:
```powershell
cd d:\Home-Assistant-IoT-\Firmware\firmware_esp\ActionBox
```

Build:
```powershell
idf.py build
```

Flash (e.g. on `COM8`):
```powershell
idf.py -p COM8 flash
```

Monitor:
```powershell
idf.py -p COM8 monitor
```

*(Or simply use the included one-click helper scripts `./build.ps1` and `./flash.ps1`)*

### Option B: Using PlatformIO

Build:
```bash
pio run
```

Upload:
```bash
pio run --target upload --upload-port COM8
```

Monitor:
```bash
pio device monitor --port COM8 --baud 115200
```

---

## 9. Testing & Automated Verification

A complete Python test suite is provided in `tools/test_actionbox.py`.

Run the automated verification suite over Serial:
```bash
python tools/test_actionbox.py --port COM8 --test
```

Send individual commands:
```bash
# Toggle Relay 1
python tools/test_actionbox.py --port COM8 --cmd TOGGLE --ch 1

# Query Current
python tools/test_actionbox.py --port COM8 --cmd GET_CURRENT --ch 1

# Clear Fault
python tools/test_actionbox.py --port COM8 --cmd CLEAR_FAULT --ch 1
```
