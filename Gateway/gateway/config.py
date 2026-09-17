"""
DTV Smart Home Gateway — Centralized Configuration
"""

import os
from pathlib import Path

# Tự động nạp cấu hình từ file .env nếu có (ở Gateway/.env hoặc /home/pi4/.env)
for env_candidate in [
    Path(__file__).resolve().parent.parent / ".env",
    Path("/home/pi4/.env"),
    Path(".env")
]:
    if env_candidate.exists():
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

# ─── MQTT ───────────────────────────────────────────
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "SmarthomePass2026!"
MQTT_CLIENT_ID = "smarthome_gateway"

# MQTT Topics (compact v2 — xem Gateway/protocol_spec.md)
TOPIC_REGISTER = "smarthome/register"      # legacy, giữ tương thích
TOPIC_HELLO = "smarthome/hello"            # node -> gateway (mới, nhẹ)
TOPIC_CFG = "smarthome/cfg/{mac_or_id}"    # gateway -> node provision
TOPIC_TELEMETRY = "smarthome/telemetry/{node_id}"  # legacy
TOPIC_TELE_SHORT = "smarthome/tele/{node_id}"      # mới, rút gọn
TOPIC_COMMAND = "smarthome/command/{node_id}"      # legacy {channel, action}
TOPIC_CMD_SHORT = "smarthome/cmd/{node_id}"        # mới {"t":"rl","ch":1,"s":1,"seq":n}
TOPIC_STATUS = "smarthome/status/{node_id}"        # legacy + ack mới
TOPIC_ALERT = "smarthome/alert"
TOPIC_VOICE_INTENT = "smarthome/voice/intent"

# ─── LLM Orchestration & Hybrid Engine ────────────────
# Chế độ: "hybrid" (Ưu tiên Gemini Cloud siêu nhanh 0.3s, tự động fallback về Qwen 3B nội bộ khi mất mạng)
#         "local"  (Luôn dùng Qwen 3B nội bộ trên Pi 4)
#         "cloud"  (Luôn dùng Cloud Gemini)
LLM_MODE = os.environ.get("LLM_MODE", "hybrid")

# Cloud LLM: Google Gemini 1.5 Flash (Miễn phí, phản hồi 0.3s, ngữ cảnh 1M tokens)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT = 3.5   # Giây tối đa chờ Cloud trước khi tự động chuyển sang Qwen 3B

# Local LLM: llama-server trên Pi 4 (Qwen2.5-3B-Instruct)
LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLAMA_TIMEOUT = 90.0   # 90s để model 3B trên Pi 4 hoàn thành ngay cả khi cold prompt eval
LLM_MAX_TOKENS = 60
LLM_TEMPERATURE = 0.0
LLM_CONTEXT_SIZE = 1024
LLM_GRAMMAR_ENABLED = True
LLM_PROMPT_CACHE = True

# ─── ASR (Sherpa-ONNX) ─────────────────────────────
ASR_MODEL_DIR = "/home/pi4/smarthome/models"
ASR_NUM_THREADS = 2
ASR_SAMPLE_RATE = 16000

# ─── TTS (EdgeTTS) ─────────────────────────────────
TTS_VOICE = "vi-VN-HoaiMyNeural"
TTS_FALLBACK_VOICE = "vi-VN-NamMinhNeural"

# ─── WebSocket Audio Server ────────────────────────
WS_AUDIO_HOST = "0.0.0.0"
WS_AUDIO_PORT = 8765

# ─── Web Monitor Dashboard ─────────────────────────
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# ─── InfluxDB ──────────────────────────────────────
INFLUX_URL = "http://127.0.0.1:8086"
INFLUX_TOKEN = ""  # Will be set after InfluxDB setup
INFLUX_ORG = "myhome"
INFLUX_BUCKET = "telemetry"

# ─── Device Registry ──────────────────────────────
REGISTRY_FILE = "/home/pi4/smarthome/device_registry.json"

# ─── Memory (SQLite) ──────────────────────────────
MEMORY_DB = "/home/pi4/smarthome/memory.db"

# ─── System ────────────────────────────────────────
LOG_LEVEL = "INFO"
VERIFY_TIMEOUT_SECONDS = 3.0
ANOMALY_SCAN_INTERVAL = 10.0
HEARTBEAT_TIMEOUT = 60
TELEMETRY_INTERVAL = 2.0

# ─── Audio Streaming (ESP32 ↔ Pi) ─────────────────
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2            # 16-bit = 2 bytes
AUDIO_FRAME_MS = 20               # 20ms per PCM frame
PCM_FRAME_SAMPLES = 320           # 16000 * 0.020 = 320 samples
PCM_FRAME_BYTES = 640             # 320 * 2 = 640 bytes
WS_SEND_CHUNK_SIZE = 2048         # Speaker PCM chunk size sent to ESP32

# ─── VAD (Voice Activity Detection) ───────────────
VAD_ENABLED = True                # Enable server-side VAD
VAD_SILENCE_DURATION_S = 1.5      # Seconds of silence before end-of-speech
VAD_MAX_DURATION_S = 10.0         # Maximum recording duration
VAD_ENERGY_THRESHOLD = 0.01       # RMS energy threshold (float PCM)

# ─── LLM System Prompt ────────────────────────────
# NLU 2 lớp: LLM chỉ phân tích ý định (intent), Gateway mới là nơi phân giải
# node_id/channel hợp lệ từ registry. LLM KHÔNG BAO GIỜ tự đặt tên node.
SYSTEM_PROMPT = """Bạn là bộ phân tích ý định (intent) cho Nhà Thông Minh IoT.
Nhiệm vụ DUY NHẤT: trích ý định từ khẩu lệnh tiếng Việt thành JSON.
Bạn KHÔNG biết node nào tồn tại. Bạn KHÔNG được bịa tên phòng hay thiết bị.
Nếu câu lệnh không nhắc phòng/thiết bị, để null — gateway sẽ tự suy luận.

Định dạng JSON duy nhất được phép:
{"voice_reply":"<câu xác nhận ngắn gọn, thân thiện>","command":{"action":"turn_on|turn_off","device":"den|quat|...|null","location":"phong_ngu|phong_khach|...|null","value":null}}
Chỉ xuất DUY NHẤT một chuỗi JSON hợp lệ, không giải thích thêm."""
