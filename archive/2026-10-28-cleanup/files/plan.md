# 🏠 DTV Smart Home — Bản Kế Hoạch Tổng Thể

---

> ## 🎯 MỤC TIÊU CỐT LÕI (NORTH STAR — đọc lại trước mỗi quyết định)
>
> **"Xây dựng hệ thống nhà thông minh TỰ HÀNH & NHẬN THỨC (Cognitive & Proactive Autonomous Smart Home), lấy dữ liệu điện năng làm PHẢN HỒI VÒNG KÍN (closed-loop) để TỰ HỌC thói quen người dùng và CHỦ ĐỘNG điều khiển, gợi ý, nhắc nhở."**
>
> Mọi dòng code, mọi quyết định kiến trúc, mọi tính năng **phải phục vụ** mục tiêu này.
> Nếu một tính năng không giúp hệ thống: (1) hiểu người dùng hơn, (2) tự động hơn, hoặc (3) an toàn hơn — thì **KHÔNG LÀM**.

---

## 📋 Mục Lục

1. [Tổng Quan Kiến Trúc](#1-tổng-quan-kiến-trúc)
2. [Hiện Trạng Dự Án](#2-hiện-trạng-dự-án)
3. [Phase 0 — Foundation (Nền Tảng)](#phase-0--foundation-nền-tảng)
4. [Phase 1 — Voice Pipeline (Giọng Nói → Lệnh)](#phase-1--voice-pipeline-giọng-nói--lệnh)
5. [Phase 2 — Closed-Loop Control (Vòng Kín Điều Khiển)](#phase-2--closed-loop-control-vòng-kín-điều-khiển)
6. [Phase 3 — Memory & Learning (Bộ Nhớ & Tự Học)](#phase-3--memory--learning-bộ-nhớ--tự-học)
7. [Phase 4 — Proactive Intelligence (Trí Tuệ Chủ Động)](#phase-4--proactive-intelligence-trí-tuệ-chủ-động)
8. [Phase 5 — MCP Integration & Ecosystem](#phase-5--mcp-integration--ecosystem)
9. [Phase 6 — Dashboard & User Experience](#phase-6--dashboard--user-experience)
10. [Verification & Testing Strategy](#verification--testing-strategy)
11. [Rủi Ro & Giải Pháp](#rủi-ro--giải-pháp)
12. [Timeline Dự Kiến](#timeline-dự-kiến)

---

## 1. Tổng Quan Kiến Trúc

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        COGNITIVE SMART HOME                           │
│                                                                       │
│  ┌─────────────┐    WebSocket     ┌──────────────────────────────┐    │
│  │  ESP32-S3    │◄──────────────►│    Raspberry Pi 4 (Brain)     │    │
│  │  Voice Node  │   Opus/PCM      │                              │    │
│  │  ┌─────────┐ │                 │  ┌────────┐  ┌────────────┐  │    │
│  │  │INMP441  │ │                 │  │SherpaON│  │ Qwen2.5    │  │    │
│  │  │ Mic     │ │    MQTT         │  │  ASR   │──│ 1.5B LLM   │  │    │
│  │  └─────────┘ │◄──────────────►│  └────────┘  └─────┬──────┘  │    │
│  │  ┌─────────┐ │                 │                    │         │    │
│  │  │MAX98357 │ │                 │  ┌────────────┐    ▼         │    │
│  │  │ Speaker │ │◄───────────────│  │  EdgeTTS   │  ┌────────┐  │    │
│  │  └─────────┘ │   Opus/PCM      │  │  (Output)  │  │Gateway │  │    │
│  │  ┌─────────┐ │                 │  └────────────┘  │Python  │  │    │
│  │  │WakeNet  │ │                 │                   └───┬────┘  │    │
│  │  │"Hi ESP" │ │                 │                       │      │    │
│  │  └─────────┘ │                 │              ┌────────▼────┐ │    │
│  └──────┬───────┘                 │              │   EMQX      │ │    │
│         │ ESP-NOW                  │              │   Broker    │ │    │
│  ┌──────▼───────┐                 │              └─────┬───────┘ │    │
│  │  ESP32       │                 │  ┌─────────────────▼───────┐ │    │
│  │  WROOM       │                 │  │ InfluxDB  │ Grafana    │ │    │
│  │  Relay Node  │                 │  │ Telemetry │ Dashboard  │ │    │
│  │  ┌─────────┐ │                 │  └───────────┴────────────┘ │    │
│  │  │PZEM-004T│ │                 │  ┌────────────────────────┐ │    │
│  │  │ Sensor  │ │                 │  │ Home Assistant + MCP   │ │    │
│  │  └─────────┘ │                 │  └────────────────────────┘ │    │
│  │  ┌─────────┐ │                 │  ┌────────────────────────┐ │    │
│  │  │ 2-CH    │ │                 │  │ Memory Engine          │ │    │
│  │  │ Relay   │ │                 │  │ (SQLite + Patterns)    │ │    │
│  │  └─────────┘ │                 │  └────────────────────────┘ │    │
│  └──────────────┘                 └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Phân Tầng Hệ Thống (Layered Architecture)

| Tầng | Tên | Trách Nhiệm | Thiết Bị |
|------|-----|-------------|----------|
| **L0** | Hardware | Relay, Sensor, Mic, Speaker | ESP32-S3 N16R8, ESP32 WROOM |
| **L1** | Communication | ESP-NOW, MQTT, WebSocket | EMQX Broker |
| **L2** | Perception | ASR, VAD, Intent Extraction | Sherpa-ONNX, Qwen LLM |
| **L3** | Decision | Command Dispatch, Validation | Gateway Python |
| **L4** | Memory | Telemetry Storage, User Profile | InfluxDB, SQLite |
| **L5** | Intelligence | Pattern Learning, Proactive Actions | Cron + Qwen Analysis |
| **L6** | Interface | Voice Output, Dashboard, MCP | EdgeTTS, Grafana, HA |

---

## 2. Hiện Trạng Dự Án

### ✅ Đã Hoàn Thành

| Hạng mục | Chi tiết | Trạng thái |
|----------|----------|------------|
| **Pi 4 Infrastructure** | Ubuntu Lite, Docker (EMQX, InfluxDB, Grafana, HA) | ✅ Running |
| **LLM Engine** | `llama-server` + `Qwen2.5-1.5B-Instruct-Q4_K_M` @ 127.0.0.1:8080 | ✅ Validated |
| **Intent Extraction** | `cli_json.sh` — Prompt tối ưu cho Area/Device/Action schema | ✅ Tested |
| **ESP32-S3 Firmware** | I2S Mic (INMP441), Speaker (MAX98357A), WakeNet "Hi ESP", ESP-NOW, TinyML | ✅ Compiled |
| **ESP32 WROOM Slave** | PZEM-004T sensor, 2-CH Relay, ESP-NOW telemetry | ✅ Working |
| **Python venv** | `/home/pi4/voice_gateway_venv` | ✅ Created |

### 🔲 Chưa Triển Khai

| Hạng mục | Ưu tiên |
|----------|---------|
| WebSocket Audio Streaming (ESP32 → Pi) | 🔴 Critical |
| Opus Codec (Nén/Giải nén) | 🔴 Critical |
| SherpaONNX ASR (Speech-to-Text) | 🔴 Critical |
| Gateway Python (Orchestrator) | 🔴 Critical |
| EdgeTTS (Text-to-Speech) | 🟡 High |
| Device Registry (Dynamic Registration) | 🟡 High |
| Closed-Loop Verification | 🟡 High |
| Memory Engine (User Profile) | 🟠 Medium |
| Proactive Intelligence | 🟠 Medium |
| MCP Server Integration | 🟢 Later |
| Dashboard Polish | 🟢 Later |

---

## Phase 0 — Foundation (Nền Tảng)

> **🎯 Checkpoint:** Phase này phục vụ mục tiêu cốt lõi bằng cách tạo HẠNG MỤC LIÊN LẠC CHUNG (communication backbone) giữa tất cả các thành phần — không có nền tảng thì không có gì tự hành được.

### 0.1 Device Registry — Đăng Ký Thiết Bị Động

**Vấn đề:** Khi thêm 1 ESP32 Node mới, server phải biết node đó ở đâu, điều khiển thiết bị gì.

**Giải pháp:** File `device_registry.json` trên Pi — mỗi node tự đăng ký khi boot qua MQTT.

```json
{
  "nodes": {
    "esp32_wroom_01": {
      "mac": "AA:BB:CC:DD:EE:01",
      "area": "phong_ngu_master",
      "description": "Node phòng ngủ chính",
      "channels": {
        "ch1": {
          "device_type": "den_ngu",
          "description": "Đèn ngủ đầu giường",
          "rated_watts": 7,
          "gpio": 26
        },
        "ch2": {
          "device_type": "den_tran",
          "description": "Đèn trần chiếu sáng",
          "rated_watts": 40,
          "gpio": 27
        }
      },
      "sensors": {
        "pzem": true,
        "temperature": false
      },
      "registered_at": "2026-09-10T00:00:00+07:00",
      "last_seen": "2026-09-10T01:00:00+07:00",
      "status": "online"
    }
  }
}
```

**Cách đăng ký Node mới:**

1. Flash firmware chuẩn lên ESP32 WROOM mới
2. Node boot → Gửi MQTT message tới topic `smarthome/register`
3. Gateway nhận → Tạo entry trong registry (status = `pending`)
4. User qua Dashboard/Voice: _"Node mới ở ban công, ổ 1 là đèn ban công, ổ 2 là quạt hút"_
5. Gateway cập nhật registry → Node chuyển `online`

**Files cần tạo:**

```
/home/pi4/smarthome/
├── device_registry.json          # Registry dữ liệu
├── gateway/
│   ├── registry_manager.py       # CRUD cho registry
│   ├── mqtt_handler.py           # MQTT subscribe/publish
│   └── config.py                 # MQTT/LLM/TTS config
```

### 0.2 MQTT Topic Convention

```
smarthome/
├── register                      # Node đăng ký: {"mac":"...", "channels":{...}}
├── telemetry/{node_id}           # Dữ liệu PZEM real-time
│   └── {"voltage":220, "current":0.5, "power":110, ...}
├── command/{node_id}             # Lệnh điều khiển từ Gateway
│   └── {"channel":"ch1", "action":"turn_on"}
├── status/{node_id}              # Node heartbeat + relay state
│   └── {"online":true, "ch1":1, "ch2":0, "uptime_s":3600}
├── voice/audio_stream            # (Reserved) Raw audio chunks
├── voice/intent                  # Kết quả intent extraction
│   └── {"action":"turn_on", "device":"den_ngu", ...}
└── alert                         # Hệ thống cảnh báo
    └── {"type":"anomaly", "node":"esp32_wroom_01", ...}
```

### 0.3 ESP32 WROOM Firmware Chuẩn Hóa

Cập nhật firmware WROOM Slave để hỗ trợ:

- [x] PZEM-004T đọc liên tục (đã có)
- [x] ESP-NOW gửi telemetry (đã có)
- [ ] **MỚI:** Kết nối Wi-Fi + MQTT client song song với ESP-NOW
- [ ] **MỚI:** Gửi telemetry qua MQTT topic `smarthome/telemetry/{node_id}` (mỗi 2 giây)
- [ ] **MỚI:** Subscribe `smarthome/command/{node_id}` để nhận lệnh relay
- [ ] **MỚI:** Tự đăng ký qua `smarthome/register` khi boot
- [ ] **MỚI:** Heartbeat `smarthome/status/{node_id}` mỗi 30 giây

**Lý do chuyển sang MQTT thay vì chỉ ESP-NOW:**
- ESP-NOW giới hạn 250 bytes/packet, không reliable
- MQTT qua Wi-Fi: reliable, buffered, QoS, dễ scale
- ESP-NOW vẫn giữ làm **fallback** khi Wi-Fi mất

---

## Phase 1 — Voice Pipeline (Giọng Nói → Lệnh)

> **🎯 Checkpoint:** Phase này phục vụ mục tiêu cốt lõi bằng cách tạo KÊNH GIAO TIẾP TỰ NHIÊN — user nói bằng giọng nói, hệ thống hiểu và thực thi. Đây là điều kiện tiên quyết để hệ thống "nhận thức".

### 1.1 Audio Streaming: ESP32-S3 → Pi 4 (WebSocket + Opus)

**Flow:**

```
[INMP441 Mic] → [I2S 16kHz/16bit] → [Opus Encode] → [WebSocket] → [Pi 4]
```

**ESP32-S3 Side (Firmware Modification):**

```c
// Thêm vào main.c sau khi WakeNet detected:
// 1. Kết nối WebSocket tới ws://192.168.11.29:8765/audio
// 2. Encode PCM chunks bằng Opus (bitrate: 16kbps, frame: 20ms)
// 3. Gửi Opus frames qua WebSocket
// 4. Khi VAD phát hiện im lặng > 1.5s → Ngắt stream, gửi END marker
```

**Thư viện cần:**
- ESP-IDF: `esp_websocket_client` (có sẵn trong ESP-IDF 5.x)
- Opus: `libopus` ported cho ESP32 (dùng `opus-1.4` compiled for Xtensa)

**Chi tiết kỹ thuật Opus trên ESP32-S3:**

| Thông số | Giá trị | Lý do |
|----------|---------|-------|
| Sample Rate | 16000 Hz | ASR standard |
| Channels | 1 (Mono) | Mic INMP441 đơn |
| Frame Size | 320 samples (20ms) | Opus standard frame |
| Bitrate | 16 kbps | Cân bằng chất lượng/bandwidth |
| Complexity | 0-2 | ESP32 CPU limited |
| Application | OPUS_APPLICATION_VOIP | Tối ưu cho giọng nói |

**Bandwidth tính toán:**
- PCM raw: 16000 × 16bit × 1ch = 256 kbps
- Opus 16kbps: **giảm 16x** → phù hợp Wi-Fi nội bộ

### 1.2 Pi 4 — WebSocket Audio Server

```python
# /home/pi4/smarthome/gateway/audio_server.py

# WebSocket server tại ws://0.0.0.0:8765/audio
# Flow:
# 1. Nhận Opus frames từ ESP32-S3
# 2. Decode Opus → PCM 16kHz/16bit
# 3. Chạy VAD (Silero VAD hoặc WebRTC VAD) để phát hiện câu nói hoàn chỉnh
# 4. Khi VAD phát hiện end-of-speech:
#    a. Buffer PCM → Gửi tới Sherpa-ONNX ASR
#    b. Nhận text → Gửi tới LLM Intent Extraction
#    c. Nhận JSON intent → Dispatch command qua MQTT
#    d. Generate voice reply qua EdgeTTS
#    e. Encode reply TTS audio → Opus → Gửi về ESP32-S3 qua WebSocket
```

### 1.3 Sherpa-ONNX ASR (Speech-to-Text Vietnamese)

**Model lựa chọn:** `sherpa-onnx-streaming-zipformer-ctc-small-2024-03-18` (Vietnamese)

**Cài đặt trên Pi 4:**

```bash
# Trong venv
pip install sherpa-onnx

# Download Vietnamese model
cd /home/pi4/smarthome/models/
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-ctc-small-2024-03-18.tar.bz2
tar xf sherpa-onnx-streaming-zipformer-ctc-small-2024-03-18.tar.bz2
```

**Tích hợp:**

```python
# /home/pi4/smarthome/gateway/asr_engine.py

import sherpa_onnx

def create_recognizer():
    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens="models/tokens.txt",
        encoder="models/encoder.onnx",
        decoder="models/decoder.onnx",
        joiner="models/joiner.onnx",
        num_threads=2,           # Pi 4 có 4 cores, dành 2 cho ASR
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
    )
```

**Latency mục tiêu:** < 500ms cho câu 3-5 giây

### 1.4 LLM Intent Extraction (Qwen2.5-1.5B)

**Đã có prompt tối ưu** từ `cli_json.sh`. Tích hợp thành Python module:

```python
# /home/pi4/smarthome/gateway/intent_engine.py

import httpx
import json

LLAMA_URL = "http://127.0.0.1:8080/completion"

SYSTEM_PROMPT = """Bạn là bộ phân tích lệnh cho Nhà Thông Minh IoT.
Nhiệm vụ: Phân tích khẩu lệnh thành JSON.
... (prompt đã test ổn định)
"""

async def extract_intent(user_text: str) -> dict:
    """
    Input:  "Bật đèn ngủ phòng ngủ"
    Output: {"voice_reply":"Đã bật đèn ngủ phòng ngủ ạ",
             "command":{"action":"turn_on","device":"den_ngu","location":"phong_ngu"}}
    """
    payload = {
        "prompt": f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
                  f"<|im_start|>user\n{user_text}<|im_end|>\n"
                  f"<|im_start|>assistant\n",
        "n_predict": 200,
        "temperature": 0.1,
        "stop": ["<|im_end|>"],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(LLAMA_URL, json=payload, timeout=15.0)
        return json.loads(resp.json()["content"])
```

**Latency mục tiêu:** < 3 giây (đã benchmark ~3.5 t/s generation)

### 1.5 EdgeTTS — Text-to-Speech Output

```python
# /home/pi4/smarthome/gateway/tts_engine.py

import edge_tts
import asyncio

VOICE = "vi-VN-HoaiMyNeural"  # Giọng nữ Việt Nam tự nhiên

async def synthesize_speech(text: str) -> bytes:
    """
    Input:  "Đã bật đèn ngủ phòng ngủ ạ"
    Output: PCM audio bytes (16kHz, 16-bit, mono)
    """
    communicate = edge_tts.Communicate(text, VOICE)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    # EdgeTTS trả về MP3 → cần decode sang PCM
    return convert_mp3_to_pcm(audio_bytes)
```

**Cài đặt:** `pip install edge-tts`

**Lưu ý:** EdgeTTS cần Internet (gọi Microsoft Azure). Nếu cần offline → fallback sang `piper-tts`.

### 1.6 Voice Pipeline — Full Flow Tổng Hợp

```
┌──────────────────────────────── FULL VOICE PIPELINE ─────────────────────────────────┐
│                                                                                      │
│  User: "Hi ESP"                                                                      │
│       │                                                                              │
│       ▼                                                                              │
│  [1] WakeNet Detect (ESP32-S3, local, ~0ms)                                          │
│       │                                                                              │
│       ▼                                                                              │
│  [2] I2S Mic → Opus Encode → WebSocket → Pi 4  (~20ms per frame)                     │
│       │                                                                              │
│       ▼                                                                              │
│  [3] Opus Decode → VAD → Buffer until silence (~50ms processing)                     │
│       │                                                                              │
│       ▼                                                                              │
│  [4] Sherpa-ONNX ASR: PCM → Vietnamese Text  (~300-500ms)                            │
│       │                                                                              │
│       ▼                                                                              │
│  [5] Qwen2.5-1.5B: Text → JSON Intent  (~2-4s)                                      │
│       │                                                                              │
│       ├──► [6a] MQTT Publish: command/{node_id} → ESP32 Relay  (~50ms)               │
│       │                                                                              │
│       └──► [6b] EdgeTTS: voice_reply → MP3 → PCM → Opus → WS → ESP32 (~1-2s)        │
│                                                                                      │
│  TỔNG LATENCY MỤC TIÊU: 3-6 giây từ khi nói xong đến khi nghe phản hồi             │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Files cần tạo (Phase 1):**

```
/home/pi4/smarthome/
├── gateway/
│   ├── __init__.py
│   ├── main.py                   # Entry point — asyncio event loop
│   ├── audio_server.py           # WebSocket server cho audio streaming
│   ├── asr_engine.py             # Sherpa-ONNX wrapper
│   ├── intent_engine.py          # LLM intent extraction
│   ├── tts_engine.py             # EdgeTTS wrapper
│   ├── mqtt_handler.py           # MQTT publish/subscribe
│   ├── registry_manager.py       # Device registry CRUD
│   └── config.py                 # Cấu hình tập trung
├── models/
│   └── sherpa-onnx-*/            # ASR model files
├── device_registry.json
└── requirements.txt
```

---

## Phase 2 — Closed-Loop Control (Vòng Kín Điều Khiển)

> **🎯 Checkpoint:** Đây là TRÁI TIM của mục tiêu cốt lõi. Hệ thống không chỉ ra lệnh mà phải KIỂM CHỨNG — lệnh bật đèn gửi rồi, nhưng đèn có thực sự sáng không? Đây chính là "closed-loop" phân biệt hệ thống thông minh với hệ thống ngu.

### 2.1 Verify-After-Command (Xác Nhận Sau Lệnh)

```
[Gateway gửi lệnh "turn_on ch1"] 
    → MQTT → [ESP32 WROOM bật relay ch1]
    → [PZEM-004T đo dòng điện thay đổi]
    → MQTT telemetry → [Gateway so sánh]
    
    Nếu power_delta > ngưỡng (e.g., >5W) → ✅ Xác nhận thành công
    Nếu power_delta ≈ 0 sau 3 giây       → ❌ Thiết bị có vấn đề!
        → Thông báo user qua EdgeTTS: "Đèn ngủ phòng ngủ có vẻ bị hỏng bóng, 
          em đã bật công tắc nhưng không thấy tiêu thụ điện."
```

```python
# /home/pi4/smarthome/gateway/verify_engine.py

class CommandVerifier:
    """
    Sau khi gửi lệnh, chờ telemetry feedback trong 5 giây.
    So sánh power trước/sau để xác nhận thiết bị thực sự hoạt động.
    """
    
    async def verify_command(self, node_id, channel, action, rated_watts):
        # 1. Ghi nhận power hiện tại
        before_power = self.get_current_power(node_id)
        
        # 2. Gửi lệnh
        await self.mqtt.publish(
            f"smarthome/command/{node_id}", 
            {"channel": channel, "action": action}
        )
        
        # 3. Chờ 3 giây, đọc lại telemetry
        await asyncio.sleep(3.0)
        after_power = self.get_current_power(node_id)
        
        # 4. Phân tích
        delta = after_power - before_power
        
        if action == "turn_on":
            if delta > rated_watts * 0.3:  # >30% công suất định mức
                return VerifyResult.SUCCESS
            elif delta > 0:
                return VerifyResult.PARTIAL  # Hoạt động yếu
            else:
                return VerifyResult.FAILED   # Không phản hồi
        elif action == "turn_off":
            if delta < -rated_watts * 0.3:
                return VerifyResult.SUCCESS
            else:
                return VerifyResult.FAILED
```

### 2.2 Anomaly Detection (Phát Hiện Bất Thường)

**Trường hợp bất thường cần phát hiện:**

| # | Tình huống | Cách phát hiện | Hành động |
|---|-----------|----------------|-----------|
| 1 | Thiết bị bật không có lệnh | `relay_state` chuyển ON nhưng không có command log | Cảnh báo user |
| 2 | Tiêu thụ vượt mức | `current_power > historical_avg * 1.5` | Cảnh báo + gợi ý tắt |
| 3 | Thiết bị chạy quá lâu | `on_duration > threshold` (e.g., điều hòa >8h) | Nhắc nhở tắt |
| 4 | Mất tín hiệu Node | `last_seen > 60 giây` | Cảnh báo mất kết nối |
| 5 | Dòng rò / Standby | `power > 0` khi tất cả relay OFF | Cảnh báo rò điện |

```python
# /home/pi4/smarthome/gateway/anomaly_engine.py

class AnomalyDetector:
    """
    Chạy liên tục (mỗi 10 giây), quét telemetry từ tất cả nodes.
    So sánh với baseline + command history để phát hiện bất thường.
    """
    
    async def scan(self):
        for node_id, node in self.registry.items():
            telemetry = self.latest_telemetry[node_id]
            
            # Case 1: Unauthorized activation
            if telemetry.relay_on and not self.command_log.has_recent_on(node_id):
                await self.alert("unauthorized_activation", node_id)
            
            # Case 2: Over-consumption
            baseline = self.memory.get_baseline_power(node_id)
            if telemetry.power > baseline * 1.5 and baseline > 10:
                await self.alert("over_consumption", node_id, 
                                 actual=telemetry.power, expected=baseline)
            
            # Case 3: Extended runtime
            on_duration = self.get_on_duration(node_id)
            max_duration = node.get("max_runtime_hours", 8)
            if on_duration > max_duration * 3600:
                await self.alert("extended_runtime", node_id,
                                 hours=on_duration/3600)
```

### 2.3 Telemetry Pipeline

```
[ESP32 WROOM]  ──MQTT──►  [Gateway]  ──write──►  [InfluxDB]
    │                        │                        │
    │ mỗi 2 giây             │ real-time cache        │ historical data
    │                        │                        │
    └── smarthome/           └── verify_engine        └── Grafana Dashboard
        telemetry/               anomaly_engine            (query 7d/30d/1y)
        {node_id}
```

**InfluxDB Schema:**

```
Measurement: device_telemetry
Tags:        node_id, area, device_type, channel
Fields:      voltage, current, power, energy, frequency, pf, relay_state
Timestamp:   nanosecond precision
```

**Files cần tạo (Phase 2):**

```
/home/pi4/smarthome/gateway/
├── verify_engine.py              # Command verification
├── anomaly_engine.py             # Anomaly detection
├── telemetry_writer.py           # InfluxDB writer
└── command_log.py                # Lịch sử lệnh (SQLite)
```

---

## Phase 3 — Memory & Learning (Bộ Nhớ & Tự Học)

> **🎯 Checkpoint:** Phase này biến hệ thống từ "thực thi lệnh" thành "HIỂU NGƯỜI DÙNG". Không có memory thì không có learning. Không có learning thì không bao giờ tự hành được. Đây là bước THEN CHỐT.

### 3.1 Memory Architecture

```python
# /home/pi4/smarthome/gateway/memory_engine.py

"""
Memory Engine gồm 3 tầng:

1. Short-Term Memory (STM) — RAM Cache
   - Telemetry 5 phút gần nhất
   - Context hội thoại hiện tại
   - Trạng thái relay real-time
   
2. Medium-Term Memory (MTM) — SQLite
   - Command history (ai bật gì, khi nào, kết quả verify)
   - Daily usage patterns (giờ bật/tắt từng thiết bị)
   - User corrections ("không, tôi muốn tắt đèn BAN CÔNG, không phải đèn ngủ")
   
3. Long-Term Memory (LTM) — InfluxDB + SQLite
   - Baseline power profiles (trung bình tiêu thụ mỗi thiết bị theo giờ/ngày/mùa)
   - User preference model (thói quen lặp đi lặp lại >5 lần = pattern)
   - Seasonal adjustment (mùa hè dùng điều hòa nhiều hơn)
"""

class MemoryEngine:
    def __init__(self):
        self.stm = ShortTermMemory()     # dict trong RAM
        self.mtm = MediumTermMemory()    # SQLite
        self.ltm = LongTermMemory()      # InfluxDB queries + SQLite
    
    async def record_command(self, intent, verify_result, timestamp):
        """Ghi lại mỗi lệnh + kết quả verification"""
        self.mtm.insert_command_log(
            user_text=intent["user_text"],
            action=intent["action"],
            device=intent["device"],
            area=intent["location"],
            verify_result=verify_result,
            timestamp=timestamp,
            hour=timestamp.hour,
            day_of_week=timestamp.weekday(),
        )
    
    async def record_correction(self, original_intent, corrected_intent):
        """Khi user sửa lệnh sai → ghi nhận để cải thiện prompt"""
        self.mtm.insert_correction(original_intent, corrected_intent)
    
    def get_daily_pattern(self, device, area, day_of_week):
        """Lấy pattern: device X ở area Y thường bật lúc mấy giờ ngày thứ mấy"""
        return self.mtm.query_pattern(device, area, day_of_week)
```

### 3.2 SQLite Schema (Medium-Term Memory)

```sql
-- /home/pi4/smarthome/memory.db

-- Lịch sử lệnh
CREATE TABLE command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    hour INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    user_text TEXT,
    action TEXT NOT NULL,
    device TEXT NOT NULL,
    area TEXT NOT NULL,
    node_id TEXT,
    channel TEXT,
    verify_result TEXT,  -- 'success', 'partial', 'failed'
    power_before REAL,
    power_after REAL
);

-- Sửa lỗi của user (dùng để fine-tune prompt/behavior)
CREATE TABLE user_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    original_text TEXT,
    original_device TEXT,
    original_area TEXT,
    corrected_device TEXT,
    corrected_area TEXT,
    notes TEXT
);

-- Patterns tự học (được tính toán từ command_log)
CREATE TABLE learned_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,  -- 'daily_routine', 'weekday_habit', 'seasonal'
    device TEXT NOT NULL,
    area TEXT NOT NULL,
    action TEXT NOT NULL,
    trigger_hour INTEGER,
    trigger_day_of_week INTEGER,  -- NULL = mỗi ngày
    confidence REAL DEFAULT 0.0,  -- 0.0 ~ 1.0
    occurrence_count INTEGER DEFAULT 0,
    last_occurred TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Baseline điện năng (tính trung bình từ InfluxDB)
CREATE TABLE power_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    device_type TEXT NOT NULL,
    avg_watts REAL,
    max_watts REAL,
    min_watts REAL,
    measurement_count INTEGER,
    last_updated TEXT
);

-- Index tối ưu query
CREATE INDEX idx_cmd_device_area ON command_log(device, area, hour);
CREATE INDEX idx_patterns_active ON learned_patterns(is_active, trigger_hour);
```

### 3.3 Learning Algorithm (Thuật Toán Tự Học)

```python
# /home/pi4/smarthome/gateway/learning_engine.py

class PatternLearner:
    """
    Chạy mỗi ngày lúc 3:00 AM (cron job).
    Phân tích command_log → Tìm patterns lặp lại → Lưu vào learned_patterns.
    
    Quy tắc confidence:
    - Lặp lại >= 5 lần trong 7 ngày liên tiếp  → confidence = 0.7
    - Lặp lại >= 14 lần trong 21 ngày           → confidence = 0.85
    - Lặp lại >= 30 lần trong 30 ngày            → confidence = 0.95
    - User xác nhận pattern                      → confidence = 1.0
    - User từ chối pattern                       → confidence = 0.0, is_active = False
    """
    
    async def analyze_daily(self):
        # 1. Query command_log 30 ngày gần nhất
        recent_commands = self.db.query("""
            SELECT device, area, action, hour, day_of_week, COUNT(*) as cnt
            FROM command_log
            WHERE timestamp > datetime('now', '-30 days')
            AND verify_result = 'success'
            GROUP BY device, area, action, hour
            HAVING cnt >= 5
            ORDER BY cnt DESC
        """)
        
        # 2. Với mỗi pattern tìm được
        for cmd in recent_commands:
            existing = self.db.get_pattern(
                cmd.device, cmd.area, cmd.action, cmd.hour
            )
            if existing:
                # Cập nhật confidence
                existing.occurrence_count = cmd.cnt
                existing.confidence = self.calculate_confidence(
                    cmd.cnt, existing.created_at
                )
                self.db.update_pattern(existing)
            else:
                # Tạo pattern mới
                self.db.insert_pattern(
                    pattern_type="daily_routine",
                    device=cmd.device,
                    area=cmd.area,
                    action=cmd.action,
                    trigger_hour=cmd.hour,
                    confidence=0.5,  # Khởi đầu thận trọng
                    occurrence_count=cmd.cnt,
                )
    
    def calculate_confidence(self, count, created_at):
        days_active = (now() - created_at).days
        if days_active < 7:
            return min(0.6, count / 10)
        elif days_active < 21:
            return min(0.85, count / 20)
        else:
            return min(0.95, count / 30)
```

---

## Phase 4 — Proactive Intelligence (Trí Tuệ Chủ Động)

> **🎯 Checkpoint:** Đây là ĐỈNH CAO của mục tiêu cốt lõi. Hệ thống không chờ lệnh nữa — nó CHỦ ĐỘNG hành động dựa trên patterns đã học. Từ "smart" chuyển thành "autonomous". Nhưng PHẢI CÓ CƠ CHẾ AN TOÀN để tránh hành động sai.

### 4.1 Proactive Action Engine

```python
# /home/pi4/smarthome/gateway/proactive_engine.py

class ProactiveEngine:
    """
    Chạy mỗi phút (cron), kiểm tra:
    1. Có pattern nào đến giờ trigger không?
    2. Confidence có đủ cao để tự động không?
    3. Thiết bị có đang ở trạng thái cần thay đổi không?
    
    CƠ CHẾ AN TOÀN 3 CẤP:
    - confidence < 0.7  → Chỉ GỢI Ý qua voice (hỏi user)
    - confidence 0.7~0.9 → Tự động nhưng THÔNG BÁO voice
    - confidence > 0.9   → Tự động IM LẶNG (chỉ log)
    - User từ chối 2 lần → Tạm dừng pattern 7 ngày
    """
    
    async def check_and_act(self):
        current_hour = datetime.now().hour
        current_dow = datetime.now().weekday()
        
        patterns = self.memory.get_active_patterns(
            trigger_hour=current_hour,
            trigger_day_of_week=current_dow
        )
        
        for pattern in patterns:
            device_state = self.registry.get_device_state(
                pattern.device, pattern.area
            )
            
            # Kiểm tra xem action có cần thiết không
            if pattern.action == "turn_on" and device_state == "on":
                continue  # Đã bật rồi, skip
            if pattern.action == "turn_off" and device_state == "off":
                continue  # Đã tắt rồi, skip
            
            if pattern.confidence < 0.7:
                # CẤP 1: GỢI Ý — hỏi user
                await self.suggest_via_voice(
                    f"Theo thói quen, bạn thường "
                    f"{self.action_to_text(pattern)} "
                    f"vào lúc này. Bạn có muốn em thực hiện không?"
                )
            elif pattern.confidence < 0.9:
                # CẤP 2: TỰ ĐỘNG + THÔNG BÁO
                await self.execute_and_notify(pattern)
            else:
                # CẤP 3: TỰ ĐỘNG IM LẶNG
                await self.execute_silently(pattern)
```

### 4.2 Proactive Scenarios (Kịch Bản Chủ Động)

| # | Kịch bản | Trigger | Hành động | Confidence cần |
|---|----------|---------|-----------|----------------|
| 1 | Sáng bật đèn phòng | 6:30 AM hàng ngày | Bật đèn trần phòng ngủ | > 0.7 |
| 2 | Tối tắt đèn sân | 11:00 PM hàng ngày | Tắt đèn sân vườn | > 0.7 |
| 3 | Quên tắt điều hòa | Chạy > 8 giờ liên tục | Voice nhắc | Anomaly |
| 4 | Tiêu thụ bất thường | Power > 150% baseline | Voice cảnh báo | Anomaly |
| 5 | Thiết bị bật không lệnh | Relay ON, no command | Voice hỏi | Anomaly |
| 6 | Báo cáo tổng kết ngày | 9:00 PM hàng ngày | Voice tổng kết | Always |

### 4.3 Qwen LLM — Context-Aware Analysis

Ngoài intent extraction, LLM còn được dùng để **phân tích dữ liệu** mỗi ngày:

```python
# Prompt cho daily analysis (chạy lúc 9 PM)
DAILY_ANALYSIS_PROMPT = """
Bạn là chuyên gia phân tích điện năng nhà thông minh.
Dữ liệu hôm nay:
{daily_telemetry_summary}

Lịch sử 7 ngày:
{weekly_trend}

Patterns đã học:
{active_patterns}

Nhiệm vụ:
1. Tóm tắt tình trạng sử dụng điện hôm nay (1-2 câu)
2. So sánh với 7 ngày trước (tăng/giảm bao nhiêu %)  
3. Nếu có bất thường, chỉ ra cụ thể
4. Gợi ý 1 mẹo tiết kiệm điện (nếu có)

Trả lời bằng tiếng Việt, ngắn gọn, thân thiện, phát qua loa.
"""
```

---

## Phase 5 — MCP Integration & Ecosystem

> **🎯 Checkpoint:** MCP (Model Context Protocol) mở rộng khả năng của LLM bằng cách cho phép nó GỌI CÁC TOOL bên ngoài — truy vấn Home Assistant, đọc thời tiết, kiểm tra lịch. Điều này giúp LLM "nhận thức" hơn khi ra quyết định.

### 5.1 MCP Server Architecture

```python
# /home/pi4/smarthome/mcp/smarthome_mcp_server.py

"""
MCP Server expose các Tools cho LLM:

1. get_device_status(area, device) → Trạng thái thiết bị
2. get_power_consumption(area, timerange) → Tiêu thụ điện  
3. control_device(area, device, action) → Điều khiển thiết bị
4. get_daily_report() → Báo cáo tổng kết
5. get_weather() → Thời tiết (external API)
6. search_command_history(query) → Tìm lịch sử lệnh
"""

from mcp.server import Server
from mcp.types import Tool

server = Server("smarthome-mcp")

@server.tool()
async def get_device_status(area: str, device: str) -> str:
    """Lấy trạng thái hiện tại của thiết bị"""
    node = registry.find_node(area, device)
    telemetry = latest_telemetry[node.id]
    return (
        f"{device} tại {area}: "
        f"{'BẬT' if telemetry.relay_on else 'TẮT'}, "
        f"công suất {telemetry.power}W"
    )

@server.tool()  
async def control_device(area: str, device: str, action: str) -> str:
    """Điều khiển thiết bị (bật/tắt)"""
    result = await gateway.execute_command(area, device, action)
    return f"Đã {action} {device} tại {area}. Kết quả: {result}"
```

### 5.2 Home Assistant Integration

```yaml
# Home Assistant configuration.yaml additions

mqtt:
  switch:
    - name: "Đèn Ngủ Phòng Ngủ"
      state_topic: "smarthome/status/esp32_wroom_01"
      command_topic: "smarthome/command/esp32_wroom_01"
      value_template: "{{ value_json.ch1 }}"
      payload_on: '{"channel":"ch1","action":"turn_on"}'
      payload_off: '{"channel":"ch1","action":"turn_off"}'
      
  sensor:
    - name: "Công Suất Phòng Ngủ"  
      state_topic: "smarthome/telemetry/esp32_wroom_01"
      unit_of_measurement: "W"
      value_template: "{{ value_json.power }}"
```

---

## Phase 6 — Dashboard & User Experience

> **🎯 Checkpoint:** Dashboard không phải mục tiêu cốt lõi, nhưng là GIAO DIỆN QUAN SÁT duy nhất để user theo dõi hệ thống đang "học" gì, "làm" gì. Thiếu dashboard = user mất niềm tin = dự án thất bại.

### 6.1 Grafana Dashboard

- **Panel 1:** Real-time power consumption (all nodes)
- **Panel 2:** Daily/Weekly energy trend
- **Panel 3:** Device activity timeline (khi nào bật/tắt)
- **Panel 4:** Anomaly alerts feed
- **Panel 5:** Learned patterns (hiển thị những gì hệ thống đã học)

### 6.2 Web Dashboard (Custom)

Tạo web UI tại `http://192.168.11.29:3000`:
- Đăng ký node mới (drag & drop floor plan)
- Xem trạng thái real-time
- Quản lý learned patterns (approve/reject)
- Voice log history

---

## Verification & Testing Strategy

### Mỗi Phase phải pass những test sau:

| Phase | Test | Criteria |
|-------|------|----------|
| 0 | Registry CRUD | Thêm/sửa/xóa node thành công |
| 0 | MQTT Ping | ESP32 → EMQX → Gateway roundtrip < 100ms |
| 1 | Audio Stream | Opus encode/decode không mất frame |
| 1 | ASR Accuracy | > 80% accuracy trên 50 câu tiếng Việt thường dùng |
| 1 | Intent JSON | > 90% parse đúng trên 30 câu test |
| 1 | End-to-End Voice | Nói "bật đèn ngủ" → đèn bật + voice reply < 6 giây |
| 2 | Verify Engine | Phát hiện đúng khi bật relay nhưng không có load |
| 2 | Anomaly Detect | Phát hiện thiết bị bật không có lệnh trong 10 giây |
| 3 | Pattern Learning | Sau 7 ngày test, hệ thống tìm ra ≥1 pattern đúng |
| 4 | Proactive Action | Hệ thống tự gợi ý/thực hiện action đúng thời điểm |
| 5 | MCP Tools | LLM gọi được get_device_status, control_device |

---

## Rủi Ro & Giải Pháp

| # | Rủi ro | Xác suất | Tác động | Giải pháp |
|---|--------|----------|----------|-----------|
| 1 | Pi 4 hết RAM (4GB) khi chạy đồng thời LLM + ASR + Docker | 🔴 Cao | 🔴 Crash | Giới hạn LLM context 512 tokens, ASR dùng small model, swap 2GB |
| 2 | Opus encode trên ESP32-S3 quá chậm | 🟡 TB | 🟡 Lag | Dùng complexity=0, frame 20ms, test trước |
| 3 | Sherpa-ONNX nhận sai tiếng Việt | 🟡 TB | 🟡 Lệnh sai | Hotword boosting, test extensive |
| 4 | EdgeTTS mất Internet | 🟡 TB | 🟡 Mất voice | Fallback: piper-tts offline |
| 5 | Qwen2.5 hiểu sai intent phức tạp | 🟡 TB | 🟡 Lệnh sai | Prompt engineering + correction loop |
| 6 | MQTT broker crash | 🟢 Thấp | 🔴 Mất ĐK | EMQX tự restart, ESP-NOW fallback |
| 7 | Proactive action sai | 🟡 TB | 🔴 Mất tin | Conservative confidence, ask-first mode |

---

## Timeline Dự Kiến

```
┌─────────────────────────────────────────────────────────────────┐
│  TUẦN 1-2: Phase 0 (Foundation)                                │
│  ├── Device Registry + MQTT Topics                             │
│  ├── ESP32 WROOM firmware: MQTT client                         │
│  └── Gateway skeleton (Python asyncio)                         │
│                                                                 │
│  TUẦN 3-4: Phase 1 (Voice Pipeline)                            │
│  ├── Opus encode trên ESP32-S3                                 │
│  ├── WebSocket audio server trên Pi                            │
│  ├── Sherpa-ONNX ASR integration                               │
│  ├── LLM intent engine (đã có prompt)                          │
│  └── EdgeTTS voice reply                                       │
│                                                                 │
│  TUẦN 5-6: Phase 2 (Closed-Loop)                               │
│  ├── Verify engine (command → telemetry feedback)              │
│  ├── Anomaly detection engine                                  │
│  ├── Telemetry pipeline → InfluxDB                             │
│  └── 🎯 MILESTONE: Nói "bật đèn" → đèn bật + xác nhận        │
│                                                                 │
│  TUẦN 7-8: Phase 3 (Memory & Learning)                         │
│  ├── SQLite memory schema                                      │
│  ├── Command logging + correction recording                    │
│  └── Pattern learning algorithm (daily cron)                   │
│                                                                 │
│  TUẦN 9-10: Phase 4 (Proactive Intelligence)                   │
│  ├── Proactive action engine                                   │
│  ├── Daily analysis report (LLM + EdgeTTS)                     │
│  └── 🎯 MILESTONE: Hệ thống tự gợi ý/thực hiện lần đầu       │
│                                                                 │
│  TUẦN 11-12: Phase 5-6 (MCP + Dashboard)                       │
│  ├── MCP server + Home Assistant integration                   │
│  ├── Grafana dashboards                                        │
│  └── 🎯 MILESTONE: Hệ thống hoàn chỉnh, tự vận hành          │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure Tổng Thể

```
/home/pi4/smarthome/
├── gateway/
│   ├── __init__.py
│   ├── main.py                   # Entry point (asyncio)
│   ├── config.py                 # Tất cả config tập trung
│   ├── audio_server.py           # WebSocket audio streaming
│   ├── asr_engine.py             # Sherpa-ONNX ASR
│   ├── intent_engine.py          # Qwen2.5 LLM intent extraction
│   ├── tts_engine.py             # EdgeTTS voice output
│   ├── mqtt_handler.py           # MQTT pub/sub
│   ├── registry_manager.py       # Device registry CRUD
│   ├── verify_engine.py          # Closed-loop verification
│   ├── anomaly_engine.py         # Anomaly detection
│   ├── telemetry_writer.py       # InfluxDB writer
│   ├── command_log.py            # SQLite command history
│   ├── memory_engine.py          # 3-tier memory system
│   ├── learning_engine.py        # Pattern learning algorithm
│   └── proactive_engine.py       # Proactive action engine
├── mcp/
│   └── smarthome_mcp_server.py   # MCP Tools for LLM
├── models/
│   ├── qwen2.5-1.5b-instruct-q4_k_m.gguf
│   └── sherpa-onnx-*/            # ASR model files
├── device_registry.json
├── memory.db                     # SQLite memory database
├── requirements.txt
├── docker-compose.yml            # EMQX, InfluxDB, Grafana, HA
└── systemd/
    ├── smarthome-gateway.service # Auto-start gateway
    └── llama-server.service      # Auto-start LLM server
```

```
d:/Home-Assistant-IoT-/
├── Firmware/
│   └── firmware_esp/
│       ├── Esp32S3_Master/       # Voice Node (I2S + WakeNet + Opus + WS)
│       └── Esp32_Wroom_Slave/    # Relay Node (PZEM + Relay + MQTT)
├── Gateway/                      # Mirror of Pi gateway code (Git sync)
├── App/                          # Mobile app (future)
├── Web/                          # Web dashboard (future)
└── plan.md                       # ← FILE NÀY
```

---

> ## 🎯 NHẮC LẠI MỤC TIÊU CỐT LÕI (đọc lại trước khi code bất kỳ dòng nào)
>
> **"Xây dựng hệ thống nhà thông minh TỰ HÀNH & NHẬN THỨC, lấy dữ liệu điện năng làm PHẢN HỒI VÒNG KÍN để TỰ HỌC thói quen người dùng và CHỦ ĐỘNG điều khiển."**
>
> - Mỗi Phase phải hoàn thành **test criteria** trước khi chuyển Phase tiếp theo.
> - Nếu một Phase bị delay, **KHÔNG** skip — mọi Phase sau phụ thuộc Phase trước.
> - Khi bị mất phương hướng → Đọc lại mục tiêu cốt lõi → Tự hỏi: "Dòng code này có giúp hệ thống TỰ HỌC và CHỦ ĐỘNG hơn không?"
