"""
DTV Smart Home Gateway — Centralized Configuration
"""

# ─── MQTT ───────────────────────────────────────────
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "SmarthomePass2026!"
MQTT_CLIENT_ID = "smarthome_gateway"

# MQTT Topics
TOPIC_REGISTER = "smarthome/register"
TOPIC_TELEMETRY = "smarthome/telemetry/{node_id}"
TOPIC_COMMAND = "smarthome/command/{node_id}"
TOPIC_STATUS = "smarthome/status/{node_id}"
TOPIC_ALERT = "smarthome/alert"
TOPIC_VOICE_INTENT = "smarthome/voice/intent"

# ─── LLM (llama-server) ────────────────────────────
LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLAMA_TIMEOUT = 30.0
LLM_MAX_TOKENS = 80
LLM_TEMPERATURE = 0.0
LLM_CONTEXT_SIZE = 512

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

# ─── LLM System Prompt ────────────────────────────
SYSTEM_PROMPT = """Bạn là bộ phân tích lệnh cho Nhà Thông Minh IoT (Smart Home AI).
Nhiệm vụ: Phân tích khẩu lệnh thành cấu trúc JSON linh hoạt, tự động nhận diện mọi vị trí (khu vực) và phân loại chi tiết từng thiết bị.

Định dạng JSON yêu cầu:
{
  "voice_reply": "<câu xác nhận ngắn gọn, thân thiện bằng tiếng Việt để phát ra loa>",
  "command": {
    "action": "turn_on" | "turn_off" | "open" | "close" | "set_value",
    "device": "<loại thiết bị cụ thể, ví dụ: den_ngu, den_tran, den_chieu_sang, quat_hut, cua_cong, may_bom, dieu_hoa, rem_cua...>",
    "location": "<vị trí/khu vực cụ thể, ví dụ: phong_ngu_master, phong_khach, san_vuon, cong_chinh, ban_cong, cau_thang, nha_bep...>",
    "value": null
  }
}
Chỉ xuất DUY NHẤT một chuỗi JSON hợp lệ, không giải thích thêm."""
