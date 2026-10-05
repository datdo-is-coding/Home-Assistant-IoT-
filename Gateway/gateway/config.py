"""
DTV Smart Home Gateway — Centralized Configuration
"""

import os
import json
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
MQTT_BROKER = os.environ.get("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883" if not os.environ.get("MQTT_CA_FILE") else "8883"))
MQTT_TLS_ENABLED = os.environ.get("MQTT_TLS_ENABLED", "true" if os.environ.get("MQTT_CA_FILE") or os.environ.get("MQTT_PORT") == "8883" else "false").lower() in ("true", "1", "yes")
MQTT_CA_FILE = os.environ.get("MQTT_CA_FILE", "")
MQTT_CERT_FILE = os.environ.get("MQTT_CERT_FILE", "")
MQTT_KEY_FILE = os.environ.get("MQTT_KEY_FILE", "")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "smarthome_gateway")
BOOTSTRAP_PASSWORD = os.environ.get("BOOTSTRAP_PASSWORD", "")
BOOTSTRAP_USERNAME = os.environ.get("BOOTSTRAP_USERNAME", "admin")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "43200"))
WEB_PUBLIC_ORIGIN = os.environ.get("WEB_PUBLIC_ORIGIN", "https://gateway.local").rstrip("/")

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

# ─── Device OS v1.0 Industrial MQTT Topics (Spec Section 14) ───
TOPIC_DEV_STATUS = "home/devices/{device_id}/status"
TOPIC_DEV_TELEMETRY = "home/devices/{device_id}/telemetry"
TOPIC_DEV_COMMAND = "home/devices/{device_id}/command"
TOPIC_DEV_CONFIG_DESIRED = "home/devices/{device_id}/config/desired"
TOPIC_DEV_CONFIG_REPORTED = "home/devices/{device_id}/config/reported"
TOPIC_DEV_RELAY_SET = "home/devices/{device_id}/relay/{channel}/set"
TOPIC_DEV_RELAY_STATE = "home/devices/{device_id}/relay/{channel}/state"
TOPIC_DEV_OTA_TRIGGER = "home/devices/{device_id}/ota/trigger"
TOPIC_DEV_OTA_PROGRESS = "home/devices/{device_id}/ota/progress"
TOPIC_DEV_UNCLAIMED = "home/discovery/unclaimed"

# ─── Feature Flags: Pure Voice Relay Mode vs AI Option ───────────────
# Khi AI_ENABLED = False: Hệ thống chạy chế độ điều khiển relay thuần túy bằng giọng nói,
# hoạt động 100% bằng Fast-Path Rule Engine siêu tốc (<5ms), hoàn toàn offline,
# không phụ thuộc LLM/Gemini, bỏ qua các module tán gẫu persona / proactive.
AI_ENABLED = os.environ.get("AI_ENABLED", "false").lower() in ("1", "true", "yes")
PERSONA_ENABLED = (os.environ.get("PERSONA_ENABLED", "false").lower() in ("1", "true", "yes")) and AI_ENABLED
PROACTIVE_ENABLED = (os.environ.get("PROACTIVE_ENABLED", "false").lower() in ("1", "true", "yes")) and AI_ENABLED
PERSONA_NAME = os.environ.get("PERSONA_NAME", "Lumi")

# ─── Acoustic Elegance & Audio Feedback Mode ──────────────────────────
# Chế độ phản hồi âm thanh:
# "hybrid": Tinh tế nhất (MẶC ĐỊNH) — Phát tiếng chuông chime/earcon êm dịu (listen_success)
#           xác nhận tức thì cho các lệnh bật/tắt thiết bị; chỉ dùng thoại ngắn khi cần
#           hỏi lại hoặc báo lỗi.
# "voice_brief": Thoại ngắn gọn, đĩnh đạc, thanh lịch (ví dụ: "Đã bật đèn.", "Đã tắt quạt.")
# "chime": Chỉ dùng âm thanh chuông xác nhận (chime tone), không nói thoại.
AUDIO_FEEDBACK_MODE = os.environ.get("AUDIO_FEEDBACK_MODE", "hybrid").lower()

