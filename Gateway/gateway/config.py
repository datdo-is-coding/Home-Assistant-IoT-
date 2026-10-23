"""
DTV Smart Home Gateway — Centralized Configuration
"""

import os
import json
from pathlib import Path

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

TOPIC_REGISTER = "smarthome/register"
TOPIC_HELLO = "smarthome/hello"
TOPIC_CFG = "smarthome/cfg/{mac_or_id}"
TOPIC_TELEMETRY = "smarthome/telemetry/{node_id}"
TOPIC_TELE_SHORT = "smarthome/tele/{node_id}"
TOPIC_COMMAND = "smarthome/command/{node_id}"
TOPIC_CMD_SHORT = "smarthome/cmd/{node_id}"
TOPIC_STATUS = "smarthome/status/{node_id}"
TOPIC_ALERT = "smarthome/alert"
TOPIC_VOICE_INTENT = "smarthome/voice/intent"

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

AI_ENABLED = os.environ.get("AI_ENABLED", "false").lower() in ("1", "true", "yes")
PERSONA_ENABLED = (os.environ.get("PERSONA_ENABLED", "false").lower() in ("1", "true", "yes")) and AI_ENABLED
PROACTIVE_ENABLED = (os.environ.get("PROACTIVE_ENABLED", "false").lower() in ("1", "true", "yes")) and AI_ENABLED
PERSONA_NAME = os.environ.get("PERSONA_NAME", "Lumi")

AUDIO_FEEDBACK_MODE = os.environ.get("AUDIO_FEEDBACK_MODE", "hybrid").lower()

LLM_MODE = os.environ.get("LLM_MODE", "hybrid" if AI_ENABLED else "off")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PROACTIVE_COOLDOWN_HOURS = float(os.environ.get("PROACTIVE_COOLDOWN_HOURS", "2.0"))
PROACTIVE_QUIET_START = int(os.environ.get("PROACTIVE_QUIET_START", "22"))
PROACTIVE_QUIET_END = int(os.environ.get("PROACTIVE_QUIET_END", "7"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "edgetts")

TTS_VOICE = os.environ.get("TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_FALLBACK_VOICE = "vi-VN-NamMinhNeural"
TTS_RATE = os.environ.get("TTS_RATE", "-4%")
TTS_PITCH = os.environ.get("TTS_PITCH", "+2Hz")

VIENEU_MODE = os.environ.get("VIENEU_MODE", "v3nano")
VIENEU_VOICE = os.environ.get("VIENEU_VOICE", "Ái Hân")

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
GEMINI_TIMEOUT = 3.5

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLAMA_TIMEOUT = 10.0
LLM_MAX_TOKENS = 60
LLM_TEMPERATURE = 0.0
LLM_CONTEXT_SIZE = 1024
LLM_GRAMMAR_ENABLED = True
LLM_PROMPT_CACHE = True

ASR_MODEL_DIR = "/home/pi4/smarthome/models"
ASR_NUM_THREADS = 2
ASR_SAMPLE_RATE = 16000


FIRMWARE_DIR = os.environ.get("FIRMWARE_DIR", "/home/pi4/Home-Assistant-IoT-/Gateway/firmware")
if not os.path.exists(FIRMWARE_DIR):
    _loc_fw = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware")
    os.makedirs(_loc_fw, exist_ok=True)
    FIRMWARE_DIR = _loc_fw

AUTH_ENABLED = True
AUTH_DB = os.environ.get("AUTH_DB", "/home/pi4/smarthome/auth.db")

WS_AUDIO_HOST = os.environ.get("WS_AUDIO_HOST", "0.0.0.0")
WS_AUDIO_PORT = 8765
WS_AUDIO_TLS_CERT = os.environ.get("WS_AUDIO_TLS_CERT", "")
WS_AUDIO_TLS_KEY = os.environ.get("WS_AUDIO_TLS_KEY", "")
WS_AUDIO_TOKEN = os.environ.get("WS_AUDIO_TOKEN", "")
WS_AUDIO_AUTH_REQUIRED = os.environ.get("WS_AUDIO_AUTH_REQUIRED", "false").lower() in ("true", "1", "yes")
ALLOW_BROADCAST_COMMANDS = False
try:
    WS_AUDIO_TOKENS = json.loads(os.environ.get("WS_AUDIO_TOKENS", "{}"))
except Exception:
    WS_AUDIO_TOKENS = {}


WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "8000"))

INFLUX_URL = "http://127.0.0.1:8086"
INFLUX_TOKEN = ""
INFLUX_ORG = "myhome"
INFLUX_BUCKET = "telemetry"

REGISTRY_FILE = os.environ.get("REGISTRY_FILE", "/home/pi4/smarthome/device_registry.json")
if not os.path.exists(os.path.dirname(REGISTRY_FILE)):
    REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_registry.json")

GATEWAY_DB = os.environ.get("GATEWAY_DB", "/var/lib/smarthome/gateway.db")
if not os.path.exists(os.path.dirname(GATEWAY_DB)):
    GATEWAY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway.db")

MEMORY_DB = os.environ.get("MEMORY_DB", "/home/pi4/smarthome/memory.db")
if not os.path.exists(os.path.dirname(MEMORY_DB)):
    MEMORY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

LOG_LEVEL = "INFO"
VERIFY_TIMEOUT_SECONDS = 0.2
ANOMALY_SCAN_INTERVAL = 10.0
HEARTBEAT_TIMEOUT = 60
TELEMETRY_INTERVAL = 2.0

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2
AUDIO_FRAME_MS = 20
PCM_FRAME_SAMPLES = 320
PCM_FRAME_BYTES = 640
WS_SEND_CHUNK_SIZE = 2048

VAD_ENABLED = True
VAD_SILENCE_DURATION_S = 1.5
VAD_MAX_DURATION_S = 10.0
VAD_ENERGY_THRESHOLD = 0.01

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