# ─── LLM Orchestration & Engine (Chỉ kích hoạt khi AI_ENABLED = True) ─
# Chế độ: "off"    (Tắt hoàn toàn LLM, chỉ dùng Rule Engine - MẶC ĐỊNH)
#         "hybrid" (Ưu tiên Gemini Cloud, fallback Qwen 3B khi mất mạng)
#         "local"  (Chỉ dùng Qwen 3B nội bộ trên Pi 4)
#         "cloud"  (Chỉ dùng Cloud Gemini)
LLM_MODE = os.environ.get("LLM_MODE", "hybrid" if AI_ENABLED else "off")

# Cloud LLM: Google Gemini 1.5 Flash
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PROACTIVE_COOLDOWN_HOURS = float(os.environ.get("PROACTIVE_COOLDOWN_HOURS", "2.0"))
PROACTIVE_QUIET_START = int(os.environ.get("PROACTIVE_QUIET_START", "22"))   # 22h đêm bắt đầu im lặng
PROACTIVE_QUIET_END = int(os.environ.get("PROACTIVE_QUIET_END", "7"))        # 07h sáng kết thúc im lặng

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

_cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_config.json")
if os.path.exists(_cfg_file):
    try:
        with open(_cfg_file, "r", encoding="utf-8") as _f:
            _loaded = json.load(_f)
            if "GEMINI_MODEL" in _loaded and _loaded["GEMINI_MODEL"].strip():
                GEMINI_MODEL = _loaded["GEMINI_MODEL"].strip()
            if "PROACTIVE_ENABLED" in _loaded:
                PROACTIVE_ENABLED = bool(_loaded["PROACTIVE_ENABLED"])
            if "TTS_RATE" in _loaded:
                TTS_RATE = str(_loaded["TTS_RATE"]).strip()
            if "TTS_PITCH" in _loaded:
                TTS_PITCH = str(_loaded["TTS_PITCH"]).strip()
            if "TTS_PROVIDER" in _loaded:
                TTS_PROVIDER = str(_loaded["TTS_PROVIDER"]).strip()
            if "VIENEU_MODE" in _loaded:
                VIENEU_MODE = str(_loaded["VIENEU_MODE"]).strip()
            if "VIENEU_VOICE" in _loaded:
                VIENEU_VOICE = str(_loaded["VIENEU_VOICE"]).strip()
    except Exception:
        pass

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT = 3.5   # Giây tối đa chờ Cloud trước khi tự động chuyển sang Qwen 3B

# Local LLM: llama-server trên Pi 4 (Qwen2.5-3B-Instruct)
LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLAMA_TIMEOUT = 10.0   # 10s cho CPU Pi 4 phản hồi an toàn
LLM_MAX_TOKENS = 60
LLM_TEMPERATURE = 0.0
LLM_CONTEXT_SIZE = 1024
LLM_GRAMMAR_ENABLED = True
LLM_PROMPT_CACHE = True


# ─── ASR (Sherpa-ONNX) ─────────────────────────────
ASR_MODEL_DIR = "/home/pi4/smarthome/models"
ASR_NUM_THREADS = 2
ASR_SAMPLE_RATE = 16000

# ─── TTS Architecture (Dual Engine: EdgeTTS Cloud vs VieNeu-TTS Local) ──
# TTS_PROVIDER: "edgetts" (Mặc định giọng Hoài My Neural ngọt ngào, dịu dàng) hoặc "vieneu" (Local 0 token)
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "edgetts")

# EdgeTTS Settings (Ngọt ngào, êm dịu, chuẩn phong cách trợ lý gia đình)
TTS_VOICE = os.environ.get("TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_FALLBACK_VOICE = "vi-VN-NamMinhNeural"
TTS_RATE = os.environ.get("TTS_RATE", "-4%")     # Nhịp độ thong thả hơn 4% để giọng ấm, dịu dàng, thủ thỉ
TTS_PITCH = os.environ.get("TTS_PITCH", "+2Hz")   # Nâng cao độ nhẹ 2Hz để giọng nữ trong trẻo, ngọt ngào

# VieNeu-TTS Settings (Local on-device CPU)
VIENEU_MODE = os.environ.get("VIENEU_MODE", "v3nano")
VIENEU_VOICE = os.environ.get("VIENEU_VOICE", "Ái Hân")

# ─── OTA Firmware Repository ─────────────────────────
FIRMWARE_DIR = os.environ.get("FIRMWARE_DIR", "/home/pi4/Home-Assistant-IoT-/Gateway/firmware")
if not os.path.exists(FIRMWARE_DIR):
    _loc_fw = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware")
    os.makedirs(_loc_fw, exist_ok=True)
    FIRMWARE_DIR = _loc_fw

# ─── Auth & Multi-tenant Security ────────────────────
AUTH_ENABLED = True
AUTH_DB = os.environ.get("AUTH_DB", "/home/pi4/smarthome/auth.db")



# ─── WebSocket Audio Server ────────────────────────
WS_AUDIO_HOST = os.environ.get("WS_AUDIO_HOST", "0.0.0.0")
WS_AUDIO_PORT = 8765
WS_AUDIO_TLS_CERT = os.environ.get("WS_AUDIO_TLS_CERT", "")
WS_AUDIO_TLS_KEY = os.environ.get("WS_AUDIO_TLS_KEY", "")
WS_AUDIO_TOKEN = os.environ.get("WS_AUDIO_TOKEN", "")
WS_AUDIO_TOKENS = json.loads(os.environ.get("WS_AUDIO_TOKENS", "{}"))

# ─── Web Monitor Dashboard ─────────────────────────
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "8000"))

# ─── InfluxDB ──────────────────────────────────────
INFLUX_URL = "http://127.0.0.1:8086"
INFLUX_TOKEN = ""  # Will be set after InfluxDB setup
INFLUX_ORG = "myhome"
INFLUX_BUCKET = "telemetry"

# ─── Device Registry (SQLite v1.0 Spec) ─────────────
REGISTRY_FILE = os.environ.get("REGISTRY_FILE", "/home/pi4/smarthome/device_registry.json")
if not os.path.exists(os.path.dirname(REGISTRY_FILE)):
    REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_registry.json")

GATEWAY_DB = os.environ.get("GATEWAY_DB", "/var/lib/smarthome/gateway.db")
if not os.path.exists(os.path.dirname(GATEWAY_DB)):
    GATEWAY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway.db")

# ─── Memory (SQLite) ──────────────────────────────
MEMORY_DB = os.environ.get("MEMORY_DB", "/home/pi4/smarthome/memory.db")
if not os.path.exists(os.path.dirname(MEMORY_DB)):
    MEMORY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

# ─── System ────────────────────────────────────────
LOG_LEVEL = "INFO"
VERIFY_TIMEOUT_SECONDS = 0.2
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

Quy tắc quan trọng:
- Trong "command.location" dùng ID dạng snake_case: phong_ngu, phong_khach, phong_ngu_master, phong_bep, phong_lam_viec, san_vuon, ban_cong, gara, phong_tam, hanh_lang.
- Trong "voice_reply", BẮT BUỘC dùng tiếng Việt có dấu tự nhiên (ví dụ: "Đã bật quạt ở phòng khách ạ.", "Đã tắt đèn ngủ phòng ngủ ạ."). TUYỆT ĐỐI KHÔNG dùng từ ngữ kiểu "phong_ngu", "phong_khach" trong voice_reply.

Định dạng JSON duy nhất được phép:
{"voice_reply":"<câu xác nhận ngắn gọn tiếng Việt có dấu>","command":{"action":"turn_on|turn_off","device":"den|quat|...|null","location":"phong_ngu|phong_khach|...|null","value":null}}
Chỉ xuất DUY NHẤT một chuỗi JSON hợp lệ, không giải thích thêm."""
